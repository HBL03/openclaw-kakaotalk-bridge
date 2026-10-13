import { timingSafeEqual } from "node:crypto";
import { WebSocket, WebSocketServer } from "ws";
import { Journal } from "./journal.js";
import { ack, type Inbound, type Outbound, type Status, MAX_FRAME_BYTES, parseFrame } from "./protocol.js";

export class DeliveryError extends Error {
  constructor(readonly state: Status) { super(`delivery_${state}`); }
}
type Options = { port: number; token: string; bridgeId: string; journal: Journal;
  onInbound: (event: Inbound) => Promise<void>; onStatus?: (connected: boolean) => void };

export class BridgeTransport {
  private server?: WebSocketServer;
  private peer?: WebSocket;
  private timer?: NodeJS.Timeout;
  private pumping = false;
  private pumpTask?: Promise<void>;
  private closing = false;
  private lastPong = 0;
  private waiting = new Map<string, { resolve: () => void; reject: (error: Error) => void; cleanup: () => void }>();
  constructor(readonly options: Options) {
    if (!/^[a-f0-9]{64}$/.test(options.token)) throw new Error("invalid_pairing_secret");
  }
  get port(): number { const address = this.server?.address(); return typeof address === "object" && address ? address.port : 0; }
  get connected(): boolean { return this.peer?.readyState === WebSocket.OPEN; }
  async start(): Promise<void> {
    this.server = new WebSocketServer({ host: "127.0.0.1", port: this.options.port, maxPayload: MAX_FRAME_BYTES,
      perMessageDeflate: false, verifyClient: ({ origin }: { origin: string }) => !origin });
    await new Promise<void>((resolve, reject) => { this.server!.once("listening", resolve); this.server!.once("error", reject); });
    this.server.on("error", () => this.options.onStatus?.(false));
    this.server.on("connection", socket => {
      if (this.closing || this.server!.clients.size > 8) { socket.close(1013); return; }
      let authenticated = false;
      const timeout = setTimeout(() => socket.close(1008), 3000);
      socket.on("error", () => socket.close());
      socket.on("message", raw => {
        if (socket.readyState !== WebSocket.OPEN) return;
        try {
          const frame = parseFrame(raw.toString());
          if (!authenticated) {
            if ((frame.type !== "hello" && frame.type !== "probe") || frame.bridgeId !== this.options.bridgeId ||
                !timingSafeEqual(Buffer.from(frame.token), Buffer.from(this.options.token))) {
              socket.close(1008, "pairing_rejected"); return;
            }
            if (frame.type === "probe") {
              clearTimeout(timeout);
              socket.send(JSON.stringify({ v: 1, type: "ready" }));
              socket.close(1000);
              return;
            }
            if (this.connected) { socket.close(1008, "peer_already_connected"); return; }
            authenticated = true;
            clearTimeout(timeout);
            this.peer = socket;
            this.lastPong = Date.now();
            this.send({ v: 1, type: "ready" });
            this.options.onStatus?.(true);
            // Replay only deliveries whose SDK caller still owns an active wait.
            for (const id of this.waiting.keys()) this.transmit(id);
            this.schedulePump();
          } else if (frame.type === "inbound.message") {
            const status = this.options.journal.admit(frame);
            this.send(ack(frame.eventId, status));
            if (status === "accepted") this.schedulePump();
          } else if (frame.type === "ack") {
            if (!this.waiting.has(frame.id)) return;
            if (["confirmed", "unknown", "expired", "failed", "rejected"].includes(frame.status)) {
              this.options.journal.finish(frame.id, frame.status);
              this.settle(frame.id, frame.status);
            }
          } else {
            socket.close(1008, "unexpected_frame");
          }
        } catch { socket.close(1008, "invalid_frame"); }
      });
      socket.on("close", () => {
        clearTimeout(timeout);
        if (this.peer === socket) { this.peer = undefined; this.options.onStatus?.(false); }
      });
      socket.on("pong", () => { if (this.peer === socket) this.lastPong = Date.now(); });
    });
    this.timer = setInterval(() => {
      try {
        this.options.journal.prune();
        for (const id of this.waiting.keys()) {
          const row = this.options.journal.get(id);
          if (row && !["queued", "sending"].includes(row.state)) this.settle(id, row.state);
        }
        if (this.connected) {
          if (Date.now() - this.lastPong > 45_000) this.peer!.terminate();
          else this.peer!.ping();
        }
      } catch { this.failClosed(); }
    }, 1000);
    this.timer.unref();
    this.schedulePump();
  }
  private failClosed(): void {
    this.closing = true;
    if (this.timer) clearInterval(this.timer);
    for (const id of [...this.waiting.keys()]) this.settle(id, "unknown");
    for (const socket of this.server?.clients ?? []) socket.terminate();
    this.options.onStatus?.(false);
  }
  private schedulePump(): void {
    if (this.pumping || this.closing) return;
    this.pumpTask = this.pump().catch(() => this.failClosed());
  }
  private send(frame: object): void {
    if (this.connected) this.peer!.send(JSON.stringify(frame));
  }
  private async pump(): Promise<void> {
    if (this.pumping || this.closing) return;
    this.pumping = true;
    try {
      for (let event = this.options.journal.next(); event && !this.closing; event = this.options.journal.next()) {
        this.options.journal.inboundState(event.eventId, "processing");
        this.send(ack(event.eventId, "processing"));
        let state: Status = "completed";
        try { await this.options.onInbound(event); }
        catch { state = "unknown"; } // Never re-run a turn with possibly completed tool actions.
        this.options.journal.inboundState(event.eventId, state);
        this.send(ack(event.eventId, state));
      }
    } finally { this.pumping = false; }
  }
  private transmit(id: string): void {
    const row = this.options.journal.get(id);
    if (!row?.payload || row.expires <= Date.now() || !this.connected) return;
    // Persist handoff before socket I/O. Duplicate frames retain the exact stored envelope.
    this.options.journal.finish(id, "sending");
    this.peer!.send(row.payload);
  }
  private settle(id: string, state: Status): void {
    const waiter = this.waiting.get(id);
    if (!waiter) return;
    this.waiting.delete(id);
    waiter.cleanup();
    if (state === "confirmed") waiter.resolve(); else waiter.reject(new DeliveryError(state));
  }
  async deliver(id: string, text: string, kind: Outbound["kind"], signal?: AbortSignal): Promise<void> {
    if (this.closing || signal?.aborted) throw new DeliveryError("failed");
    const row = this.options.journal.outbound(id, text, kind);
    if (row.state === "confirmed") return;
    if (!["queued", "sending"].includes(row.state)) throw new DeliveryError(row.state);
    if (this.waiting.has(id)) throw new Error("delivery_already_owned");
    await new Promise<void>((resolve, reject) => {
      const abort = () => {
        const state = this.options.journal.get(id)?.state === "queued" ? "failed" : "unknown";
        this.send({ v: 1, type: "cancel.delivery", id });
        this.options.journal.finish(id, state);
        this.settle(id, state);
      };
      this.waiting.set(id, { resolve, reject, cleanup: () => signal?.removeEventListener("abort", abort) });
      signal?.addEventListener("abort", abort, { once: true });
      if (signal?.aborted) abort(); else this.transmit(id);
    });
  }
  async close(): Promise<void> {
    this.closing = true;
    if (this.timer) clearInterval(this.timer);
    for (const id of [...this.waiting.keys()]) {
      const state = this.options.journal.get(id)?.state === "queued" ? "failed" : "unknown";
      this.send({ v: 1, type: "cancel.delivery", id });
      this.options.journal.finish(id, state);
      this.settle(id, state);
    }
    for (const socket of this.server?.clients ?? []) socket.terminate();
    if (this.server) await new Promise<void>(resolve => this.server!.close(() => resolve()));
    // The account lifecycle must not replace this transport while an admitted turn still settles.
    await this.pumpTask;
  }
}
