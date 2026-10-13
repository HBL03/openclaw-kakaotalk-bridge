import hashlib
import json
from pathlib import Path
import subprocess
import sys
from unittest.mock import Mock
import pytest
from kakao_local.models import BridgeError
from kakao_local.setup import install_channel


def test_managed_install_is_repeatable_and_preserves_agent_settings(tmp_path, monkeypatch, capsys):
    import base64
    import io
    from kakao_local.setup import _LINUX_SETUP
    base = tmp_path / ".openclaw"
    base.mkdir()
    config = base / "openclaw.json"
    original = {"agents": {"defaults": {"model": "existing-model"}}, "tools": {"deny": ["exec"]}}
    config.write_text(json.dumps(original))
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    calls = []

    def run(args, **kwargs):
        calls.append(args)
        if "--version" in args:
            return subprocess.CompletedProcess(args, 0, "OpenClaw 2026.10.2", "")
        return subprocess.CompletedProcess(args, 0, "", "")

    monkeypatch.setattr(subprocess, "run", run)
    archive = b"test archive"
    request = {"archive": base64.b64encode(archive).decode(), "sha256": hashlib.sha256(archive).hexdigest(),
               "token": "a" * 64, "bridgeId": "test", "port": 29531}
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(request)))
    exec(_LINUX_SETUP, {})
    assert json.loads(capsys.readouterr().out)["status"] == "installed"
    installed = config.read_bytes()
    parsed = json.loads(installed)
    assert parsed["agents"] == original["agents"] and parsed["tools"] == original["tools"]
    assert parsed["channels"]["kakao-local"]["dmHistoryLimit"] == 12
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(request)))
    with pytest.raises(SystemExit) as stopped:
        exec(_LINUX_SETUP, {})
    assert stopped.value.code == 0
    assert json.loads(capsys.readouterr().out)["status"] == "already_installed"
    assert config.read_bytes() == installed
    assert sum("plugins" in args for args in calls) == 1
    request["token"] = "b" * 64
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(request)))
    with pytest.raises(AssertionError, match="pairing_conflict"):
        exec(_LINUX_SETUP, {})
    assert config.read_bytes() == installed


def test_bootstrap_failure_reuses_saved_pairing_on_retry(tmp_path, monkeypatch):
    from kakao_local import bootstrap
    archive = tmp_path / "channel.tgz"
    archive.write_bytes(b"test")
    archive.with_suffix(".tgz.sha256").write_text(hashlib.sha256(b"test").hexdigest())
    directory = tmp_path / "settings"
    monkeypatch.setattr(bootstrap, "gateway_action", Mock())

    def save(directory):
        (directory / "pairing.dpapi").write_bytes(b"fake encrypted secret")
        return "a" * 64

    saved = Mock(side_effect=save)
    monkeypatch.setattr(bootstrap, "save_secret", saved)
    monkeypatch.setattr(bootstrap, "load_secret", lambda _: "a" * 64)
    remote = Mock(side_effect=[BridgeError("interrupted"), {"status": "already_installed"}])
    monkeypatch.setattr(bootstrap, "install_channel", remote)
    monkeypatch.setattr(bootstrap, "doctor", lambda _: {"ok": True})
    with pytest.raises(BridgeError, match="interrupted"):
        bootstrap.install(directory, archive)
    first = remote.call_args.args
    assert bootstrap.install(directory, archive)["ok"]
    assert remote.call_args.args == first
    saved.assert_called_once()


def test_doctor_is_read_only_and_cli_masks_unexpected_errors(tmp_path, capsys, monkeypatch):
    from types import SimpleNamespace
    from kakao_local import bootstrap
    assert bootstrap.doctor(tmp_path)["code"] == "not_installed"
    assert not list(tmp_path.iterdir())
    monkeypatch.setattr(bootstrap, "doctor", Mock(side_effect=RuntimeError("secret-value")))
    args = SimpleNamespace(doctor=True, result_file=None)
    assert bootstrap.run_cli(args, tmp_path) == 1
    output = capsys.readouterr().out
    assert "secret-value" not in output
    assert json.loads(output)["code"] == "setup_failed"


def test_probe_uses_a_separate_authenticated_frame_without_ui():
    import threading
    from websockets.sync.server import serve
    from kakao_local.bootstrap import probe_connection
    from kakao_local.config import BridgeConfig
    from kakao_local.protocol import decode, encode
    frames = []

    def handle(ws):
        frames.append(decode(ws.recv(timeout=3)))
        ws.send(encode({"type": "ready"}))

    with serve(handle, "127.0.0.1", 0) as server:
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            config = BridgeConfig(endpoint=f"ws://127.0.0.1:{server.socket.getsockname()[1]}", bridge_id="test")
            assert probe_connection(config, "a" * 64)
        finally:
            server.shutdown()
            thread.join(timeout=5)
    assert frames == [{"v": 1, "type": "probe", "bridgeId": "test", "token": "a" * 64}]


def test_package_hash_is_checked_before_wsl_is_called(tmp_path, monkeypatch):
    package = tmp_path / "test.tgz"
    package.write_bytes(b"synthetic package")
    run = Mock()
    monkeypatch.setattr(subprocess, "run", run)
    with pytest.raises(BridgeError, match="hash_mismatch"):
        install_channel(package, "incorrect", "a" * 64, "test")
    run.assert_not_called()


def test_setup_uses_stdin_and_does_not_expose_cli_output(tmp_path, monkeypatch):
    package = tmp_path / "test.tgz"
    package.write_bytes(b"synthetic package")
    digest = hashlib.sha256(package.read_bytes()).hexdigest()
    run = Mock(return_value=subprocess.CompletedProcess([], 1, "sensitive stdout", "sensitive stderr"))
    monkeypatch.setattr(subprocess, "run", run)
    with pytest.raises(BridgeError) as caught:
        install_channel(package, digest, "a" * 64, "test")
    assert "sensitive" not in str(caught.value)
    assert "a" * 64 not in " ".join(run.call_args.args[0])
    request = json.loads(run.call_args.kwargs["input"])
    assert request["sha256"] == digest and request["bridgeId"] == "test"
    assert "--user" in run.call_args.args[0]


@pytest.mark.skipif(sys.platform != "win32", reason="Windows DPAPI")
def test_secret_is_not_stored_as_plaintext(tmp_path: Path):
    from kakao_local.config import load_secret, save_secret
    token = "b" * 64
    save_secret(tmp_path, token)
    assert token.encode() not in (tmp_path / "pairing.dpapi").read_bytes()
    assert load_secret(tmp_path) == token


@pytest.mark.skipif(sys.platform != "win32", reason="Windows Qt app")
def test_gui_starts_paused_and_save_autostart_is_explicit(tmp_path, monkeypatch):
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication
    from kakao_local import tray
    app = QApplication.instance() or QApplication([])
    startup = Mock()
    monkeypatch.setattr(tray, "set_autostart", startup)
    window = tray.BridgeWindow(tmp_path)
    try:
        assert window.engine is None
        assert not window.autostart.isChecked()
        startup.assert_not_called()
        assert window.save()
        startup.assert_called_once_with(False)
        assert not json.loads((tmp_path / "config.json").read_text())["confirmed_self"]
    finally:
        window.timer.stop()
        window.tray.hide()
        window.hide()
        window.deleteLater()
        app.processEvents()
