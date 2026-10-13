import assert from "node:assert/strict";
import test from "node:test";
import { once } from "node:events";
import { mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { createServer } from "node:net";
import { WebSocket } from "ws";
import type { PluginRuntime } from "openclaw/plugin-sdk/channel-core";
import entry from "../src/index.js";
import { channel, dispatchInbound, sessionKey, setRuntime } from "../src/channel.js";
import { resolveAccount } from "../src/config.js";
import { ack, parseFrame } from "../src/protocol.js";

test("SDK entry loads with a self-only channel and preserves configured agent routing", async () => {
  assert.equal(entry.id, "kakao-local");
  assert.deepEqual(channel.capabilities.chatTypes, ["direct"]);
  const calls: Record<string, unknown>[] = [];
  setRuntime({ channel: {
    routing: { resolveAgentRoute: () => ({ agentId: "existing-agent" }) },
    inbound: { dispatch: async (params: Record<string, unknown>) => { calls.push(params); } },
  } } as unknown as PluginRuntime);
  await dispatchInbound({}, { v: 1, type: "inbound.message", eventId: "event", roomId: "self",
    text: "10분 뒤 알려줘", observedAt: Date.now() });
  const ctx = calls[0]!.ctxPayload as Record<string, unknown>;
  assert.equal(ctx.SessionKey, sessionKey("existing-agent"));
  assert.equal(ctx.Provider, "kakao-local");
  assert.equal(ctx.OriginatingTo, "self");
  assert.equal(ctx.BodyForAgent, "10분 뒤 알려줘");
  assert.equal(ctx.CommandAuthorized, true);
  assert.deepEqual((calls[0]!.delivery as { durable: object }).durable, { to: "self", replyToId: "event" });
  assert.equal((calls[0]!.cfg as any).channels["kakao-local"].dmHistoryLimit, 12);
  assert.equal((calls[0]!.replyOptions as any).promptCacheKey, sessionKey("existing-agent"));
});

test("outbound calls without durable custody fail before sending", async () => {
  await assert.rejects(channel.message!.send!.text!({ cfg: {}, to: "self", text: "test" }), /requires_durable/);
  await assert.rejects(channel.message!.send!.text!({ cfg: {}, to: "another-room", text: "test" }), /unsupported_room/);
});

test("one account only; channel disabled unless explicitly enabled", () => {
  assert.equal(resolveAccount({}).enabled, false);
  assert.equal(resolveAccount({}).maxRequestsPerHour, 60);
  assert.throws(() => resolveAccount({ channels: { "kakao-local": { dmHistoryLimit: 0 } } }), /invalid_usage_limits/);
  assert.throws(() => resolveAccount({}, "another"), /unsupported_account/);
  assert.equal(channel.messaging!.normalizeTarget!("kakao-local:self"), "self");
  assert.equal(channel.messaging!.normalizeTarget!("group"), undefined);
});

test("SDK account lifecycle sends durable reply and Cron-style notification over the paired transport", async () => {
  const probe = createServer();
  probe.listen(0, "127.0.0.1");
  await once(probe, "listening");
  const port = (probe.address() as { port: number }).port;
  await new Promise<void>(resolve => probe.close(() => resolve()));
  const directory = mkdtempSync(join(tmpdir(), "kakao-channel-test-"));
  const secretFile = join(directory, "secret");
  const token = "a".repeat(64);
  writeFileSync(secretFile, token, { mode: 0o600 });
  const abort = new AbortController();
  let ready!: () => void;
  const started = new Promise<void>(resolve => { ready = resolve; });
  const lifecycle = channel.gateway!.startAccount!({
    cfg: {}, accountId: "default", account: { accountId: "default", enabled: true, port,
      secretFile, stateDir: directory, bridgeId: "sdk-test" }, abortSignal: abort.signal,
    setStatus: status => { if (status.running) ready(); },
  } as Parameters<NonNullable<NonNullable<typeof channel.gateway>["startAccount"]>>[0]);
  try {
    await started;
    const socket = new WebSocket(`ws://127.0.0.1:${port}`);
    const kinds: string[] = [];
    socket.on("message", raw => {
      const frame = parseFrame(raw.toString());
      if (frame.type === "outbound.message") {
        kinds.push(frame.kind);
        socket.send(JSON.stringify(ack(frame.deliveryId, "confirmed")));
      }
    });
    await once(socket, "open");
    const paired = once(socket, "message");
    socket.send(JSON.stringify({ v: 1, type: "hello", bridgeId: "sdk-test", token }));
    await paired;
    let dispatched = 0;
    const reply = await channel.message!.send!.text!({ cfg: {}, to: "self", text: "reply",
      deliveryQueueId: "sdk-reply", replyToId: "incoming", onPlatformSendDispatch: async () => { dispatched++; } });
    const notice = await channel.message!.send!.text!({ cfg: {}, to: "kakao-local:self", text: "reminder",
      deliveryQueueId: "sdk-notice", onPlatformSendDispatch: async () => { dispatched++; } });
    assert.deepEqual(kinds, ["reply", "notification"]);
    assert.equal(dispatched, 2);
    assert.deepEqual(reply.receipt.platformMessageIds, []);
    assert.deepEqual(notice.target, { kind: "room", id: "self" });
  } finally {
    abort.abort();
    await lifecycle;
    rmSync(directory, { recursive: true });
  }
});
