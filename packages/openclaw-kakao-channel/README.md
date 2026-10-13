# openclaw-kakao-channel

The `kakao-local` channel connects OpenClaw to KakaoTalk self-chat through the
paired Windows bridge. It routes chat commands to the existing agent and returns
agent replies and scheduled notifications to the same conversation.

The channel targets OpenClaw `2026.10.2` and Node 24.19.0. Only `self` and
`kakao-local:self` are valid destinations. The channel is disabled by default.

Install the reviewed local tarball with the Windows setup flow documented at
[HBL03/openclaw-kakaotalk-bridge](https://github.com/HBL03/openclaw-kakaotalk-bridge).
The host owns agent execution and durable delivery intents. This package owns
loopback authentication and the transport journal. UI confirmation is local
evidence only; it does not fabricate a provider message ID.

Example configuration (placeholders, not credentials):

```json
{
  "channels": {
    "kakao-local": {
      "enabled": true,
      "port": 29531,
      "secretFile": "/home/openclaw/.openclaw/kakao-local/pairing.secret",
      "stateDir": "/home/openclaw/.openclaw/kakao-local",
      "bridgeId": "COPY_FROM_WINDOWS_CONFIG"
    }
  }
}
```

The secret must contain 64 lowercase hexadecimal characters, have mode `0600`,
and match the Windows user's DPAPI-protected pairing secret. Never put it in a
URL or commit it to source control. Gateway restart is explicit after install.
