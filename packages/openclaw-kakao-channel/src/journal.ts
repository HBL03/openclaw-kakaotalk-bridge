import { createHash } from "node:crypto";
import { chmodSync, mkdirSync, statSync } from "node:fs";
import { dirname } from "node:path";
import { DatabaseSync } from "node:sqlite";
import { type Inbound, type Outbound, type Status, parseFrame, TTL_MS } from "./protocol.js";

type Row = { id: string; digest: string; payload: string | null; state: Status; created: number; expires: number };
/** A transport journal, not a second worker that retries OpenClaw agent turns. */
export class Journal {
  readonly db: DatabaseSync;
  constructor(readonly path: string, readonly maxRequestsPerHour = 60) {
    if (!Number.isInteger(maxRequestsPerHour) || maxRequestsPerHour < 1 || maxRequestsPerHour > 600)
      throw new Error("invalid_usage_limits");
    if (path !== ":memory:") mkdirSync(dirname(path), { recursive: true, mode: 0o700 });
    this.db = new DatabaseSync(path);
    this.db.exec(`PRAGMA journal_mode=DELETE; PRAGMA secure_delete=ON; PRAGMA synchronous=FULL;
      CREATE TABLE IF NOT EXISTS inbound(id TEXT PRIMARY KEY,digest TEXT,payload TEXT,state TEXT,created INTEGER);
      CREATE TABLE IF NOT EXISTS outbound(id TEXT PRIMARY KEY,digest TEXT,payload TEXT,state TEXT,created INTEGER,expires INTEGER);
      UPDATE inbound SET state='unknown',payload=NULL WHERE state='processing';
      UPDATE outbound SET state='unknown',payload=NULL WHERE state='sending';
      PRAGMA user_version=1;`);
    if (path !== ":memory:") chmodSync(path, 0o600);
  }
  close(): void { this.db.close(); }
  private digest(value: unknown): string { return createHash("sha256").update(JSON.stringify(value)).digest("hex"); }
  admit(event: Inbound, now = Date.now()): Status {
    this.prune(now);
    const digest = this.digest(event);
    const old = this.db.prepare("SELECT digest,state FROM inbound WHERE id=?").get(event.eventId) as Row | undefined;
    if (old) {
      if (old.digest !== digest) throw new Error("event_id_collision");
      return old.state;
    }
    const count = this.db.prepare("SELECT count(*) AS n FROM inbound WHERE state='accepted'").get() as { n: number };
    const recent = this.db.prepare("SELECT count(*) AS n FROM inbound WHERE created>? AND state NOT IN ('rejected','expired')")
      .get(now - 3_600_000) as { n: number };
    const state = event.observedAt > now + 60_000 || event.observedAt + TTL_MS <= now ? "expired" :
      count.n >= 5 || recent.n >= this.maxRequestsPerHour ? "rejected" : "accepted";
    this.db.prepare("INSERT INTO inbound VALUES(?,?,?,?,?)").run(event.eventId, digest,
      state === "accepted" ? JSON.stringify(event) : null, state, now);
    return state;
  }
  next(): Inbound | undefined {
    this.prune();
    const row = this.db.prepare("SELECT payload FROM inbound WHERE state='accepted' ORDER BY created,rowid LIMIT 1").get() as { payload: string } | undefined;
    return row ? JSON.parse(row.payload) as Inbound : undefined;
  }
  inboundState(id: string, state: Status): void {
    this.db.prepare("UPDATE inbound SET state=?,payload=CASE WHEN ?='accepted' THEN payload ELSE NULL END WHERE id=?").run(state, state, id);
  }
  outbound(id: string, text: string, kind: Outbound["kind"], now = Date.now()): Row {
    this.prune(now);
    const digest = this.digest({ text, kind });
    let row = this.get(id);
    if (row) {
      if (row.digest !== digest) throw new Error("delivery_id_collision");
      return row;
    }
    const count = this.db.prepare("SELECT count(*) AS n FROM outbound WHERE state IN ('queued','sending')").get() as { n: number };
    if (count.n >= 10) throw new Error("outbound_queue_full");
    const payload: Outbound = { v: 1, type: "outbound.message", deliveryId: id, roomId: "self",
      text, kind, createdAt: now, expiresAt: now + TTL_MS };
    parseFrame(JSON.stringify(payload));
    this.db.prepare("INSERT INTO outbound VALUES(?,?,?,?,?,?)").run(id, digest, JSON.stringify(payload), "queued", now, now + TTL_MS);
    row = this.get(id);
    if (!row) throw new Error("journal_write_failed");
    return row;
  }
  get(id: string): Row | undefined { return this.db.prepare("SELECT * FROM outbound WHERE id=?").get(id) as Row | undefined; }
  finish(id: string, state: Status): void {
    this.db.prepare("UPDATE outbound SET state=?,payload=CASE WHEN ? IN ('queued','sending') THEN payload ELSE NULL END WHERE id=?").run(state, state, id);
  }
  prune(now = Date.now()): void {
    this.db.prepare("UPDATE outbound SET state=CASE WHEN state='sending' THEN 'unknown' ELSE 'expired' END,payload=NULL WHERE expires<=? AND state IN ('queued','sending')").run(now);
    this.db.prepare("UPDATE inbound SET state='expired',payload=NULL WHERE state='accepted' AND json_extract(payload,'$.observedAt')<=?").run(now - TTL_MS);
    const cutoff = now - 7 * 86_400_000;
    this.db.prepare("DELETE FROM inbound WHERE created<? AND state NOT IN ('accepted','processing')").run(cutoff);
    this.db.prepare("DELETE FROM outbound WHERE created<? AND state NOT IN ('queued','sending')").run(cutoff);
    if (this.path !== ":memory:" && statSync(this.path).size > 20 * 1024 * 1024) throw new Error("journal_size_limit");
  }
}
