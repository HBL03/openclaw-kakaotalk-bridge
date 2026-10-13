import json
import math
import re
import time
from .models import BridgeError

VERSION = 1
MAX_FRAME_BYTES = 65536
TTL_MS = 15 * 60 * 1000
_ID = re.compile(r"^[A-Za-z0-9_.:/-]{1,160}$")


def now_ms() -> int:
    return time.time_ns() // 1_000_000


def identifier(value: object) -> str:
    if not isinstance(value, str) or not _ID.fullmatch(value):
        raise BridgeError("invalid_id")
    return value


def decode(raw: str | bytes) -> dict:
    if len(raw.encode() if isinstance(raw, str) else raw) > MAX_FRAME_BYTES:
        raise BridgeError("frame_too_large")
    try:
        message = json.loads(raw)
    except (ValueError, UnicodeError) as exc:
        raise BridgeError("invalid_json") from exc
    if not isinstance(message, dict) or type(message.get("v")) is not int or message["v"] != VERSION:
        raise BridgeError("protocol_mismatch")
    kind = message.get("type")
    if kind in ("inbound.message", "outbound.message"):
        if message.get("roomId") != "self":
            raise BridgeError("unsupported_room")
        identifier(message.get("eventId" if kind == "inbound.message" else "deliveryId"))
        text = message.get("text")
        limit = 4000 if kind == "inbound.message" else 16000
        if not isinstance(text, str) or not text.strip() or len(text) > limit or "\x00" in text:
            raise BridgeError("invalid_text")
        time_fields = ("observedAt",) if kind == "inbound.message" else ("createdAt", "expiresAt")
        for field in time_fields:
            value = message.get(field)
            if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
                raise BridgeError("invalid_timestamp")
        if kind == "outbound.message":
            if message.get("kind") not in ("reply", "notification"):
                raise BridgeError("invalid_delivery_kind")
            if not 0 < message["expiresAt"] - message["createdAt"] <= TTL_MS:
                raise BridgeError("invalid_expiry")
    elif kind in ("hello", "probe"):
        identifier(message.get("bridgeId"))
        if not isinstance(message.get("token"), str) or not re.fullmatch(r"[a-f0-9]{64}", message["token"]):
            raise BridgeError("invalid_pairing")
    elif kind == "ack":
        identifier(message.get("id"))
        if message.get("status") not in (
            "accepted", "processing", "completed", "queued", "sending", "confirmed",
            "unknown", "failed", "expired", "rejected",
        ):
            raise BridgeError("invalid_ack")
    elif kind == "cancel.delivery":
        identifier(message.get("id"))
    elif kind != "ready":
        raise BridgeError("unknown_frame")
    return message


def encode(message: dict) -> str:
    return json.dumps({"v": VERSION, **message}, ensure_ascii=False, separators=(",", ":"))


def ack(identity: str, status: str) -> dict:
    return {"v": VERSION, "type": "ack", "id": identity, "status": status}


def chunks(text: str, kind: str) -> list[str]:
    prefix = "[OpenClaw 알림]" if kind == "notification" else "[OpenClaw]"
    # Every physical message has its own bot prefix, including multiline parts.
    # Prevent generated text from impersonating another clipboard message record.
    text = re.sub(r"(?m)^(?=\[|\d{4}년|---)", "\u2060", text)
    width = 1000 - len(prefix) - 20
    parts = [text[i:i + width] for i in range(0, len(text), width)]
    return [f"{prefix}{f' ({i + 1}/{len(parts)})' if len(parts) > 1 else ''}\n{part}"
            for i, part in enumerate(parts)]
