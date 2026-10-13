from .models import Message, Snapshot


class MockAdapter:
    """In-memory self-room used by tests and --demo; never touches KakaoTalk."""
    def __init__(self):
        self.messages: list[Message] = []
        self.sent: list[str] = []

    def append(self, text: str) -> None:
        self.messages.append(Message("self", "2026-10-13", "12:00", text))

    def preflight(self) -> None:
        pass

    def read_snapshot(self) -> Snapshot:
        return Snapshot(tuple(self.messages), "self", 1)

    def send_text(self, text: str) -> None:
        self.sent.append(text)
        self.append(text)

    def verify_send(self, text: str, before: Snapshot) -> bool:
        return any(msg.text == text for msg in self.messages[len(before.messages):])
