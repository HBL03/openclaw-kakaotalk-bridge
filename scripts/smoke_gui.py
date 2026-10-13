"""Render only our own Qt widgets offscreen; never bind or inspect KakaoTalk."""
import argparse
import os
from pathlib import Path
import tempfile

os.environ["QT_QPA_PLATFORM"] = "offscreen"


def main() -> None:
    from PySide6.QtWidgets import QApplication
    from PySide6.QtGui import QFont, QFontDatabase
    from kakao_local.tray import BridgeWindow
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    app = QApplication([])
    font = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts/malgun.ttf"
    if font.is_file():
        QFontDatabase.addApplicationFont(str(font))
    app.setFont(QFont("Malgun Gothic", 10))
    with tempfile.TemporaryDirectory(prefix="kakao-local-gui-") as directory:
        window = BridgeWindow(Path(directory))
        window.show()
        app.processEvents()
        assert window.engine is None and not window.autostart.isChecked()
        args.output.parent.mkdir(parents=True, exist_ok=True)
        if not window.grab().save(str(args.output)):
            raise RuntimeError("GUI render failed")
        window.timer.stop()
        window.tray.hide()
        window.hide()
        window.deleteLater()
        app.processEvents()
    print("Offscreen settings window rendered; no KakaoTalk or Gateway access.")


if __name__ == "__main__":
    main()
