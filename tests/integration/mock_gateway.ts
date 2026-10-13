import { Journal } from "../../packages/openclaw-kakao-channel/src/journal.js";
import { BridgeTransport } from "../../packages/openclaw-kakao-channel/src/transport.js";

const journal = new Journal(":memory:");
let calls = 0;
const server = new BridgeTransport({ port: 0, token: "a".repeat(64), bridgeId: "test-bridge", journal,
  onInbound: async event => {
    calls++;
    await server.deliver(`reply:${event.eventId}`, `echo ${calls}: ${event.text}`, "reply");
  },
});
await server.start();
process.stdout.write(JSON.stringify({ port: server.port }) + "\n");
setTimeout(async () => { await server.close(); process.exit(0); }, 30_000).unref();
