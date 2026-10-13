from datetime import datetime, timezone
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("release_gate", ROOT / "scripts/check_release.py")
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)


def evidence():
    return {"sourceCommit": "a" * 40, "version": "0.1.0-beta.1", "checkedAt": "2026-10-13T00:00:00Z",
            "environment": {"windowsBuild": "test", "kakaoVersion": "test", "openclawVersion": "2026.10.2", "tester": "test"},
            "results": {"p0EchoCount": 20, "commandCount": 100, "duplicateSends": 0, "wrongRoomSends": 0,
                        **{key: True for key in gate.REQUIRED_CHECKS}}, "lgplSourceAndNoticesReviewed": True}


def test_release_template_cannot_pass():
    template = json.loads((ROOT / "release/evidence.example.json").read_text())
    assert gate.validate(template, "a" * 40, "0.1.0-dev.1")


def test_manual_evidence_must_match_commit_date_and_version():
    now = datetime(2026, 10, 13, 1, tzinfo=timezone.utc)
    data = evidence()
    assert gate.validate(data, "a" * 40, "0.1.0-beta.1", now) == []
    assert gate.validate(data, "b" * 40, "0.1.0-beta.1", now)
    assert gate.validate(data, "a" * 40, "0.1.0-dev.1", now)
    assert gate.validate(data, "a" * 40, "0.1.0-beta.1", datetime(2026, 11, 1, tzinfo=timezone.utc))
    data["results"]["wrongRoomSends"] = 1
    assert gate.validate(data, "a" * 40, "0.1.0-beta.1", now)
