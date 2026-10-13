import hashlib
import secrets
import sys
import threading
import webbrowser
from pathlib import Path
from urllib.parse import urlparse
from PySide6.QtCore import QLockFile, QTimer, QThread, Signal
from PySide6.QtGui import QAction, QFont
from PySide6.QtWidgets import (QApplication, QCheckBox, QFileDialog, QFormLayout, QHBoxLayout,
                              QLabel, QLineEdit, QMainWindow, QMenu, QMessageBox, QPushButton,
                              QStyle, QSystemTrayIcon, QVBoxLayout, QWidget)
from .autostart import set_autostart
from .config import BridgeConfig, data_dir, load_secret, save_secret
from .diagnostics import export_diagnostics
from .local_transport import BridgeEngine
from .models import BridgeError
from .poc import EchoProbe
from .setup import install_channel
from .ui_adapter import WindowsUiAdapter

LABELS = {
    "paused": "일시 정지", "watching": "새 명령 대기 중", "connection_failed": "Gateway 연결 대기",
    "user_active": "PC 사용 중 — 입력이 멈추면 재개", "desktop_locked": "Windows 잠금 — 대기 중",
    "confirmed": "카카오톡 UI에서 발송 확인", "unknown": "전송 확인 불가 — 자동 재발송하지 않음",
    "self_room_type_unverified": "본인 방 유형 확인 실패 — 전송 차단 (P0 검증 필요)",
    "clipboard_format_not_restorable": "현재 클립보드 형식을 보존할 수 없어 대기 중",
    "bound_window_changed": "대상 창 변경 — 다시 확인 필요", "self_window_not_unique": "본인 방 창을 하나만 열어 주세요",
    "empty_command": "사용법: !ai 뒤에 질문을 입력하세요", "stopped": "중지됨",
}


class InstallTask(QThread):
    done = Signal(str)

    def __init__(self, action):
        super().__init__()
        self.action = action

    def run(self):
        try:
            self.action()
            self.done.emit("설치 완료. OpenClaw Companion에서 Gateway를 재시작한 뒤 연결을 시작하세요.")
        except Exception as error:
            self.done.emit(str(error) if isinstance(error, BridgeError) else "설치 실패 — Gateway 진단을 확인하세요.")


