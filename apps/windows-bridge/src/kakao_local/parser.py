"""Parse text copied from the KakaoTalk message list, never its private DB."""
import re
from .models import BridgeError, Message, Snapshot

_DATE = re.compile(r"^-*\s*(\d{4})년\s*(\d{1,2})월\s*(\d{1,2})일(?:\s+\S+요일)?\s*-*$")
_HEADER = re.compile(r"^\[(.+?)\]\s*\[대화상대\s*(\d+)명?\]")
_MESSAGE = re.compile(r"^\[(.+?)\]\s*\[(오전|오후|AM|PM)\s*(\d{1,2}):(\d{2})\] ?(.*)$")


def parse_snapshot(raw: str) -> Snapshot:
    messages: list[Message] = []
    title = None
    members = None
    date = "unknown"
    current: list[str] | None = None

    def flush() -> None:
        nonlocal current
        if current is not None:
            messages.append(Message(*current[:3], current[3].rstrip("\n")))
            current = None

    for line in raw.replace("\r\n", "\n").split("\n"):
        if match := _DATE.fullmatch(line.strip()):
            flush()
            from datetime import date as Date
            try:
                date = Date(*map(int, match.groups())).isoformat()
            except ValueError as exc:
                raise BridgeError("invalid_date") from exc
        elif match := _HEADER.match(line):
            if current is not None or messages:
                raise BridgeError("ambiguous_header")
            title, members = match[1], int(match[2])
        elif match := _MESSAGE.fullmatch(line):
            flush()
            hour, minute = int(match[3]), int(match[4])
            if not (1 <= hour <= 12 and 0 <= minute < 60):
                raise BridgeError("invalid_time")
            hour = hour % 12 + (12 if match[2] in ("오후", "PM") else 0)
            current = [match[1], date, f"{hour:02}:{minute:02}", match[5]]
        elif current is not None:
            current[3] += "\n" + line
        elif line.strip():
            # An unexpected format must not silently become an empty baseline.
            raise BridgeError("unsupported_clipboard_format")
    flush()
    return Snapshot(tuple(messages), title, members)


def command_body(text: str) -> str | None:
    if not re.match(r"^!ai(?:\s|$)", text):
        return None
    body = text[3:].strip()
    if len(body) > 4000:
        raise BridgeError("command_too_long")
    return body
