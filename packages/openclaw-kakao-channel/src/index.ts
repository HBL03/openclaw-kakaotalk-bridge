import { defineChannelPluginEntry } from "openclaw/plugin-sdk/channel-core";
import { channel, setRuntime } from "./channel.js";

const entry: ReturnType<typeof defineChannelPluginEntry> = defineChannelPluginEntry({
  id: "kakao-local", name: "KakaoTalk Local", description: "Single-user Windows KakaoTalk self-chat bridge",
  plugin: channel, setRuntime,
});

export default entry;
