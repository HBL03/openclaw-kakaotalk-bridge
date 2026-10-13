import threading
from pathlib import Path
from .delivery_queue import DeliveryWorker
from .models import BridgeError, UnsafeDesktop
from .monitor import Monitor
from .protocol import TTL_MS, now_ms
from .state_store import StateStore


class EchoProbe:
    """User-started P0 loop. No model or Gateway is called."""
    def __init__(self, directory: Path, adapter_factory, poll_seconds: float = 5):
        self.directory, self.adapter_factory, self.poll_seconds = directory, adapter_factory, poll_seconds
        self.stop = threading.Event()
        self.status = {"state": "starting", "confirmed": 0, "counts": {}}

    def snapshot(self) -> dict:
        return dict(self.status)

    def run(self) -> None:
        store = StateStore(self.directory / "p0.sqlite3")
        try:
            adapter = self.adapter_factory()
        except Exception:
            self.status["state"] = "adapter_start_failed"
            store.close()
            return
        monitor = Monitor(adapter, store)
        delivery = DeliveryWorker(store, adapter)
        try:
            while not self.stop.is_set():
                try:
                    store.prune()
                    errors = monitor.poll()
                    self.status["state"] = errors[-1] if errors else "watching"
                    for event in store.pending_inbound():
                        stamp = now_ms()
                        store.admit_delivery({"v": 1, "type": "outbound.message", "roomId": "self",
                                              "deliveryId": event["eventId"], "kind": "reply",
                                              "createdAt": stamp, "expiresAt": stamp + TTL_MS,
                                              "text": "P0 echo: " + event["text"]})
                        store.inbound_ack(event["eventId"], "accepted")
                    if result := delivery.deliver_one():
                        self.status["state"] = result[1]
                        if result[1] == "confirmed":
                            self.status["confirmed"] += 1
                    self.status["counts"] = store.status()
                except UnsafeDesktop as error:
                    self.status["state"] = str(error)
                    if str(error) == "desktop_locked":
                        monitor.cursor.reset()
                except BridgeError as error:
                    self.status["state"] = str(error)
                    break
                except Exception:
                    self.status["state"] = "adapter_failed"
                    break
                self.stop.wait(self.poll_seconds)
        finally:
            store.close()
