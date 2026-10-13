from .models import UiAdapter, UnsafeDesktop
from .protocol import chunks, now_ms
from .state_store import StateStore


class DeliveryWorker:
    def __init__(self, store: StateStore, adapter: UiAdapter):
        self.store, self.adapter = store, adapter

    def deliver_one(self) -> tuple[str, str] | None:
        event = self.store.next_delivery()
        if not event:
            return None
        identity = event["deliveryId"]
        parts = chunks(event["text"], event["kind"])
        for index, text in enumerate(parts):
            previous = self.store.part_state(identity, index)
            if previous == "confirmed":
                continue
            if previous in ("sending", "unknown"):
                self.store.set_delivery(identity, "unknown")
                return identity, "unknown"
            if event["expiresAt"] <= now_ms():
                state = "unknown" if index else "expired"
                self.store.set_delivery(identity, state)
                return identity, state
            try:
                self.adapter.preflight()
                before = self.adapter.read_snapshot()
                self.adapter.preflight()
            except UnsafeDesktop:
                self.store.set_delivery(identity, "queued")
                return None
            except Exception:
                state = "unknown" if index else "failed"
                self.store.set_delivery(identity, state)
                return identity, state
            # Commit the intent before the first operation that may send.
            self.store.set_part(identity, index, "sending")
            self.store.set_delivery(identity, "sending")
            try:
                self.adapter.send_text(text)
                confirmed = self.adapter.verify_send(text, before)
            except Exception:
                confirmed = False
            state = "confirmed" if confirmed else "unknown"
            self.store.set_part(identity, index, state)
            if not confirmed:
                self.store.set_delivery(identity, "unknown")
                return identity, "unknown"
        self.store.set_delivery(identity, "confirmed")
        return identity, "confirmed"
