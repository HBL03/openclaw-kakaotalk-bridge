import json
import os
import secrets
from dataclasses import asdict, dataclass
from pathlib import Path
from urllib.parse import urlparse
from uuid import uuid4
from .models import BridgeError


def data_dir() -> Path:
    return Path(os.environ.get("LOCALAPPDATA", Path.home())) / "OpenClawKakaoLocal"


@dataclass
class BridgeConfig:
    endpoint: str = "ws://127.0.0.1:29531"
    bridge_id: str = ""
    room_title: str = ""
    self_sender: str = ""
    confirmed_self: bool = False
    poll_seconds: float = 5.0
    idle_seconds: float = 3.0
    start_on_login: bool = False

    def validate(self) -> None:
        parsed = urlparse(self.endpoint)
        if (parsed.scheme != "ws" or parsed.hostname != "127.0.0.1" or
                not parsed.port or parsed.username or parsed.password or parsed.query or parsed.fragment or
                parsed.path not in ("", "/")):
            raise BridgeError("loopback_endpoint_required")
        if not 5 <= self.poll_seconds <= 60 or not 3 <= self.idle_seconds <= 60:
            raise BridgeError("unsafe_poll_configuration")

    @classmethod
    def load(cls, directory: Path) -> "BridgeConfig":
        path = directory / "config.json"
        value = cls(**json.loads(path.read_text(encoding="utf-8"))) if path.exists() else cls(bridge_id=str(uuid4()))
        value.validate()
        return value

    def save(self, directory: Path) -> None:
        self.validate()
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / "config.json"
        temp = directory / "config.json.tmp"
        temp.write_text(json.dumps(asdict(self), ensure_ascii=False, indent=2), encoding="utf-8")
        temp.replace(path)


def save_secret(directory: Path, token: str | None = None) -> str:
    import win32crypt
    directory.mkdir(parents=True, exist_ok=True)
    token = token or secrets.token_hex(32)
    if len(token) != 64 or any(c not in "0123456789abcdef" for c in token):
        raise BridgeError("invalid_pairing_secret")
    ciphertext = win32crypt.CryptProtectData(token.encode(), "kakao-local", None, None, None, 0)
    (directory / "pairing.dpapi").write_bytes(ciphertext)
    return token


def load_secret(directory: Path) -> str:
    import win32crypt
    return win32crypt.CryptUnprotectData((directory / "pairing.dpapi").read_bytes(), None, None, None, 0)[1].decode()
