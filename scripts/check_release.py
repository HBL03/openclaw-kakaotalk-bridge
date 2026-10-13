"""Fail-closed public release gate. Never substitutes mocks for manual evidence."""
import argparse
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]
REQUIRED_CHECKS = (
    "selfRoomGuard", "crashRecovery", "clipboardRestored", "focusGuard", "lockGuard",
    "resumeBaseline", "minimizedWindow", "agentRoundtrip", "sessionContinuity", "cronAnnounce",
    "sdkReceiptSemantics", "offlineTtl", "wslLoopback", "gatewayRestart", "longReply",
    "cleanInstall", "upgrade", "uninstall", "existingConfigPreserved",
)


def validate(evidence: dict, commit: str, version: str, now: datetime | None = None) -> list[str]:
    failures = []
    now = now or datetime.now(timezone.utc)
    if not re.fullmatch(r"[0-9a-f]{40}", commit) or evidence.get("sourceCommit") != commit:
        failures.append("source commit does not match")
    if re.search(r"dev|preview", version, re.I) or evidence.get("version") != version:
        failures.append("version is a development build or does not match")
    try:
        checked = datetime.fromisoformat(evidence["checkedAt"].replace("Z", "+00:00"))
        if checked.tzinfo is None or not now - timedelta(days=14) <= checked <= now:
            raise ValueError("stale evidence")
    except (KeyError, TypeError, ValueError, AttributeError):
        failures.append("manual evidence must be dated within the last 14 days (UTC)")
    environment = evidence.get("environment", {})
    for key in ("windowsBuild", "kakaoVersion", "openclawVersion", "tester"):
        if not isinstance(environment.get(key), str) or not environment[key].strip():
            failures.append(f"missing environment.{key}")
    if environment.get("openclawVersion") != "2026.10.2":
        failures.append("unsupported OpenClaw version")
    results = evidence.get("results", {})
    for key, minimum in (("p0EchoCount", 20), ("commandCount", 100)):
        if type(results.get(key)) is not int or results[key] < minimum:
            failures.append(f"{key} must be at least {minimum}")
    for key in ("duplicateSends", "wrongRoomSends"):
        if type(results.get(key)) is not int or results[key] != 0:
            failures.append(f"{key} must be measured as zero")
    for key in REQUIRED_CHECKS:
        if results.get(key) is not True:
            failures.append(f"manual check missing: {key}")
    if evidence.get("lgplSourceAndNoticesReviewed") is not True:
        failures.append("LGPL corresponding source and notices must be reviewed")
    return failures


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence", type=Path, required=True)
    args = parser.parse_args()
    try:
        evidence = json.loads(args.evidence.read_text(encoding="utf-8-sig"))
        commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True, stderr=subprocess.DEVNULL).strip()
        dirty = subprocess.check_output(["git", "status", "--porcelain", "--untracked-files=normal"], cwd=ROOT, text=True)
        version = json.loads((ROOT / "package.json").read_text(encoding="utf-8"))["version"]
        failures = validate(evidence, commit, version)
        if dirty:
            failures.append("working tree must be clean")
    except (OSError, ValueError, subprocess.CalledProcessError, TypeError):
        failures = ["evidence or source commit unavailable"]
    if failures:
        print("PUBLIC RELEASE BLOCKED:\n- " + "\n- ".join(failures))
        return 1
    print("Manual release evidence passed. Binary signatures must still be verified by the build script.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
