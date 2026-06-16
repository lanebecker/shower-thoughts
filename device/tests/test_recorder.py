"""
Unit tests for device/recorder.py buffer/flush/upload helpers.

Hardware modules (RPi.GPIO, pyaudio) are stubbed in device/conftest.py, which
also puts device/ on sys.path so `import recorder` works off-Pi. These tests
exercise only the pure buffer-management and upload helpers; no real audio is
recorded.
"""

import wave

import pytest

import recorder


# Timestamped filenames sort chronologically, so this list is oldest -> newest.
_NAMES = [
    "thought_20260610_000000.wav",
    "thought_20260611_000000.wav",
    "thought_20260612_000000.wav",
    "thought_20260613_000000.wav",
    "thought_20260614_000000.wav",
]


def _make_wavs(directory, names):
    """Create empty placeholder files and return their Paths in given order."""
    paths = []
    for name in names:
        p = directory / name
        p.write_bytes(b"")
        paths.append(p)
    return paths


def _make_real_wav(path):
    """Write a minimal but valid WAV so _post_wav can open it."""
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(16000)
        wf.writeframes(b"\x00\x00" * 8)
    return path


@pytest.fixture(autouse=True)
def _reset_state():
    """Keep state from leaking between tests."""
    recorder._state = recorder.State.IDLE
    yield
    recorder._state = recorder.State.IDLE


# 1. pending ordering
def test_pending_wavs_oldest_first(tmp_path, monkeypatch):
    monkeypatch.setattr(recorder, "RECORDINGS_DIR", tmp_path)
    # Create out of order to prove the function sorts, not just preserves order.
    _make_wavs(tmp_path, list(reversed(_NAMES)))
    result = [p.name for p in recorder._pending_wavs()]
    assert result == _NAMES


# 2. buffer cap
def test_enforce_buffer_cap_keeps_newest(tmp_path, monkeypatch):
    monkeypatch.setattr(recorder, "RECORDINGS_DIR", tmp_path)
    monkeypatch.setattr(recorder, "MAX_BUFFERED", 3)
    _make_wavs(tmp_path, _NAMES)  # 5 files

    recorder._enforce_buffer_cap()

    remaining = [p.name for p in recorder._pending_wavs()]
    assert remaining == _NAMES[-3:]  # newest 3 survive


# 3. flush order + stop-on-failure
def test_flush_pending_oldest_first_stops_on_failure(tmp_path, monkeypatch):
    monkeypatch.setattr(recorder, "RECORDINGS_DIR", tmp_path)
    recorder._state = recorder.State.IDLE
    _make_wavs(tmp_path, _NAMES)  # 5 files

    seen = []
    # Succeed twice, then fail on the 3rd call. Fake does NOT delete files.
    results = iter([True, True, False])

    def fake_post(fp):
        seen.append(fp)
        return next(results)

    monkeypatch.setattr(recorder, "_post_wav", fake_post)

    sent = recorder._flush_pending()

    assert sent == 2                      # only the two successes counted
    assert len(seen) == 3                 # stopped after the failure, not all 5
    assert [p.name for p in seen] == _NAMES[:3]  # oldest-first order
    # Fake never deletes, so all 5 still exist on disk.
    assert sorted(p.name for p in tmp_path.glob("thought_*.wav")) == _NAMES


# 4. flush yields to active recording
def test_flush_pending_yields_to_recording(tmp_path, monkeypatch):
    monkeypatch.setattr(recorder, "RECORDINGS_DIR", tmp_path)
    _make_wavs(tmp_path, _NAMES)
    recorder._state = recorder.State.RECORDING

    def fail_if_called(fp):
        pytest.fail("_post_wav must not run while recording")

    monkeypatch.setattr(recorder, "_post_wav", fail_if_called)

    sent = recorder._flush_pending()
    assert sent == 0


# 5. _post_wav success
def test_post_wav_success_deletes_file(tmp_path, monkeypatch):
    monkeypatch.setattr(recorder, "RECORDINGS_DIR", tmp_path)
    wav = _make_real_wav(tmp_path / "thought_20260615_120000.wav")

    class FakeResp:
        def raise_for_status(self):
            pass

        def json(self):
            return {"job_id": "abc"}

    monkeypatch.setattr(recorder.requests, "post", lambda *a, **k: FakeResp())

    assert recorder._post_wav(wav) is True
    assert not wav.exists()


# 6. _post_wav failure
def test_post_wav_failure_keeps_file(tmp_path, monkeypatch):
    monkeypatch.setattr(recorder, "RECORDINGS_DIR", tmp_path)
    wav = _make_real_wav(tmp_path / "thought_20260615_130000.wav")

    def boom(*a, **k):
        raise recorder.requests.RequestException("down")

    monkeypatch.setattr(recorder.requests, "post", boom)

    assert recorder._post_wav(wav) is False
    assert wav.exists()
