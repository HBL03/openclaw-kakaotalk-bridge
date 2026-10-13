import json
import threading
import time
from pathlib import Path
from websockets.sync.client import connect
from .config import BridgeConfig
from .delivery_queue import DeliveryWorker
from .diagnostics import setup_logging
from .models import BridgeError, UiAdapter, UnsafeDesktop
from .monitor import Monitor
from .protocol import MAX_FRAME_BYTES, ack, decode, encode, now_ms
from .state_store import StateStore


class BridgeEngine:
    def __init__(self, config: BridgeConfig, directory: Path, token: str, adapter_factory):
        self.config, self.directory, self.token = config, directory, token
        self.adapter_factory = adapter_factory
        self.stop = threading.Event()
        self.paused = threading.Event()
        self.paused.set()
        self.status = {"state": "paused", "counts": {}}

    def run(self) -> None:
        logger = setup_logging(self.directory)
        store = StateStore(self.directory / "state.sqlite3")
        try:
            adapter: UiAdapter = self.adapter_factory()
        except Exception:
            self.status["state"] = "adapter_start_failed"
            store.close()
            return
        monitor = Monitor(adapter, store)
        delivery = DeliveryWorker(store, adapter)
        failures = 0
        try:
            while not self.stop.is_set():
                try:
                    with connect(self.config.endpoint, max_size=MAX_FRAME_BYTES, open_timeout=5,
                                 close_timeout=2, proxy=None) as ws:
                        ws.send(encode({"type": "hello", "bridgeId": self.config.bridge_id, "token": self.token}))
                        if decode(ws.recv(timeout=5))["type"] != "ready":
                            raise BridgeError("pairing_failed")
                        failures = 0
                        monitor.cursor.reset()
                        last_poll = 0.0
                        last_prune = 0.0
                        sent_at: dict[str, float] = {}
                        was_paused = True
                        while not self.stop.is_set():
                            try:
                                frame = decode(ws.recv(timeout=0.1))
                                if frame["type"] == "outbound.message":
                                    state = store.admit_delivery(frame)
                                    ws.send(encode(ack(frame["deliveryId"], state)))
                                elif frame["type"] == "ack":
                                    store.inbound_ack(frame["id"], frame["status"])
                                    sent_at.pop(frame["id"], None)
                                elif frame["type"] == "cancel.delivery":
                                    ws.send(encode(ack(frame["id"], store.cancel_delivery(frame["id"]))))
                            except TimeoutError:
                                pass
                            if self.paused.is_set():
                                self.status["state"] = "paused"
                                was_paused = True
                            else:
                                if was_paused:
                                    monitor.cursor.reset()
                                    was_paused = False
                                if time.monotonic() - last_poll >= self.config.poll_seconds:
                                    last_poll = time.monotonic()
                                    try:
                                        errors = monitor.poll()
                                        self.status["state"] = errors[-1] if errors else "watching"
                                        if result := delivery.deliver_one():
                                            ws.send(encode(ack(*result)))
                                    except UnsafeDesktop as error:
                                        self.status["state"] = str(error)
                                        if str(error) == "desktop_locked":
                                            monitor.cursor.reset()
                                    except BridgeError as error:
                                        self.status["state"] = str(error)
                                        self.paused.set()
                                        logger.warning("monitor_stopped code=%s", str(error))
                                for event in store.pending_inbound():
                                    identity = event["eventId"]
                                    if time.monotonic() - sent_at.get(identity, -100) > 15:
                                        ws.send(encode(event))
                                        sent_at[identity] = time.monotonic()
                            store.expire(now_ms())
                            self.status["counts"] = store.status()
                            if time.monotonic() - last_prune > 60:
                                store.prune()
                                last_prune = time.monotonic()
                except Exception as error:
                    # Exception bodies may contain a token, endpoint, or message: never log them.
                    failures += 1
                    self.status["state"] = "connection_failed"
                    logger.warning("connection_failed type=%s", type(error).__name__)
                    if failures >= 5:
                        self.paused.set()
                    self.stop.wait(min(30, 2 ** min(failures, 5)))
        finally:
            store.close()
            self.status["state"] = "stopped"

    def snapshot(self) -> dict:
        return json.loads(json.dumps(self.status))
