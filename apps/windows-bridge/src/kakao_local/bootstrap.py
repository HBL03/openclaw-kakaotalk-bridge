"""Noninteractive install/doctor entry points; never inspect or operate KakaoTalk."""
import hashlib
import time
from pathlib import Path
from urllib.parse import urlparse
from websockets.sync.client import connect
from .config import BridgeConfig, load_secret, save_secret
from .models import BridgeError
from .protocol import decode, encode, MAX_FRAME_BYTES
from .setup import install_channel, gateway_action


def probe_connection(config: BridgeConfig, token: str) -> bool:
    # A probe authenticates without claiming the UI connection or dispatching work.
    try:
        with connect(config.endpoint, max_size=MAX_FRAME_BYTES, open_timeout=3,
                     close_timeout=1, proxy=None) as ws:
            ws.send(encode({"type": "probe", "bridgeId": config.bridge_id, "token": token}))
            return decode(ws.recv(timeout=3))["type"] == "ready"
    except Exception:
        return False


def doctor(directory: Path) -> dict:
    if not (directory / "config.json").is_file() or not (directory / "pairing.dpapi").is_file():
        return {"ok": False, "code": "not_installed", "next": "run_install"}
    config = BridgeConfig.load(directory)
    connected = probe_connection(config, load_secret(directory))
    selected = bool(config.confirmed_self and config.room_title and config.self_sender)
    return {"ok": connected, "code": "connected" if connected else "gateway_unreachable",
            "selfConfigured": selected, "kakaoVerified": False,
            "next": "test_chat" if connected and selected else "confirm_self_in_settings" if connected else "check_gateway"}


def install(directory: Path, archive: Path, distro: str = "OpenClawGateway",
            restart: bool = False) -> dict:
    sidecar = archive.with_suffix(archive.suffix + ".sha256")
    if not archive.is_file() or not sidecar.is_file():
        raise BridgeError("package_or_checksum_missing")
    fields = sidecar.read_text(encoding="utf-8-sig").split()
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    if not fields or fields[0] != digest:
        raise BridgeError("archive_hash_mismatch")
    # Read-only environment check before creating pairing state or touching Gateway config.
    gateway_action("check", distro)
    config = BridgeConfig.load(directory)
    config.save(directory)
    # Save before remote mutation: retry after a process crash reuses the same key.
    token = load_secret(directory) if (directory / "pairing.dpapi").exists() else save_secret(directory)
    result = install_channel(archive, digest, token, config.bridge_id, distro, urlparse(config.endpoint).port)
    if restart and (result.get("gatewayRestartRequired") or not probe_connection(config, token)):
        gateway_action("restart", distro)
        for _ in range(10):
            if probe_connection(config, token):
                break
            time.sleep(1)
    checked = doctor(directory)
    return {**checked, "install": result["status"], "gatewayRestartRequired": not checked["ok"]}


def run_cli(args, directory: Path) -> int:
    lock = None
    try:
        if args.doctor:
            result = doctor(directory)
        else:
            if args.package is None:
                raise BridgeError("package_required")
            from PySide6.QtCore import QLockFile
            directory.mkdir(parents=True, exist_ok=True)
            lock = QLockFile(str(directory / "bridge.lock"))
            if not lock.tryLock(0):
                raise BridgeError("close_bridge_before_install")
            result = install(directory, args.package, args.distro, args.restart_gateway)
    except Exception as error:
        code = str(error) if isinstance(error, BridgeError) else "setup_failed"
        result = {"ok": False, "code": code, "next": "check_installation_guide"}
    finally:
        if lock is not None:
            lock.unlock()
    import json
    text = json.dumps(result, ensure_ascii=True, separators=(",", ":"))
    if args.result_file:
        args.result_file.write_text(text, encoding="utf-8")
    else:
        print(text)
    return 0 if result["ok"] else 1
