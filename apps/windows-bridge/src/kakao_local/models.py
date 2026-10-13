from dataclasses import dataclass
from enum import StrEnum
from hashlib import sha256
from typing import Protocol


class BridgeError(Exception):
    """An error code safe to show in diagnostics (never message text)."""


class UnsafeDesktop(BridgeError):
    pass


class AmbiguousSnapshot(BridgeError):
    pass


class DeliveryState(StrEnum):
    QUEUED = "queued"
    SENDING = "sending"
    CONFIRMED = "confirmed"
    UNKNOWN = "unknown"
    FAILED = "failed"
    EXPIRED = "expired"


@dataclass(frozen=True)
class Message:
    sender: str
    date: str
    time: str
    text: str

    @property
    def fingerprint(self) -> str:
        import json
        return sha256(json.dumps(
            [self.sender, self.date, self.time, self.text], ensure_ascii=False
        ).encode()).hexdigest()


@dataclass(frozen=True)
class Snapshot:
    messages: tuple[Message, ...]
    room_title: str | None = None
    member_count: int | None = None


class UiAdapter(Protocol):
    def read_snapshot(self) -> Snapshot: ...
    def preflight(self) -> None: ...
    def send_text(self, text: str) -> None: ...
    def verify_send(self, text: str, before: Snapshot) -> bool: ...
