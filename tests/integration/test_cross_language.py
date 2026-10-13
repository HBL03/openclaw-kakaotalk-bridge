import json
import os
from pathlib import Path
import shutil
import subprocess
import threading
import time
from kakao_local.config import BridgeConfig
from kakao_local.local_transport import BridgeEngine
from kakao_local.mock_adapter import MockAdapter


def test_python_engine_to_typescript_gateway(tmp_path):
    root = Path(__file__).resolve().parents[2]
    local = root / ".cache/node-v24.19.0-win-x64/node.exe"
    node = os.environ.get("KAKAO_TEST_NODE") or (str(local) if local.exists() else shutil.which("node"))
    assert node, "Node 24.19.0 is required for integration tests"
    process = subprocess.Popen([node, "--import", "tsx", "tests/integration/mock_gateway.ts"], cwd=root,
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8")
    engine = None
    worker = None
    try:
        ready = json.loads(process.stdout.readline())
        adapter = MockAdapter()
        config = BridgeConfig(endpoint=f"ws://127.0.0.1:{ready['port']}", bridge_id="test-bridge")
        engine = BridgeEngine(config, tmp_path, "a" * 64, lambda: adapter)
        engine.paused.clear()
        worker = threading.Thread(target=engine.run)
        worker.start()
        deadline = time.monotonic() + 20
        while engine.snapshot()["state"] != "watching" and time.monotonic() < deadline:
            time.sleep(0.05)
        assert engine.snapshot()["state"] == "watching"
        adapter.append("!ai 한국어 왕복 🙂")
        while not adapter.sent and time.monotonic() < deadline:
            time.sleep(0.05)
        assert adapter.sent == ["[OpenClaw]\necho 1: 한국어 왕복 🙂"]
        time.sleep(0.3)
        assert engine.snapshot()["counts"]["outbound"] == {"confirmed": 1}
    finally:
        if engine:
            engine.stop.set()
        if worker:
            worker.join(6)
        process.terminate()
        process.communicate(timeout=10)
        assert worker is None or not worker.is_alive()
