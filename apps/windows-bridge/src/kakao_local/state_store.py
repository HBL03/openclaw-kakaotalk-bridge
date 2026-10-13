"""Durable UI dispatch journal. A SENDING record is never blindly replayed."""
import hashlib
import json
import sqlite3
from pathlib import Path
from .models import BridgeError
from .protocol import TTL_MS, now_ms


class StateStore:
    def __init__(self, path: Path | str):
        if str(path) != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.executescript("""
            PRAGMA journal_mode=DELETE;
            PRAGMA secure_delete=ON;
            PRAGMA synchronous=FULL;
            CREATE TABLE IF NOT EXISTS inbound (
              id TEXT PRIMARY KEY, payload TEXT, state TEXT NOT NULL, created INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS deliveries (
              id TEXT PRIMARY KEY, digest TEXT NOT NULL, payload TEXT, state TEXT NOT NULL,
              created INTEGER NOT NULL, expires INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS parts (
              id TEXT NOT NULL, part INTEGER NOT NULL, state TEXT NOT NULL,
              PRIMARY KEY(id, part)
            );
            PRAGMA user_version=1;
        """)
        with self.db:
            self.db.execute("UPDATE deliveries SET state='unknown',payload=NULL WHERE state='sending'")
            self.db.execute("UPDATE parts SET state='unknown' WHERE state='sending'")

    def close(self) -> None:
        self.db.close()

    def admit_inbound(self, event: dict) -> bool:
        with self.db:
            if self.db.execute("SELECT 1 FROM inbound WHERE id=?", (event["eventId"],)).fetchone():
                return False
            count = self.db.execute("SELECT count(*) FROM inbound WHERE state='observed'").fetchone()[0]
            if count >= 5:
                raise BridgeError("inbound_queue_full")
            self.db.execute("INSERT INTO inbound VALUES (?,?,?,?)", (
                event["eventId"], json.dumps(event), "observed", event["observedAt"]))
        return True

    def pending_inbound(self, at: int | None = None) -> list[dict]:
        at = now_ms() if at is None else at
        with self.db:
            self.db.execute("UPDATE inbound SET state='expired',payload=NULL WHERE state='observed' AND created<=?",
                            (at - TTL_MS,))
        return [json.loads(row[0]) for row in self.db.execute(
            "SELECT payload FROM inbound WHERE state='observed' ORDER BY created,rowid")]

    def inbound_ack(self, identity: str, state: str) -> None:
        with self.db:
            self.db.execute("UPDATE inbound SET state=?,payload=NULL WHERE id=?", (state, identity))

    def admit_delivery(self, event: dict, at: int | None = None) -> str:
        at = now_ms() if at is None else at
        digest = hashlib.sha256(json.dumps(event, sort_keys=True).encode()).hexdigest()
        identity = event["deliveryId"]
        with self.db:
            row = self.db.execute("SELECT digest,state FROM deliveries WHERE id=?", (identity,)).fetchone()
            if row:
                if row["digest"] != digest:
                    raise BridgeError("delivery_id_collision")
                return row["state"]
            self.expire(at)
            state = "expired" if event["expiresAt"] <= at else "queued"
            if state == "queued":
                count = self.db.execute("SELECT count(*) FROM deliveries WHERE state IN ('queued','sending')").fetchone()[0]
                if count >= 10:
                    raise BridgeError("outbound_queue_full")
            self.db.execute("INSERT INTO deliveries VALUES (?,?,?,?,?,?)", (
                identity, digest, json.dumps(event) if state == "queued" else None,
                state, event["createdAt"], event["expiresAt"]))
        return state

    def expire(self, at: int) -> None:
        self.db.execute("""UPDATE deliveries SET state=CASE WHEN EXISTS (
          SELECT 1 FROM parts WHERE parts.id=deliveries.id AND parts.state='confirmed'
          ) THEN 'unknown' ELSE 'expired' END,payload=NULL WHERE state='queued' AND expires<=?""", (at,))
        self.db.execute("UPDATE inbound SET state='expired',payload=NULL WHERE state='observed' AND created<=?",
                        (at - TTL_MS,))
        self.db.commit()

    def next_delivery(self, at: int | None = None) -> dict | None:
        self.expire(now_ms() if at is None else at)
        row = self.db.execute("SELECT payload FROM deliveries WHERE state='queued' ORDER BY created,rowid LIMIT 1").fetchone()
        return json.loads(row[0]) if row else None

    def set_delivery(self, identity: str, state: str) -> None:
        with self.db:
            self.db.execute("UPDATE deliveries SET state=?,payload=CASE WHEN ? IN ('queued','sending') THEN payload ELSE NULL END WHERE id=?",
                            (state, state, identity))

    def cancel_delivery(self, identity: str) -> str:
        with self.db:
            self.db.execute("""UPDATE deliveries SET state=CASE WHEN EXISTS (
              SELECT 1 FROM parts WHERE parts.id=deliveries.id AND parts.state='confirmed'
              ) THEN 'unknown' ELSE 'failed' END,payload=NULL WHERE id=? AND state='queued'""", (identity,))
        row = self.db.execute("SELECT state FROM deliveries WHERE id=?", (identity,)).fetchone()
        return row[0] if row else "failed"

    def part_state(self, identity: str, part: int) -> str | None:
        row = self.db.execute("SELECT state FROM parts WHERE id=? AND part=?", (identity, part)).fetchone()
        return row[0] if row else None

    def set_part(self, identity: str, part: int, state: str) -> None:
        with self.db:
            self.db.execute("INSERT INTO parts VALUES (?,?,?) ON CONFLICT(id,part) DO UPDATE SET state=excluded.state",
                            (identity, part, state))

    def status(self) -> dict:
        return {"inbound": dict(self.db.execute("SELECT state,count(*) FROM inbound GROUP BY state")),
                "outbound": dict(self.db.execute("SELECT state,count(*) FROM deliveries GROUP BY state"))}

    def prune(self, at: int | None = None) -> None:
        at = now_ms() if at is None else at
        self.expire(at)
        with self.db:
            self.db.execute("DELETE FROM inbound WHERE created<? AND state!='observed'", (at - 7 * 86400000,))
            self.db.execute("DELETE FROM deliveries WHERE created<? AND state NOT IN ('queued','sending')", (at - 7 * 86400000,))
            self.db.execute("DELETE FROM parts WHERE id NOT IN (SELECT id FROM deliveries)")
        pages = self.db.execute("PRAGMA page_count").fetchone()[0]
        size = self.db.execute("PRAGMA page_size").fetchone()[0]
        if pages * size > 20 * 1024 * 1024:
            raise BridgeError("state_store_limit")
