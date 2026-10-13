export const VERSION = 1 as const;
export const TTL_MS = 900_000;
export const MAX_FRAME_BYTES = 65_536;
export type Status = "accepted" | "processing" | "completed" | "queued" | "sending" |
  "confirmed" | "unknown" | "failed" | "expired" | "rejected";
export type Inbound = { v: 1; type: "inbound.message"; eventId: string; roomId: "self"; observedAt: number; text: string };
export type Outbound = { v: 1; type: "outbound.message"; deliveryId: string; roomId: "self";
  createdAt: number; expiresAt: number; kind: "reply" | "notification"; text: string };
export type Ack = { v: 1; type: "ack"; id: string; status: Status };
export type Hello = { v: 1; type: "hello"; bridgeId: string; token: string };
export type Frame = Inbound | Outbound | Ack | Hello | { v: 1; type: "ready" } |
  { v: 1; type: "cancel.delivery"; id: string };
const statuses = new Set<Status>(["accepted", "processing", "completed", "queued", "sending", "confirmed",
  "unknown", "failed", "expired", "rejected"]);

export function identifier(value: unknown): asserts value is string {
  if (typeof value !== "string" || !/^[A-Za-z0-9_.:/-]{1,160}$/.test(value)) throw new Error("invalid_id");
}
export function target(value: string): "self" {
  if (value !== "self" && value !== "kakao-local:self") throw new Error("unsupported_room");
  return "self";
}
export function parseFrame(raw: string): Frame {
  if (Buffer.byteLength(raw) > MAX_FRAME_BYTES) throw new Error("frame_too_large");
  const frame = JSON.parse(raw) as Record<string, unknown>;
  if (!frame || typeof frame !== "object" || frame.v !== VERSION) throw new Error("protocol_mismatch");
  switch (frame.type) {
    case "inbound.message":
    case "outbound.message": {
      if (frame.roomId !== "self") throw new Error("unsupported_room");
      identifier(frame.type === "inbound.message" ? frame.eventId : frame.deliveryId);
      const limit = frame.type === "inbound.message" ? 4000 : 16000;
      if (typeof frame.text !== "string" || !frame.text.trim() || [...frame.text].length > limit || frame.text.includes("\0")) {
        throw new Error("invalid_text");
      }
      const fields = frame.type === "inbound.message" ? ["observedAt"] : ["createdAt", "expiresAt"];
      for (const field of fields) {
        if (typeof frame[field] !== "number" || !Number.isFinite(frame[field]) || frame[field] < 0) throw new Error("invalid_timestamp");
      }
      if (frame.type === "outbound.message") {
        const ttl = Number(frame.expiresAt) - Number(frame.createdAt);
        if (ttl <= 0 || ttl > TTL_MS || !["reply", "notification"].includes(String(frame.kind))) throw new Error("invalid_expiry");
      }
      break;
    }
    case "hello":
      identifier(frame.bridgeId);
      if (typeof frame.token !== "string" || !/^[a-f0-9]{64}$/.test(frame.token)) throw new Error("invalid_pairing");
      break;
    case "ack":
      identifier(frame.id);
      if (!statuses.has(frame.status as Status)) throw new Error("invalid_ack");
      break;
    case "cancel.delivery": identifier(frame.id); break;
    case "ready": break;
    default: throw new Error("unknown_frame");
  }
  return frame as Frame;
}
export const ack = (id: string, status: Status): Ack => ({ v: VERSION, type: "ack", id, status });
