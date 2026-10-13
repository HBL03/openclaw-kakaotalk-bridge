import json
import zipfile
import pytest
from kakao_local.config import BridgeConfig
from kakao_local.diagnostics import export_diagnostics, redact
from kakao_local.models import BridgeError
from kakao_local.protocol import decode, encode


@pytest.mark.parametrize("url", ["ws://0.0.0.0:29531", "ws://192.168.0.1:29531", "wss://example.com",
    "ws://user:password@127.0.0.1:1", "ws://127.0.0.1:1?token=abc"])
def test_only_exact_loopback(url):
    with pytest.raises(BridgeError):
        BridgeConfig(endpoint=url).validate()


@pytest.mark.parametrize("frame", [{"v": 2, "type": "ready"}, {"v": True, "type": "ready"},
    {"v": 1, "type": "inbound.message", "roomId": "someone", "text": "hi"},
    {"v": 1, "type": "ack", "id": "okay", "status": "invented"}])
def test_protocol_rejects_bad_frames(frame):
    with pytest.raises(BridgeError):
        decode(json.dumps(frame))


def test_unicode_roundtrip():
    frame = {"type": "inbound.message", "eventId": "test", "roomId": "self", "observedAt": 1, "text": "안녕 🙂"}
    assert decode(encode(frame))["text"] == frame["text"]


def test_diagnostic_export_allowlist(tmp_path):
    destination = tmp_path / "diagnostics.zip"
    export_diagnostics(destination, {"state": "paused", "counts": {}, "token": "private-token", "text": "private-message"})
    with zipfile.ZipFile(destination) as archive:
        assert archive.namelist() == ["diagnostics.json"]
        data = archive.read("diagnostics.json").decode()
        assert "private" not in data


def test_redaction():
    value = redact("token=secret abc " + "a" * 64 + r" C:\Users\TestPerson\data")
    assert "secret" not in value and "TestPerson" not in value and "a" * 64 not in value
