"""
Tests for the FastAPI app in main.py via TestClient.

main.py reads DEVICE_TOKEN and ALLOW_NO_DEVICE_TOKEN at import time, so each
auth scenario sets the env vars then reloads the module to pick up the new
config, returning a fresh TestClient bound to the reloaded app.
"""

import importlib

import pytest
from fastapi.testclient import TestClient

import main as main_module
import summarizer


def make_note():
    return summarizer.Note(
        title="Idea",
        summary="A summary",
        full_text="full text here",
        tags=["x", "y"],
        recorded_at="2026-06-15T10:00:00",
    )


def fresh_client(monkeypatch, *, device_token=None, allow_no_token=None):
    """Set env, reload main, and return (reloaded_main, TestClient)."""
    if device_token is None:
        monkeypatch.delenv("DEVICE_TOKEN", raising=False)
    else:
        monkeypatch.setenv("DEVICE_TOKEN", device_token)

    if allow_no_token is None:
        monkeypatch.delenv("ALLOW_NO_DEVICE_TOKEN", raising=False)
    else:
        monkeypatch.setenv("ALLOW_NO_DEVICE_TOKEN", allow_no_token)

    reloaded = importlib.reload(main_module)
    return reloaded, TestClient(reloaded.app)


WAV = {"audio": ("thought.wav", b"RIFFfake", "audio/wav")}


def test_health_ok(monkeypatch):
    _, client = fresh_client(monkeypatch, device_token="secret")
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_upload_no_token_unset_allow_returns_503(monkeypatch):
    _, client = fresh_client(monkeypatch, device_token=None, allow_no_token=None)
    resp = client.post("/upload", files=WAV)
    assert resp.status_code == 503


def test_upload_no_token_with_allow_returns_202(monkeypatch):
    main_reloaded, client = fresh_client(
        monkeypatch, device_token=None, allow_no_token="1"
    )
    # Stub the pipeline so the background task can't do real I/O.
    monkeypatch.setattr(main_reloaded, "transcribe_audio", lambda p: "t")
    monkeypatch.setattr(main_reloaded, "summarize_thought", lambda t: make_note())

    class _Adapter:
        def send(self, note):
            pass

    monkeypatch.setattr(main_reloaded, "get_adapter", lambda: _Adapter())
    resp = client.post("/upload", files=WAV)
    assert resp.status_code == 202


def test_upload_missing_header_returns_401(monkeypatch):
    _, client = fresh_client(monkeypatch, device_token="secret")
    resp = client.post("/upload", files=WAV)
    assert resp.status_code == 401


def test_upload_wrong_header_returns_401(monkeypatch):
    _, client = fresh_client(monkeypatch, device_token="secret")
    resp = client.post("/upload", files=WAV, headers={"X-Device-Token": "nope"})
    assert resp.status_code == 401


def test_upload_non_wav_returns_400(monkeypatch):
    _, client = fresh_client(monkeypatch, device_token="secret")
    resp = client.post(
        "/upload",
        files={"audio": ("thought.mp3", b"data", "audio/mpeg")},
        headers={"X-Device-Token": "secret"},
    )
    assert resp.status_code == 400


def test_upload_happy_path_runs_pipeline(monkeypatch):
    main_reloaded, client = fresh_client(monkeypatch, device_token="secret")

    received = []

    class _Adapter:
        def send(self, note):
            received.append(note)

    monkeypatch.setattr(main_reloaded, "transcribe_audio", lambda p: "hello transcript")

    # Mirror the real summarize_thought contract: full_text is the transcript.
    def fake_summarize(transcript):
        note = make_note()
        note.full_text = transcript
        return note

    monkeypatch.setattr(main_reloaded, "summarize_thought", fake_summarize)
    monkeypatch.setattr(main_reloaded, "get_adapter", lambda: _Adapter())

    resp = client.post("/upload", files=WAV, headers={"X-Device-Token": "secret"})
    assert resp.status_code == 202
    body = resp.json()
    assert "job_id" in body
    job_id = body["job_id"]

    # TestClient runs background tasks before returning the response, so by now
    # the job should have completed.
    job_resp = client.get("/job/" + job_id, headers={"X-Device-Token": "secret"})
    assert job_resp.status_code == 200
    status = job_resp.json()["status"]
    assert status in {"queued", "transcribing", "summarizing", "delivering", "done"}
    assert status == "done"

    assert len(received) == 1
    assert received[0].full_text == "hello transcript"


def test_get_unknown_job_returns_404(monkeypatch):
    _, client = fresh_client(monkeypatch, device_token="secret")
    resp = client.get("/job/unknownid", headers={"X-Device-Token": "secret"})
    assert resp.status_code == 404
