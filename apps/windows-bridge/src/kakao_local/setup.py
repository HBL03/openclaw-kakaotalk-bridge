"""Install a locally built, reviewed channel archive into an existing managed WSL.

Uses stdin, not Windows drive mounts. No remote shell script, root, model changes,
or login automation. Caller supplies an exact archive SHA256.
"""
import base64
import hashlib
import json
import re
import subprocess
from pathlib import Path
from .models import BridgeError

_LINUX_SETUP = r'''
import base64, hashlib, json, os, pathlib, shutil, subprocess, sys, tempfile
request=json.load(sys.stdin)
base=pathlib.Path.home()/'.openclaw'
config_path=base/'openclaw.json'
old=config_path.read_bytes()
config=json.loads(old)
archive=base64.b64decode(request['archive'],validate=True)
assert hashlib.sha256(archive).hexdigest()==request['sha256'], 'archive_hash_mismatch'
cli=shutil.which('openclaw')
assert cli, 'openclaw_cli_not_found'
version=subprocess.run([cli,'--version'],capture_output=True,text=True,check=True).stdout
assert '2026.10.2' in version, 'unsupported_openclaw_version'
assert 'kakao-local' not in config.get('channels',{}), 'channel_already_configured'
state=base/'kakao-local'
state.mkdir(mode=0o700,exist_ok=True)
state.chmod(0o700)
backup=state/'config.before-install.json'
if backup.exists(): raise RuntimeError('existing_backup_requires_review')
backup.write_bytes(old); backup.chmod(0o600)
with tempfile.TemporaryDirectory(prefix='kakao-local-') as work:
    package=pathlib.Path(work)/'channel.tgz'; package.write_bytes(archive)
    result=subprocess.run([cli,'plugins','install',str(package)],capture_output=True,text=True)
    if result.returncode:
        # The CLI owns its own edits. Never overwrite possible concurrent user edits.
        raise RuntimeError('plugin_install_failed; review OpenClaw plugin approval/diagnostics')
before_merge=config_path.read_bytes()
written=None
try:
    merged=json.loads(before_merge)
    secret=state/'pairing.secret'; secret.write_text(request['token']); secret.chmod(0o600)
    merged.setdefault('channels',{})['kakao-local']={
        'enabled':True,'port':request['port'],'secretFile':str(secret),
        'stateDir':str(state),'bridgeId':request['bridgeId']}
    plugins=merged.setdefault('plugins',{})
    plugins.setdefault('entries',{}).setdefault('kakao-local',{})['enabled']=True
    allowed=plugins.get('allow')
    if isinstance(allowed,list) and 'kakao-local' not in allowed: allowed.append('kakao-local')
    temp=config_path.with_suffix('.kakao-local.tmp')
    written=json.dumps(merged,ensure_ascii=False,indent=2).encode('utf-8')
    temp.write_bytes(written); temp.chmod(0o600)
    if config_path.read_bytes()!=before_merge: raise RuntimeError('config_changed_during_install')
    temp.replace(config_path)
    checked=subprocess.run([cli,'config','validate'],capture_output=True,text=True)
    if checked.returncode: raise RuntimeError('config_validation_failed')
except Exception:
    # Restore only our own write, preserving the plugin CLI's state and newer edits.
    if written is not None and config_path.read_bytes()==written:
        temp=config_path.with_suffix('.kakao-local.rollback.tmp')
        temp.write_bytes(before_merge); temp.chmod(0o600); temp.replace(config_path)
    raise
print(json.dumps({'status':'installed','gatewayRestartRequired':True}))
'''


def install_channel(archive: Path, expected_sha256: str, token: str, bridge_id: str,
                    distro: str = "OpenClawGateway", port: int = 29531) -> dict:
    if not archive.is_file() or hashlib.sha256(archive.read_bytes()).hexdigest() != expected_sha256:
        raise BridgeError("archive_hash_mismatch")
    if not 1024 <= port <= 65535:
        raise BridgeError("invalid_port")
    if not re.fullmatch(r"[a-f0-9]{64}", token) or not re.fullmatch(r"[A-Za-z0-9_.:/-]{1,160}", bridge_id):
        raise BridgeError("invalid_pairing")
    request = {"archive": base64.b64encode(archive.read_bytes()).decode(), "sha256": expected_sha256,
               "token": token, "bridgeId": bridge_id, "port": port}
    result = subprocess.run(["wsl.exe", "-d", distro, "--user", "openclaw", "--", "python3", "-c", _LINUX_SETUP],
                            input=json.dumps(request), capture_output=True, text=True, encoding="utf-8",
                            timeout=180, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    if result.returncode:
        # Never relay raw CLI output (may include config secrets) to a log or UI.
        raise BridgeError("wsl_install_failed_review_gateway_plugin_diagnostics")
    return json.loads(result.stdout)
