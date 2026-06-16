"""
Tests for transcriber.py rate-limit / timeout retry behavior.

The OpenAI client call is mocked; we never hit the network. RateLimitError needs
an httpx.Response to construct, so we build a throwaway 429 response.
"""

import httpx
import pytest
from openai import RateLimitError, APITimeoutError

import transcriber


def _rate_limit_error(retry_after=None):
    headers = {"retry-after": str(retry_after)} if retry_after is not None else {}
    request = httpx.Request("POST", "https://api.openai.com/v1/audio/transcriptions")
    response = httpx.Response(429, headers=headers, request=request)
    return RateLimitError("rate limited", response=response, body=None)


@pytest.fixture
def no_sleep(monkeypatch):
    """Make backoff instant and record the delays that were requested."""
    delays = []
    monkeypatch.setattr(transcriber.time, "sleep", lambda d: delays.append(d))
    return delays


def test_succeeds_first_try(monkeypatch, tmp_path, no_sleep):
    audio = tmp_path / "a.wav"
    audio.write_bytes(b"RIFFfake")
    monkeypatch.setattr(
        transcriber._client.audio.transcriptions, "create",
        lambda **kw: "  hello world  ",
    )
    assert transcriber.transcribe_audio(audio) == "hello world"
    assert no_sleep == []  # no retries needed


def test_retries_then_succeeds(monkeypatch, tmp_path, no_sleep):
    audio = tmp_path / "a.wav"
    audio.write_bytes(b"RIFFfake")
    monkeypatch.setattr(transcriber, "WHISPER_MAX_RETRIES", 3)
    monkeypatch.setattr(transcriber, "WHISPER_RETRY_BASE_DELAY", 2.0)

    calls = {"n": 0}

    def flaky(**kw):
        calls["n"] += 1
        if calls["n"] < 3:
            raise _rate_limit_error()
        return "recovered"

    monkeypatch.setattr(transcriber._client.audio.transcriptions, "create", flaky)
    assert transcriber.transcribe_audio(audio) == "recovered"
    assert calls["n"] == 3
    # Two backoffs: 2*2^0=2, then 2*2^1=4
    assert no_sleep == [2.0, 4.0]


def test_honors_retry_after_header(monkeypatch, tmp_path, no_sleep):
    audio = tmp_path / "a.wav"
    audio.write_bytes(b"RIFFfake")
    monkeypatch.setattr(transcriber, "WHISPER_MAX_RETRIES", 2)
    monkeypatch.setattr(transcriber, "WHISPER_RETRY_BASE_DELAY", 1.0)

    calls = {"n": 0}

    def flaky(**kw):
        calls["n"] += 1
        if calls["n"] == 1:
            raise _rate_limit_error(retry_after=30)
        return "ok"

    monkeypatch.setattr(transcriber._client.audio.transcriptions, "create", flaky)
    assert transcriber.transcribe_audio(audio) == "ok"
    # Retry-After (30) wins over the computed backoff (1.0).
    assert no_sleep == [30.0]


def test_raises_after_exhausting_retries(monkeypatch, tmp_path, no_sleep):
    audio = tmp_path / "a.wav"
    audio.write_bytes(b"RIFFfake")
    monkeypatch.setattr(transcriber, "WHISPER_MAX_RETRIES", 3)

    def always_fail(**kw):
        raise _rate_limit_error()

    monkeypatch.setattr(transcriber._client.audio.transcriptions, "create", always_fail)
    with pytest.raises(RateLimitError):
        transcriber.transcribe_audio(audio)
    # Slept between attempts 1->2 and 2->3, but not after the final failure.
    assert len(no_sleep) == 2


def test_non_retryable_error_propagates_immediately(monkeypatch, tmp_path, no_sleep):
    audio = tmp_path / "a.wav"
    audio.write_bytes(b"RIFFfake")

    def boom(**kw):
        raise ValueError("bad audio format")

    monkeypatch.setattr(transcriber._client.audio.transcriptions, "create", boom)
    with pytest.raises(ValueError):
        transcriber.transcribe_audio(audio)
    assert no_sleep == []  # never retried
