import json
import logging
import platform
import re
import time
import zipfile
from logging.handlers import RotatingFileHandler
from pathlib import Path
from . import __version__


def redact(value: str) -> str:
    value = re.sub(r"(?i)(bearer\s+|(?:token|secret|api[_-]?key)\s*[:=]\s*)[^\s,;]+", r"\1[REDACTED]", value)
    value = re.sub(r"\b(?:sk-[A-Za-z0-9_-]{8,}|[a-fA-F0-9]{64})\b", "[REDACTED]", value)
    return re.sub(r"(?i)([A-Z]:\\Users\\)[^\\\s]+", r"\1[USER]", value)


def setup_logging(directory: Path) -> logging.Logger:
    directory.mkdir(parents=True, exist_ok=True)
    for path in directory.glob("bridge.log*"):
        if path.is_file() and path.stat().st_mtime < time.time() - 7 * 86400:
            try:
                path.unlink()
            except OSError:
                pass  # Another live handler can hold the current file on Windows.
    logger = logging.getLogger("kakao_local")
    if not logger.handlers:
        handler = RotatingFileHandler(directory / "bridge.log", maxBytes=2_000_000, backupCount=6, encoding="utf-8")
        handler.setFormatter(RedactingFormatter("%(asctime)s %(levelname)s %(message)s"))
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
    return logger


class RedactingFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        return redact(super().format(record))


def export_diagnostics(destination: Path, status: dict) -> None:
    # Allowlisted facts only: do not bundle config, DB, clipboard, or arbitrary logs.
    facts = {"bridgeVersion": __version__, "system": platform.system(),
             "osVersion": platform.version(), "python": platform.python_version(),
             "state": status.get("state", "unknown"), "counts": status.get("counts", {})}
    with zipfile.ZipFile(destination, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("diagnostics.json", json.dumps(facts, ensure_ascii=False, indent=2))
