import subprocess
import sys


def set_autostart(enabled: bool) -> None:
    import winreg
    command = [sys.executable]
    if not getattr(sys, "frozen", False):
        command += ["-m", "kakao_local.main"]
    command += ["--tray"]
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run") as key:
        if enabled:
            winreg.SetValueEx(key, "OpenClawKakaoLocal", 0, winreg.REG_SZ, subprocess.list2cmdline(command))
        else:
            try:
                winreg.DeleteValue(key, "OpenClawKakaoLocal")
            except FileNotFoundError:
                pass
