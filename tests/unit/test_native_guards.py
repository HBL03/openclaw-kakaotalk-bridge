import sys
from unittest.mock import MagicMock
import pytest
from kakao_local.config import BridgeConfig
from kakao_local.models import BridgeError, Message, Snapshot, UnsafeDesktop

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="Win32 guard mocks")


def adapter():
    from kakao_local.ui_adapter import WindowsUiAdapter
    value = WindowsUiAdapter(BridgeConfig(room_title="self", self_sender="owner", confirmed_self=True))
    value.gui = MagicMock()
    value.gui.EnumChildWindows.side_effect = lambda hwnd, visit, ctx: None
    return value


def test_room_title_alone_is_not_self_evidence():
    with pytest.raises(BridgeError, match="type_unverified"):
        adapter()._self_evidence(Snapshot(()))


def test_wrong_sender_or_member_count_blocks_send():
    with pytest.raises(BridgeError, match="not_self_room"):
        adapter()._self_evidence(Snapshot((), "self", 2))
    with pytest.raises(BridgeError, match="unexpected_sender"):
        adapter()._self_evidence(Snapshot((Message("other", "", "", "hello"),), "self", 1))


def test_locked_desktop_does_not_bind_or_send():
    value = adapter()
    value.desktop_ready = lambda: False
    value.bind_self = MagicMock()
    with pytest.raises(UnsafeDesktop, match="desktop_locked"):
        value.preflight()
    value.bind_self.assert_not_called()


def test_clipboard_with_unrestorable_format_is_not_modified():
    value = adapter()
    value.clip = MagicMock()
    value.clip.EnumClipboardFormats.return_value = 999
    with pytest.raises(UnsafeDesktop, match="restorable"):
        with value._clipboard():
            pass
    value.clip.EmptyClipboard.assert_not_called()


def test_newer_user_clipboard_wins_over_restoration():
    value = adapter()
    value.clip = MagicMock()
    value.clip.EnumClipboardFormats.return_value = 0
    value.clip.GetClipboardSequenceNumber.return_value = 8
    with value._clipboard() as state:
        state["owned_sequence"] = 7
    value.clip.EmptyClipboard.assert_not_called()


def test_real_input_after_own_input_blocks_next_action():
    value = adapter()
    value.api = MagicMock()
    value.api.GetTickCount.return_value = 10000
    value.api.GetLastInputInfo.return_value = 9990
    value._own_input_tick = 9990
    value._check_idle()
    value.api.GetLastInputInfo.return_value = 9991
    with pytest.raises(UnsafeDesktop, match="user_active"):
        value._check_idle()


def test_focus_uses_pointer_sized_native_structure(monkeypatch):
    import ctypes
    from kakao_local.ui_adapter import _GuiThreadInfo, _Input
    value = adapter()
    dll = MagicMock()

    def fill(thread, pointer):
        info = ctypes.cast(pointer, ctypes.POINTER(_GuiThreadInfo)).contents
        assert info.cbSize == ctypes.sizeof(_GuiThreadInfo)
        info.hwndFocus = 1234
        return 1
    dll.GetGUIThreadInfo.side_effect = fill
    monkeypatch.setattr(ctypes, "WinDLL", lambda *args, **kwargs: dll)
    assert value._focused_control(99) == 1234
    assert ctypes.sizeof(_Input) == (40 if ctypes.sizeof(ctypes.c_void_p) == 8 else 28)
