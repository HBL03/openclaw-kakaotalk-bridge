import argparse
import json
from pathlib import Path
from . import __version__


def main() -> None:
    parser = argparse.ArgumentParser(description="OpenClaw KakaoTalk local bridge")
    parser.add_argument("--version", action="version", version=__version__)
    parser.add_argument("--data-dir", type=Path)
    parser.add_argument("--tray", action="store_true")
    parser.add_argument("--demo", action="store_true", help="Run a synthetic echo test; does not access KakaoTalk")
    parser.add_argument("--demo-output", type=Path, help="Write synthetic result to JSON (also works in a GUI build)")
    args = parser.parse_args()
    if args.demo_output and not args.demo:
        parser.error("--demo-output requires --demo")
    if args.demo:
        from .delivery_queue import DeliveryWorker
        from .mock_adapter import MockAdapter
        from .monitor import Monitor
        from .protocol import TTL_MS, now_ms
        from .state_store import StateStore
        store = StateStore(":memory:")
        adapter = MockAdapter()
        monitor = Monitor(adapter, store)
        monitor.poll()
        adapter.append("!ai 안녕")
        monitor.poll()
        for event in store.pending_inbound():
            stamp = now_ms()
            store.admit_delivery({"v": 1, "type": "outbound.message", "roomId": "self",
                                  "deliveryId": event["eventId"], "text": "echo: " + event["text"],
                                  "kind": "reply", "createdAt": stamp, "expiresAt": stamp + TTL_MS})
            DeliveryWorker(store, adapter).deliver_one()
            store.inbound_ack(event["eventId"], "completed")
        monitor.poll()
        result = json.dumps({"mode": "synthetic", "sent": adapter.sent, "counts": store.status()}, ensure_ascii=False)
        if args.demo_output:
            args.demo_output.write_text(result, encoding="utf-8")
        else:
            print(result)
        store.close()
        return
    from .tray import run_gui
    run_gui(args.data_dir, args.tray)


if __name__ == "__main__":
    main()
