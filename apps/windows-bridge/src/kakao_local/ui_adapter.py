"""Conservative Win32 adapter. Importing this module performs no UI operations.

No DB access, room search, coordinate clicks, login, bulk-send, or background
service automation. Unsupported self-room evidence fails closed at the P0 gate.
"""
import ctypes
from ctypes import wintypes
import time
from contextlib import contextmanager
from pathlib import Path
from .config import BridgeConfig
from .models import BridgeError, Snapshot, UnsafeDesktop
from .parser import parse_snapshot


class _GuiThreadInfo(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.DWORD), ("flags", wintypes.DWORD),
                ("hwndActive", wintypes.HWND), ("hwndFocus", wintypes.HWND),
                ("hwndCapture", wintypes.HWND), ("hwndMenuOwner", wintypes.HWND),
                ("hwndMoveSize", wintypes.HWND), ("hwndCaret", wintypes.HWND),
                ("rcCaret", wintypes.RECT)]


class _KeyboardInput(ctypes.Structure):
    _fields_ = [("wVk", wintypes.WORD), ("wScan", wintypes.WORD),
                ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD),
                ("dwExtraInfo", ctypes.c_size_t)]


class _MouseInput(ctypes.Structure):
    _fields_ = [("dx", wintypes.LONG), ("dy", wintypes.LONG), ("mouseData", wintypes.DWORD),
                ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD), ("dwExtraInfo", ctypes.c_size_t)]


class _InputUnion(ctypes.Union):
    _fields_ = [("ki", _KeyboardInput), ("mi", _MouseInput)]


class _Input(ctypes.Structure):
    _fields_ = [("type", wintypes.DWORD), ("data", _InputUnion)]


