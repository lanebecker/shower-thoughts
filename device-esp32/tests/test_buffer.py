"""Tests for the buffered-recording manager (mirrors the Pi buffer policy)."""

import buffer


_NAMES = [
    "thought_20260610_000000.wav",
    "thought_20260611_000000.wav",
    "thought_20260612_000000.wav",
    "thought_20260613_000000.wav",
    "thought_20260614_000000.wav",
]


def _make(directory, names):
    for n in names:
        (directory / n).write_bytes(b"")


def test_pending_wavs_oldest_first(tmp_path):
    _make(tmp_path, list(reversed(_NAMES)))          # create out of order
    assert buffer.pending_wavs(str(tmp_path)) == _NAMES


def test_pending_ignores_non_matching_files(tmp_path):
    _make(tmp_path, _NAMES)
    (tmp_path / "notes.txt").write_bytes(b"x")
    (tmp_path / "thought_partial.tmp").write_bytes(b"x")
    assert buffer.pending_wavs(str(tmp_path)) == _NAMES


def test_enforce_cap_keeps_newest_and_returns_dropped(tmp_path):
    _make(tmp_path, _NAMES)                            # 5 files
    dropped = buffer.enforce_cap(str(tmp_path), 3)
    assert dropped == _NAMES[:2]                        # two oldest dropped
    assert buffer.pending_wavs(str(tmp_path)) == _NAMES[2:]


def test_enforce_cap_noop_when_under_limit(tmp_path):
    _make(tmp_path, _NAMES[:2])
    assert buffer.enforce_cap(str(tmp_path), 50) == []
    assert buffer.pending_wavs(str(tmp_path)) == _NAMES[:2]
