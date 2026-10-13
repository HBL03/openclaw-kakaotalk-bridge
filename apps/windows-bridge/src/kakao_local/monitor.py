from uuid import uuid4
from .dedup import SnapshotCursor
from .models import BridgeError, UiAdapter
from .parser import command_body
from .protocol import now_ms
from .state_store import StateStore


class Monitor:
    def __init__(self, adapter: UiAdapter, store: StateStore):
        self.adapter, self.store = adapter, store
        self.cursor = SnapshotCursor()

    def poll(self) -> list[str]:
        errors = []
        snapshot = self.adapter.read_snapshot()
        for message in self.cursor.observe(snapshot):
            try:
                body = command_body(message.text)
                if body is None:
                    continue
                if not body:
                    errors.append("empty_command")
                    continue
                self.store.admit_inbound({
                    "v": 1, "type": "inbound.message", "eventId": str(uuid4()),
                    "roomId": "self", "observedAt": now_ms(), "text": body,
                })
            except BridgeError as error:
                errors.append(str(error))
        return errors
