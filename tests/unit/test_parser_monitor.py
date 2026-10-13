import pytest
from kakao_local.dedup import SnapshotCursor
from kakao_local.mock_adapter import MockAdapter
from kakao_local.models import AmbiguousSnapshot, BridgeError, Message, Snapshot
from kakao_local.monitor import Monitor
from kakao_local.parser import command_body, parse_snapshot
from kakao_local.state_store import StateStore


def test_multiline_dates_and_emoji():
    result = parse_snapshot("[self] [대화상대 1명]\r\n2026년 10월 13일 화요일\r\n"
                            "[self] [오전 12:00] !ai 첫 줄\r\n\r\n  둘째 줄 🙂\r\n"
                            "[self] [오후 12:01] 메모")
    assert result.member_count == 1
    assert result.messages[0].text == "!ai 첫 줄\n\n  둘째 줄 🙂"
    assert result.messages[0].time == "00:00"
    assert result.messages[1].time == "12:01"
    assert result.messages[0].date == "2026-10-13"


@pytest.mark.parametrize("text,expected", [("!ai hello", "hello"), ("!ai\n질문", "질문"), ("!ai", ""),
    ("!aix nope", None), (" !ai memo", None), ("[OpenClaw]\n!ai hello", None),
    ("[OpenClaw 알림] 물 마시기", None), ("memo !ai test", None)])
def test_command_filter(text, expected):
    assert command_body(text) == expected


@pytest.mark.parametrize("text", ["카카오톡의 다른 복사 형식", "[self] [오후 25:72] bad", "2026년 13월 1일 월요일"])
def test_unknown_formats_fail_closed(text):
    with pytest.raises(BridgeError):
        parse_snapshot(text)


def test_command_limit():
    with pytest.raises(BridgeError, match="command_too_long"):
        command_body("!ai " + "가" * 4001)


def test_one_hundred_identical_occurrences_not_coalesced():
    adapter, store = MockAdapter(), StateStore(":memory:")
    adapter.append("!ai old command")
    monitor = Monitor(adapter, store)
    assert monitor.poll() == []
    ids = set()
    for _ in range(100):
        adapter.append("!ai 동일한 명령")
        monitor.poll()
        pending = store.pending_inbound()
        assert len(pending) == 1
        ids.add(pending[0]["eventId"])
        store.inbound_ack(pending[0]["eventId"], "completed")
        adapter.append("[OpenClaw]\n응답")
        monitor.poll()
        assert not store.pending_inbound()
    assert len(ids) == 100
    store.close()


def test_full_append_and_unique_shift():
    def snapshot(keys):
        return Snapshot(tuple(Message("self", "2026-10-13", "00:00", x) for x in keys))
    cursor = SnapshotCursor()
    cursor.observe(snapshot(["a", "b", "c"]))
    assert [m.text for m in cursor.observe(snapshot(["b", "c", "d"]))] == ["d"]
    with pytest.raises(AmbiguousSnapshot):
        cursor.observe(snapshot(["unrelated", "!ai old"]))
    assert cursor.observe(snapshot(["unrelated", "!ai old"])) == ()


def test_ambiguous_repeated_tail_stops():
    cursor = SnapshotCursor()
    msg = Message("self", "2026-10-13", "00:00", "repeat")
    cursor.observe(Snapshot((Message("self", "", "", "anchor"), msg, msg)))
    with pytest.raises(AmbiguousSnapshot):
        cursor.observe(Snapshot((msg, msg, Message("self", "", "", "next"))))


def test_pause_resume_establishes_fresh_baseline():
    adapter, store = MockAdapter(), StateStore(":memory:")
    monitor = Monitor(adapter, store)
    monitor.poll()
    monitor.cursor.reset()
    adapter.append("!ai while paused")
    monitor.poll()
    assert not store.pending_inbound()
    store.close()
