import { join } from "node:path";
import { buildChannelOutboundSessionRoute, createChatChannelPlugin,
  type PluginRuntime, type OpenClawConfig } from "openclaw/plugin-sdk/channel-core";
import { buildChannelInboundEventContext } from "openclaw/plugin-sdk/channel-inbound";
import { defineChannelMessageAdapter, type ChannelMessageSendTextContext,
  type ChannelMessageSendResult } from "openclaw/plugin-sdk/channel-outbound";
import { PlatformMessageNotDispatchedError } from "openclaw/plugin-sdk/error-runtime";
import { resolveAccount, loadToken, schema, type Account } from "./config.js";
import { Journal } from "./journal.js";
import { BridgeTransport } from "./transport.js";
import { type Inbound, target } from "./protocol.js";

let runtime: PluginRuntime;
let transport: BridgeTransport | undefined;
export function setRuntime(value: PluginRuntime): void { runtime = value; }
export const sessionKey = (agentId: string): string => `agent:${agentId}:kakao-local:default:direct:self`;

async function send(ctx: ChannelMessageSendTextContext): Promise<ChannelMessageSendResult> {
  target(ctx.to);
  if (ctx.accountId && ctx.accountId !== "default") throw new Error("unsupported_account");
  if (!transport || !ctx.deliveryQueueId) {
    throw new PlatformMessageNotDispatchedError("kakao_local_requires_durable_delivery", { cause: "missing_transport_or_intent", retryable: false });
  }
  ctx.signal?.throwIfAborted();
  await ctx.onPlatformSendDispatch?.();
  ctx.assertDirectAdapterHandoff?.();
  const id = `${ctx.deliveryQueueId}:${ctx.deliveryPartIndex ?? 0}`;
  await transport.deliver(id, ctx.text, ctx.replyToId ? "reply" : "notification", ctx.signal);
  // Kakao UI has no provider message ID. Do not invent one, or claim mobile/device delivery.
  return { receipt: { platformMessageIds: [], parts: [], sentAt: Date.now(), raw: [
    { channel: "kakao-local", target: { kind: "room", id: "self" }, meta: { localDeliveryId: id, evidence: "ui_observed" } },
  ] }, target: { kind: "room", id: "self" } };
}

export async function dispatchInbound(cfg: OpenClawConfig, event: Inbound): Promise<void> {
  const route = runtime.channel.routing.resolveAgentRoute({ cfg, channel: "kakao-local", accountId: "default",
    peer: { kind: "direct", id: "self" } });
  const key = sessionKey(route.agentId);
  const ctxPayload = buildChannelInboundEventContext({
    channel: "kakao-local", accountId: "default", provider: "kakao-local", surface: "kakao-local",
    messageId: event.eventId, timestamp: event.observedAt, from: "kakao-local:self",
    sender: { id: "self", name: "self", isSelf: true, isBot: false },
    conversation: { kind: "direct", id: "self", label: "나와의 채팅" },
    route: { agentId: route.agentId, routeSessionKey: key },
    reply: { to: "self", originatingTo: "self", deliveryTarget: "self", replyToId: event.eventId, sourceReplyDeliveryMode: "direct" },
    message: { rawBody: event.text, bodyForAgent: event.text, commandBody: event.text },
    access: { commands: { authorized: true } },
    channelIngress: "unsupported", // Dedicated local pairing is verified before this boundary.
  });
  await runtime.channel.inbound.dispatch({
    cfg, channel: "kakao-local", accountId: "default", route: { agentId: route.agentId, sessionKey: key },
    ctxPayload, messageId: event.eventId,
    replyOptions: { disableBlockStreaming: true },
    delivery: {
      durable: { to: "self", replyToId: event.eventId },
      preparePayload: (payload, info) => info.kind === "final" ? payload : null,
      deliver: async () => { throw new Error("kakao_local_direct_delivery_disabled"); },
    },
  });
}