class WindowsUiAdapter:
    def __init__(self, config: BridgeConfig):
        import win32api
        import win32clipboard
        import win32con
        import win32gui
        import win32process
        self.api, self.clip, self.con = win32api, win32clipboard, win32con
        self.gui, self.process = win32gui, win32process
        self.config = config
        self.hwnd = 0
        self.pid = 0
        self._own_input_tick = None
        self._self_verified = False

    def desktop_ready(self) -> bool:
        user32 = ctypes.WinDLL("user32", use_last_error=True)
        user32.OpenInputDesktop.restype = ctypes.c_void_p
        user32.CloseDesktop.argtypes = [ctypes.c_void_p]
        user32.GetUserObjectInformationW.argtypes = [ctypes.c_void_p, ctypes.c_int,
                                                    ctypes.c_void_p, ctypes.c_uint, ctypes.c_void_p]
        desktop = user32.OpenInputDesktop(0, False, 1)
        if not desktop:
            return False
        try:
            name = ctypes.create_unicode_buffer(256)
            needed = ctypes.c_uint()
            return bool(user32.GetUserObjectInformationW(desktop, 2, name, ctypes.sizeof(name),
                                                         ctypes.byref(needed))) and name.value == "Default"
        finally:
            user32.CloseDesktop(desktop)

    def _process_path(self, hwnd: int) -> str:
        _, pid = self.process.GetWindowThreadProcessId(hwnd)
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.OpenProcess.restype = ctypes.c_void_p
        kernel.QueryFullProcessImageNameW.argtypes = [ctypes.c_void_p, ctypes.c_uint,
                                                     ctypes.c_void_p, ctypes.c_void_p]
        kernel.CloseHandle.argtypes = [ctypes.c_void_p]
        handle = kernel.OpenProcess(0x1000, False, pid)
        if not handle:
            return ""
        try:
            buffer = ctypes.create_unicode_buffer(32768)
            size = ctypes.c_uint(len(buffer))
            if kernel.QueryFullProcessImageNameW(handle, 0, buffer, ctypes.byref(size)):
                return buffer.value
            return ""
        finally:
            kernel.CloseHandle(handle)

    def bind_self(self) -> None:
        if not self.config.confirmed_self or not self.config.room_title or not self.config.self_sender:
            raise BridgeError("self_confirmation_required")
        matches = []

        def visit(hwnd: int, _context: object) -> None:
            if (self.gui.GetWindowText(hwnd) == self.config.room_title and
                    self.gui.GetClassName(hwnd) == "EVA_Window_Dblclk" and
                    Path(self._process_path(hwnd)).name.lower() == "kakaotalk.exe"):
                matches.append(hwnd)
        self.gui.EnumWindows(visit, None)
        if len(matches) != 1:
            raise BridgeError("self_window_not_unique")
        self.hwnd = matches[0]
        _, self.pid = self.process.GetWindowThreadProcessId(self.hwnd)
        self._self_verified = False

    def _child(self, class_name: str) -> int:
        handles = []
        self.gui.EnumChildWindows(self.hwnd, lambda hwnd, _: handles.append(hwnd)
                                  if self.gui.GetClassName(hwnd) == class_name else None, None)
        if len(handles) != 1:
            raise BridgeError("unsupported_control_tree")
        return handles[0]

    def preflight(self) -> None:
        if not self.desktop_ready():
            self._self_verified = False
            raise UnsafeDesktop("desktop_locked")
        if not self.hwnd:
            self.bind_self()
        if (not self.gui.IsWindow(self.hwnd) or self.gui.GetWindowText(self.hwnd) != self.config.room_title or
                self.process.GetWindowThreadProcessId(self.hwnd)[1] != self.pid or
                Path(self._process_path(self.hwnd)).name.lower() != "kakaotalk.exe"):
            self.hwnd = 0
            self._self_verified = False
            raise BridgeError("bound_window_changed")
        # GetLastInputInfo uses wrapping 32-bit ticks; account for wrap correctly.
        self._check_idle()

    def _check_idle(self) -> None:
        last_input = self.api.GetLastInputInfo()
        idle_ms = (self.api.GetTickCount() - last_input) & 0xFFFFFFFF
        if idle_ms < self.config.idle_seconds * 1000 and last_input != self._own_input_tick:
            raise UnsafeDesktop("user_active")

    @contextmanager
    def _focus(self, control: int):
        self.preflight()
        previous = self.gui.GetForegroundWindow()
        self.gui.ShowWindow(self.hwnd, self.con.SW_RESTORE)
        self.gui.SetForegroundWindow(self.hwnd)
        current = self.api.GetCurrentThreadId()
        target, _ = self.process.GetWindowThreadProcessId(self.hwnd)
        attached = current != target
        if attached:
            self.process.AttachThreadInput(current, target, True)
        try:
            self.gui.SetFocus(control)
            self._assert_focus(control)
            yield
        finally:
            if attached:
                self.process.AttachThreadInput(current, target, False)
            # Never steal focus back after an intervening user switch.
            if previous and self.gui.IsWindow(previous) and self.gui.GetForegroundWindow() == self.hwnd:
                try:
                    self.gui.SetForegroundWindow(previous)
                except Exception:
                    pass

    def _assert_focus(self, control: int) -> None:
        self._check_idle()
        if not self.desktop_ready() or self.gui.GetForegroundWindow() != self.hwnd:
            raise UnsafeDesktop("focus_changed")
        thread, _ = self.process.GetWindowThreadProcessId(self.hwnd)
        if self._focused_control(thread) != control:
            raise UnsafeDesktop("focus_changed")

    def _focused_control(self, thread: int) -> int:
        user32 = ctypes.WinDLL("user32", use_last_error=True)
        user32.GetGUIThreadInfo.argtypes = [wintypes.DWORD, ctypes.POINTER(_GuiThreadInfo)]
        info = _GuiThreadInfo(cbSize=ctypes.sizeof(_GuiThreadInfo))
        if not user32.GetGUIThreadInfo(thread, ctypes.byref(info)):
            raise UnsafeDesktop("focus_unavailable")
        return info.hwndFocus or 0

    def _key(self, control: int, key: int, ctrl: bool = False) -> None:
        self._assert_focus(control)
        if any(self.api.GetAsyncKeyState(vk) & 0x8000 for vk in
               (self.con.VK_CONTROL, self.con.VK_SHIFT, self.con.VK_MENU, self.con.VK_LWIN, self.con.VK_RWIN)):
            raise UnsafeDesktop("modifier_pressed")
        keys = ([(self.con.VK_CONTROL, 0)] if ctrl else []) + [(key, 0), (key, self.con.KEYEVENTF_KEYUP)]
        if ctrl:
            keys.append((self.con.VK_CONTROL, self.con.KEYEVENTF_KEYUP))
        tick = self.api.GetTickCount() & 0xFFFFFFFF
        batch = (_Input * len(keys))(*[_Input(type=1, data=_InputUnion(
            ki=_KeyboardInput(wVk=vk, dwFlags=flags, time=tick))) for vk, flags in keys])
        user32 = ctypes.WinDLL("user32", use_last_error=True)
        user32.SendInput.argtypes = [wintypes.UINT, ctypes.POINTER(_Input), ctypes.c_int]
        if user32.SendInput(len(keys), batch, ctypes.sizeof(_Input)) != len(keys):
            raise BridgeError("input_not_inserted")
        # Only our exact injected timestamp is exempt, never a general grace period.
        self._own_input_tick = tick

    @contextmanager
    def _clipboard(self):
        # Only formats that can be copied losslessly by value are supported.
        # Rich/OLE/image/file clipboards cause a wait instead of data loss.
        allowed = {self.con.CF_UNICODETEXT, self.con.CF_TEXT, self.con.CF_OEMTEXT, self.con.CF_LOCALE}
        saved = {}
        self.clip.OpenClipboard()
        try:
            fmt = self.clip.EnumClipboardFormats(0)
            while fmt:
                if fmt not in allowed:
                    raise UnsafeDesktop("clipboard_format_not_restorable")
                saved[fmt] = self.clip.GetClipboardData(fmt)
                fmt = self.clip.EnumClipboardFormats(fmt)
        finally:
            self.clip.CloseClipboard()
        state = {"owned_sequence": None}
        try:
            yield state
        finally:
            # A third party's newer clipboard takes precedence over our backup.
            if state["owned_sequence"] is not None:
                self.clip.OpenClipboard()
                try:
                    if self.clip.GetClipboardSequenceNumber() == state["owned_sequence"]:
                        self.clip.EmptyClipboard()
                        for fmt, data in saved.items():
                            self.clip.SetClipboardData(fmt, data)
                finally:
                    self.clip.CloseClipboard()

    def _self_evidence(self, snapshot: Snapshot) -> None:
        labels = []
        self.gui.EnumChildWindows(self.hwnd, lambda hwnd, _: labels.append(self.gui.GetWindowText(hwnd)), None)
        if snapshot.room_title and snapshot.room_title != self.config.room_title:
            raise BridgeError("room_header_mismatch")
        if snapshot.member_count not in (None, 1):
            raise BridgeError("not_self_room")
        if snapshot.member_count != 1 and "나와의 채팅" not in labels:
            # Human confirmation/title alone is not sufficient for an unattended send.
            raise BridgeError("self_room_type_unverified")
        if any(msg.sender != self.config.self_sender for msg in snapshot.messages):
            raise BridgeError("unexpected_sender")
        self._self_verified = True

    def read_snapshot(self) -> Snapshot:
        self.preflight()
        control = self._child("EVA_VH_ListControl_Dblclk")
        with self._clipboard() as clipboard, self._focus(control):
            before = self.clip.GetClipboardSequenceNumber()
            self._key(control, self.con.VK_A, ctrl=True)
            self._key(control, self.con.VK_C, ctrl=True)
            for _ in range(20):
                if self.clip.GetClipboardSequenceNumber() != before:
                    break
                time.sleep(0.025)
            else:
                raise BridgeError("copy_not_observed")
            self._assert_focus(control)
            self.clip.OpenClipboard()
            try:
                owner = self.clip.GetClipboardOwner()
                if not owner or self.process.GetWindowThreadProcessId(owner)[1] != self.pid:
                    raise UnsafeDesktop("clipboard_owner_changed")
                raw = self.clip.GetClipboardData(self.con.CF_UNICODETEXT)
                clipboard["owned_sequence"] = self.clip.GetClipboardSequenceNumber()
            finally:
                self.clip.CloseClipboard()
            snapshot = parse_snapshot(raw)
            self._self_evidence(snapshot)
            return snapshot

    def send_text(self, text: str) -> None:
        self.preflight()
        if not self._self_verified:
            raise BridgeError("self_room_type_unverified")
        if not text.startswith(("[OpenClaw]", "[OpenClaw 알림]")) or len(text) > 1000:
            raise BridgeError("unsafe_outbound_text")
        control = self._child("RICHEDIT50W")
        if self.gui.GetWindowText(control):
            raise UnsafeDesktop("user_draft_present")
        with self._clipboard() as clipboard, self._focus(control):
            self.clip.OpenClipboard()
            try:
                self.clip.EmptyClipboard()
                self.clip.SetClipboardText(text, self.con.CF_UNICODETEXT)
                clipboard["owned_sequence"] = self.clip.GetClipboardSequenceNumber()
            finally:
                self.clip.CloseClipboard()
            self._key(control, ord("V"), ctrl=True)
            time.sleep(0.1)
            if self.gui.GetWindowText(control).replace("\r\n", "\n") != text:
                raise BridgeError("paste_not_verified")
            self._key(control, self.con.VK_RETURN)

    def verify_send(self, text: str, before: Snapshot) -> bool:
        from .dedup import SnapshotCursor
        cursor = SnapshotCursor()
        cursor.observe(before)
        for _ in range(3):
            time.sleep(self.config.idle_seconds + 0.1)
            after = self.read_snapshot()
            new = cursor.observe(after)
            if any(msg.text == text and msg.sender == self.config.self_sender for msg in new):
                return True
        return False
