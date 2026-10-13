from .models import AmbiguousSnapshot, Message, Snapshot


class SnapshotCursor:
    """Compare ordered occurrences, not a set of message/content hashes.

    Full-prefix growth is unambiguous, including 100 identical occurrences.
    A shifted/truncated snapshot is accepted only with one unique overlap.
    Equal fixed-size all-identical snapshots cannot reveal an append: live
    collection therefore copies the entire loaded list, never a fixed tail.
    """

    def __init__(self) -> None:
        self._previous: tuple[str, ...] | None = None

    def reset(self) -> None:
        self._previous = None

    def observe(self, snapshot: Snapshot) -> tuple[Message, ...]:
        keys = tuple(message.fingerprint for message in snapshot.messages)
        previous = self._previous
        self._previous = keys
        if previous is None or keys == previous:
            return ()
        if len(keys) >= len(previous) and keys[:len(previous)] == previous:
            return snapshot.messages[len(previous):]
        if not previous or not keys:
            raise AmbiguousSnapshot("snapshot_discontinuity")
        overlaps = [n for n in range(1, min(len(keys), len(previous)) + 1)
                    if previous[-n:] == keys[:n]]
        if len(overlaps) != 1 or overlaps[0] < 2:
            raise AmbiguousSnapshot("snapshot_discontinuity")
        return snapshot.messages[overlaps[0]:]
