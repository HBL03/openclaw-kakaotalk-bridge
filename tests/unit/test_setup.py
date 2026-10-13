import hashlib
import json
from pathlib import Path
import subprocess
import sys
from unittest.mock import Mock
import pytest
from kakao_local.models import BridgeError
from kakao_local.setup import install_channel


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