export const channel = createChatChannelPlugin<Account>({
  base: {
    id: "kakao-local",
    meta: { id: "kakao-local", label: "KakaoTalk Local", selectionLabel: "KakaoTalk Local (self only)",
      docsPath: "/channels/kakao-local", blurb: "Windows self-chat bridge; local UI delivery evidence only" },
    capabilities: { chatTypes: ["direct"], media: false, reactions: false, threads: false, blockStreaming: false },
    configSchema: { schema },
    config: { listAccountIds: () => ["default"], resolveAccount, defaultAccountId: () => "default",
      isEnabled: account => account.enabled,
      isConfigured: account => Boolean(account.secretFile && account.stateDir && account.bridgeId),
      resolveAllowFrom: () => ["self"], resolveDefaultTo: () => "self",
      describeAccount: account => ({ accountId: "default", enabled: account.enabled, configured: Boolean(account.secretFile) }) },
    reload: { configPrefixes: ["channels.kakao-local"] },
    messaging: {
      normalizeTarget: raw => { try { return target(raw); } catch { return undefined; } },
      targetResolver: { looksLikeId: raw => raw === "self" || raw === "kakao-local:self", hint: "self" },
      resolveOutboundSessionRoute: params => {
        target(params.target);
        const route = buildChannelOutboundSessionRoute({ cfg: params.cfg, agentId: params.agentId,
          channel: "kakao-local", accountId: "default", peer: { kind: "direct", id: "self" },
          chatType: "direct", from: "kakao-local:self", to: "self" });
        return { ...route, sessionKey: sessionKey(params.agentId) };
      },
    },
    directory: { self: async () => ({ kind: "user", id: "self", name: "나와의 채팅" }),
      listPeers: async () => [{ kind: "user", id: "self", name: "나와의 채팅" }], listGroups: async () => [] },
    message: defineChannelMessageAdapter({ id: "kakao-local", send: { text: send },
      durableFinal: { capabilities: { text: true }, automaticUnknownSendReconciliation: false } }),
    outbound: { deliveryMode: "direct", textChunkLimit: 16000, chunkerMode: "text", chunker: null,
      sendText: async ctx => {
        const { onDeliveryResult: _legacyCallback, ...context } = ctx;
        const result = await send(context);
        return { channel: "kakao-local", messageId: "", target: result.target,
          meta: { receipt: result.receipt, evidence: "ui_observed" } };
      } },
    status: { defaultRuntime: { accountId: "default", running: false, connected: false },
      buildAccountSnapshot: ({ account, runtime: current }) => ({ ...current, accountId: "default",
        enabled: account.enabled, configured: Boolean(account.secretFile), connected: transport?.connected ?? false }) },
    gateway: {
      startAccount: async ctx => {
        const token = loadToken(ctx.account);
        const journal = new Journal(join(ctx.account.stateDir, "transport.sqlite3"));
        const owned = new BridgeTransport({ port: ctx.account.port, token,
          bridgeId: ctx.account.bridgeId, journal, onInbound: event => dispatchInbound(ctx.cfg, event),
          onStatus: connected => ctx.setStatus({ accountId: "default", running: true, connected }) });
        transport = owned;
        try {
          await owned.start();
          ctx.setStatus({ accountId: "default", running: true, connected: false });
          await new Promise<void>(resolve => {
            if (ctx.abortSignal.aborted) resolve(); else ctx.abortSignal.addEventListener("abort", () => resolve(), { once: true });
          });
        } finally {
          await owned.close();
          journal.close();
          if (transport === owned) transport = undefined;
          ctx.setStatus({ accountId: "default", running: false, connected: false });
        }
      },
    },
  },
  security: {
    dm: { channelKey: "kakao-local", resolvePolicy: () => "allowlist", resolveAllowFrom: () => ["self"] },
    dmRouting: { resolveDmScope: () => "per-account-channel-peer",
      resolveDmRoute: ({ route }) => ({ sessionKey: sessionKey(route.agentId) }) },
  },
  threading: { topLevelReplyToMode: "off" },
});
