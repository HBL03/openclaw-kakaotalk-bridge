import assert from "node:assert/strict";
import { once } from "node:events";
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import test from "node:test";
import { WebSocket } from "ws";
import { Journal } from "../src/journal.js";
import { BridgeTransport } from "../src/transport.js";
import { ack, type Inbound, parseFrame, target, TTL_MS } from "../src/protocol.js";

const token = "a".repeat(64);
const event = (id = "one", text = "안녕"): Inbound => ({ v: 1, type: "inbound.message", eventId: id,
  roomId: "self", observedAt: Date.now(), text });
const sleep = (ms: number) => new Promise(resolve => setTimeout(resolve, ms));
async function client(server: BridgeTransport, key = token) {
  const socket = new WebSocket(`ws://127.0.0.1:${server.port}`);
  await once(socket, "open");
  const ready = once(socket, key === token ? "message" : "close");
  socket.send(JSON.stringify({ v: 1, type: "hello", bridgeId: "test-bridge", token: key }));
  await ready;
  return socket;
}
async function harness(onInbound: (input: Inbound) => Promise<void> = async () => {}) {
  const journal = new Journal(":memory:");
  const server = new BridgeTransport({ port: 0, token, bridgeId: "test-bridge", journal, onInbound });
  await server.start();
  return { journal, server, close: async () => { await server.close(); journal.close(); } };
}

test("pairing rejects wrong secret and non-self targets", async () => {
  const h = await harness();
  try {
    const socket = await client(h.server, "b".repeat(64));
    assert.equal(socket.readyState, WebSocket.CLOSED);
    assert.equal(h.server.connected, false);
    assert.throws(() => target("someone"));
    assert.throws(() => parseFrame(JSON.stringify({ ...event(), roomId: "group" })));
  } finally { await h.close(); }
});

test("duplicate inbound frames run the agent once; repeated text with a fresh id runs again", async () => {
  let calls = 0;
  const h = await harness(async () => { calls++; });
  try {
    const socket = await client(h.server);
    const first = event();
    socket.send(JSON.stringify(first));
    socket.send(JSON.stringify(first));
    socket.send(JSON.stringify(event("two")));
    await sleep(100);
    assert.equal(calls, 2);
  } finally { await h.close(); }
});

test("confirmed delivery is replay-safe, without renewing TTL", async () => {
  const h = await harness();
  try {
    const socket = await client(h.server);
    let sends = 0;
    socket.on("message", raw => {
      const message = parseFrame(raw.toString());
      if (message.type === "outbound.message") { sends++; socket.send(JSON.stringify(ack(message.deliveryId, "confirmed"))); }
    });
    await h.server.deliver("result", "reply", "reply");
    const expiry = h.journal.get("result")!.expires;
    await h.server.deliver("result", "reply", "reply");
    assert.equal(sends, 1);
    assert.equal(h.journal.get("result")!.expires, expiry);
    assert.equal(h.journal.get("result")!.payload, null);
  } finally { await h.close(); }
});

test("offline delivery waits for reconnect then uses the original id", async () => {
  const h = await harness();
  try {
    const delivered = h.server.deliver("offline", "reminder", "notification");
    const socket = new WebSocket(`ws://127.0.0.1:${h.server.port}`);
    socket.on("message", raw => {
      const message = parseFrame(raw.toString());
      if (message.type === "outbound.message") socket.send(JSON.stringify(ack(message.deliveryId, "confirmed")));
    });
    await once(socket, "open");
    socket.send(JSON.stringify({ v: 1, type: "hello", bridgeId: "test-bridge", token }));
    await delivered;
    assert.equal(h.journal.get("offline")!.state, "confirmed");
  } finally { await h.close(); }
});

test("unknown sends are never replayed", async () => {
  const h = await harness();
  try {
    const socket = await client(h.server);
    let sends = 0;
    socket.on("message", raw => {
      const message = parseFrame(raw.toString());
      if (message.type === "outbound.message") { sends++; socket.send(JSON.stringify(ack(message.deliveryId, "unknown"))); }
    });
    await assert.rejects(h.server.deliver("unknown", "reply", "reply"), /unknown/);
    await assert.rejects(h.server.deliver("unknown", "reply", "reply"), /unknown/);
    assert.equal(sends, 1);
  } finally { await h.close(); }
});

test("cancellation retires an offline intent", async () => {
  const h = await harness();
  try {
    const control = new AbortController();
    const pending = h.server.deliver("cancel", "reply", "reply", control.signal);
    control.abort();
    await assert.rejects(pending, /failed/);
    assert.equal(h.journal.get("cancel")!.payload, null);
  } finally { await h.close(); }
});

test("inbound queue is bounded and IDs cannot change payload", () => {
  const db = new Journal(":memory:");
  try {
    const first = event();
    assert.equal(db.admit(first), "accepted");
    assert.throws(() => db.admit({ ...first, text: "different" }), /collision/);
    for (let i = 0; i < 4; i++) db.admit(event(String(i)));
    assert.equal(db.admit(event("overflow")), "rejected");
    assert.equal(db.admit({ ...event("old"), observedAt: 1 }), "expired");
  } finally { db.close(); }
});

test("restart quarantines uncertain agent turns and dispatched sends", () => {
  const directory = mkdtempSync(join(tmpdir(), "kakao-local-test-"));
  const path = join(directory, "state.sqlite3");
  let db = new Journal(path);
  const first = event();
  db.admit(first);
  db.inboundState(first.eventId, "processing");
  db.outbound("send", "text", "reply");
  db.finish("send", "sending");
  db.close();
  db = new Journal(path);
  try {
    assert.equal(db.admit(first), "unknown");
    assert.equal(db.next(), undefined);
    assert.equal(db.get("send")!.state, "unknown");
    assert.equal(db.get("send")!.payload, null);
  } finally { db.close(); rmSync(directory, { recursive: true }); }
});

test("expiry is based on first admission and does not reset on retries", () => {
  const db = new Journal(":memory:");
  try {
    const start = Date.now();
    const row = db.outbound("ttl", "notice", "notification", start);
    assert.equal(db.outbound("ttl", "notice", "notification", start + 100).expires, row.expires);
    db.prune(start + TTL_MS);
    assert.equal(db.get("ttl")!.state, "expired");
    assert.equal(db.get("ttl")!.payload, null);
  } finally { db.close(); }
});

test("outbound validates text before retaining a new intent", () => {
  const db = new Journal(":memory:");
  try {
    assert.throws(() => db.outbound("bad", "x".repeat(16001), "reply"), /invalid_text/);
    assert.equal(db.get("bad"), undefined);
    assert.throws(() => db.outbound("bad", "\0", "reply"), /invalid_text/);
  } finally { db.close(); }
});