class BridgeWindow(QMainWindow):
    def __init__(self, directory: Path):
        super().__init__()
        self.directory = directory
        self.config = BridgeConfig.load(directory)
        self.engine = None
        self.worker = None
        self.install_task = None
        self.setWindowTitle("OpenClaw · 카카오톡 로컬 브리지 — 개발 미리보기")
        self.resize(700, 560)
        root = QWidget()
        layout = QVBoxLayout(root)
        heading = QLabel("나와의 채팅을 OpenClaw에 연결")
        heading.setStyleSheet("font-size:22px;font-weight:600;margin-bottom:8px")
        layout.addWidget(heading)
        note = QLabel("실제 기기 검증 전 개발 버전입니다. 본인 방만 지원하며, PC 사용 중에는 동작을 기다립니다.\n"
                      "카카오톡에서 나와의 채팅 창을 직접 열어 주세요. 잠금·절전 중 동작은 보장하지 않습니다.")
        note.setWordWrap(True)
        layout.addWidget(note)
        form = QFormLayout()
        self.title = QLineEdit(self.config.room_title)
        self.sender = QLineEdit(self.config.self_sender)
        self.endpoint = QLineEdit(self.config.endpoint)
        self.distro = QLineEdit("OpenClawGateway")
        form.addRow("본인 채팅방 창 제목", self.title)
        form.addRow("내 메시지의 표시 이름", self.sender)
        form.addRow("로컬 연결 주소", self.endpoint)
        form.addRow("Gateway WSL 배포판", self.distro)
        layout.addLayout(form)
        self.confirm = QCheckBox("선택한 창이 내 계정의 '나와의 채팅'임을 확인했습니다")
        self.confirm.setChecked(self.config.confirmed_self)
        layout.addWidget(self.confirm)
        self.autostart = QCheckBox("Windows 로그인 시 실행하고 감시 재개")
        self.autostart.setChecked(self.config.start_on_login)
        layout.addWidget(self.autostart)
        row = QHBoxLayout()
        for label, callback in [("설정 저장", self.save), ("P0 echo 시작", self.start_echo),
                                ("OpenClaw 연결", self.start_bridge), ("일시 정지 / 종료", self.stop_worker)]:
            button = QPushButton(label)
            button.clicked.connect(callback)
            row.addWidget(button)
        layout.addLayout(row)
        second = QHBoxLayout()
        for label, callback in [("채널 패키지 설치", self.install), ("진단 내보내기", self.export),
                                ("업데이트 확인", lambda: webbrowser.open("https://github.com/HBL03/openclaw-kakaotalk-bridge/releases"))]:
            button = QPushButton(label)
            button.clicked.connect(callback)
            second.addWidget(button)
        layout.addLayout(second)
        self.state = QLabel("일시 정지 — 먼저 P0 echo 테스트로 읽기·쓰기를 검증하세요.")
        self.state.setWordWrap(True)
        self.state.setStyleSheet("background:#eef2f7;padding:16px;border-radius:6px")
        layout.addWidget(self.state)
        self.counts = QLabel("")
        layout.addWidget(self.counts)
        layout.addStretch()
        self.setCentralWidget(root)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh)
        self.timer.start(1000)
        self.tray = QSystemTrayIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_ComputerIcon), self)
        menu = QMenu(self)
        for label, callback in [("상태 / 설정", self.showNormal), ("일시 정지", self.stop_worker),
                                ("진단 내보내기", self.export), ("종료", self.quit)]:
            action = QAction(label, self)
            action.triggered.connect(callback)
            menu.addAction(action)
        self.tray.setContextMenu(menu)
        self.tray.setToolTip("OpenClaw KakaoTalk Local")
        self.tray.activated.connect(lambda reason: self.showNormal() if reason == QSystemTrayIcon.ActivationReason.Trigger else None)
        self.tray.show()

    def save(self) -> bool:
        if self.worker and self.worker.is_alive():
            QMessageBox.information(self, "설정", "먼저 감시를 중지하세요.")
            return False
        try:
            self.config.room_title = self.title.text().strip()
            self.config.self_sender = self.sender.text().strip()
            self.config.endpoint = self.endpoint.text().strip()
            self.config.confirmed_self = self.confirm.isChecked()
            self.config.start_on_login = self.autostart.isChecked()
            self.config.save(self.directory)
            set_autostart(self.config.start_on_login)
            return True
        except Exception:
            QMessageBox.warning(self, "설정 오류", "로컬 주소와 Windows 사용자 권한을 확인하세요.")
            return False

    def _start(self, factory) -> None:
        if not self.save():
            return
        if not self.config.confirmed_self or not self.config.room_title or not self.config.self_sender:
            QMessageBox.information(self, "본인 방 확인", "창 제목, 표시 이름, 본인 방 확인을 완료하세요.")
            return
        try:
            self.engine = factory()
            self.worker = threading.Thread(target=self.engine.run, daemon=True)
            self.worker.start()
        except Exception:
            self.state.setText("시작 실패 — 채널 설치 및 페어링 상태를 확인하세요.")

    def start_echo(self) -> None:
        self._start(lambda: EchoProbe(self.directory, lambda: WindowsUiAdapter(self.config)))

    def start_bridge(self) -> None:
        def create():
            engine = BridgeEngine(self.config, self.directory, load_secret(self.directory), lambda: WindowsUiAdapter(self.config))
            engine.paused.clear()
            return engine
        self._start(create)

    def stop_worker(self) -> None:
        if self.engine:
            self.engine.stop.set()
        self.state.setText("중지 요청됨 — 진행 중인 UI 작업이 끝나면 종료합니다.")

    def refresh(self) -> None:
        if self.engine:
            snapshot = self.engine.snapshot()
            state = snapshot.get("state", "unknown")
            self.state.setText(LABELS.get(state, state))
            self.counts.setText(f"처리 현황: {snapshot.get('counts', {})}")

    def install(self) -> None:
        if not self.save():
            return
        filename, _ = QFileDialog.getOpenFileName(self, "빌드한 채널 패키지 선택", "", "Channel package (*.tgz)")
        if not filename:
            return
        archive = Path(filename)
        manifest = archive.with_suffix(archive.suffix + ".sha256")
        if not manifest.exists():
            QMessageBox.warning(self, "해시 파일 필요", "패키지와 함께 생성된 .tgz.sha256 파일이 필요합니다.")
            return
        expected = manifest.read_text(encoding="utf-8").split()[0]
        if hashlib.sha256(archive.read_bytes()).hexdigest() != expected:
            QMessageBox.warning(self, "검증 실패", "패키지 해시가 일치하지 않습니다.")
            return
        if self.install_task and self.install_task.isRunning():
            return
        token = load_secret(self.directory) if (self.directory / "pairing.dpapi").exists() else secrets.token_hex(32)
        distro = self.distro.text().strip()
        port = urlparse(self.config.endpoint).port
        bridge_id = self.config.bridge_id

        def perform_install():
            install_channel(archive, expected, token, bridge_id, distro, port)
            save_secret(self.directory, token)

        self.install_task = InstallTask(perform_install)
        self.install_task.done.connect(self.state.setText)
        self.install_task.start()
        self.state.setText("채널 설치 중… 기존 에이전트와 모델 설정을 유지합니다.")

    def export(self) -> None:
        filename, _ = QFileDialog.getSaveFileName(self, "진단 내보내기", "kakao-local-diagnostics.zip", "ZIP (*.zip)")
        if filename:
            export_diagnostics(Path(filename), self.engine.snapshot() if self.engine else {"state": "paused"})

    def quit(self) -> None:
        self.stop_worker()
        if self.install_task and self.install_task.isRunning():
            self.state.setText("설치 작업이 끝난 후 종료하세요.")
            return
        if self.worker and self.worker.is_alive():
            self.worker.join(timeout=15)
            if self.worker.is_alive():
                self.state.setText("진행 중 작업을 기다리는 중입니다. 잠시 후 종료하세요.")
                return
        QApplication.instance().quit()

    def closeEvent(self, event):
        event.ignore()
        self.hide()


def run_gui(directory: Path | None = None, tray: bool = False) -> None:
    app = QApplication(sys.argv)
    app.setFont(QFont("Malgun Gothic", 10))
    app.setQuitOnLastWindowClosed(False)
    directory = directory or data_dir()
    directory.mkdir(parents=True, exist_ok=True)
    lock = QLockFile(str(directory / "bridge.lock"))
    if not lock.tryLock(0):
        QMessageBox.information(None, "OpenClaw KakaoTalk", "이미 실행 중입니다. 트레이 아이콘을 확인하세요.")
        return
    window = BridgeWindow(directory)
    if not tray:
        window.show()
    elif window.config.start_on_login:
        QTimer.singleShot(1000, window.start_bridge)
    app.exec()
    lock.unlock()
