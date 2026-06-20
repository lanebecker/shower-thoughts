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


# --------------------------------------------------------------------------- #
# Shared stubs. The pipeline does real network/disk I/O, so every test that
# exercises /upload wires these in. Kept here once instead of re-inlined per test.
# --------------------------------------------------------------------------- #


def stub_pipeline(monkeypatch, main_reloaded, *, transcript="hello transcript", received=None):
    """Wire transcribe/summarize/adapter to in-memory stubs (no real I/O).

    full_text mirrors the real summarize_thought contract (== transcript). Pass a
    list as `received` to capture the Note handed to the adapter.
    """
    monkeypatch.setattr(main_reloaded, "transcribe_audio", lambda p: transcript)

    def fake_summarize(t):
        note = make_note()
        note.full_text = t
        return note

    monkeypatch.setattr(main_reloaded, "summarize_thought", fake_summarize)

    class _Adapter:
        def send(self, note):
            if received is not None:
                received.append(note)

    monkeypatch.setattr(main_reloaded, "get_adapter", lambda: _Adapter())


def stub_noop_process(monkeypatch, main_reloaded):
    """Replace _process_job with a no-op so a saved WAV survives for inspection.

    The real _process_job unlinks the WAV in a finally block, and TestClient runs
    background tasks before returning the response.
    """

    async def _noop(job_id, audio_path):
        pass

    monkeypatch.setattr(main_reloaded, "_process_job", _noop)


def run_happy_upload(monkeypatch, client, main_reloaded):
    """Drive one successful upload through the stubbed pipeline; return job_id."""
    stub_pipeline(monkeypatch, main_reloaded)
    resp = client.post("/upload", files=WAV, headers={"X-Device-Token": "secret"})
    assert resp.status_code == 202
    return resp.json()["job_id"]


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
    stub_pipeline(monkeypatch, main_reloaded)
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
    stub_pipeline(monkeypatch, main_reloaded, received=received)

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


def test_jobs_list_empty(monkeypatch):
    _, client = fresh_client(monkeypatch, device_token="secret")
    resp = client.get("/jobs", headers={"X-Device-Token": "secret"})
    assert resp.status_code == 200
    assert resp.json() == {"jobs": []}


def test_jobs_list_requires_auth(monkeypatch):
    _, client = fresh_client(monkeypatch, device_token="secret")
    assert client.get("/jobs").status_code == 401


def test_jobs_list_returns_completed_note(monkeypatch):
    main_reloaded, client = fresh_client(monkeypatch, device_token="secret")
    job_id = run_happy_upload(monkeypatch, client, main_reloaded)

    resp = client.get("/jobs", headers={"X-Device-Token": "secret"})
    assert resp.status_code == 200
    jobs = resp.json()["jobs"]
    assert len(jobs) == 1
    job = jobs[0]
    assert job["id"] == job_id
    assert job["status"] == "done"
    assert job["title"] == "Idea"
    # tags round-trip back into a real list.
    assert job["tags"] == ["x", "y"]


def test_jobs_limit_param_validated(monkeypatch):
    _, client = fresh_client(monkeypatch, device_token="secret")
    # Out-of-range limit (max 200) should be a 422 validation error.
    assert client.get("/jobs?limit=999", headers={"X-Device-Token": "secret"}).status_code == 422


def test_job_persists_across_restart(monkeypatch, tmp_path):
    """A reload of main with the same JOBS_DB still sees a prior job (restart sim)."""
    db = str(tmp_path / "persist.db")
    monkeypatch.setenv("JOBS_DB", db)
    main_reloaded, client = fresh_client(monkeypatch, device_token="secret")
    job_id = run_happy_upload(monkeypatch, client, main_reloaded)

    # Simulate a backend restart: reload main against the same DB file.
    monkeypatch.setenv("JOBS_DB", db)
    main_again, client2 = fresh_client(monkeypatch, device_token="secret")
    resp = client2.get("/job/" + job_id, headers={"X-Device-Token": "secret"})
    assert resp.status_code == 200
    assert resp.json()["status"] == "done"


def test_upload_malformed_filename_is_client_error_not_500(monkeypatch):
    _, client = fresh_client(monkeypatch, device_token="secret")
    # A multipart audio part with an empty/missing filename must be rejected as
    # a clean client error (FastAPI validation 422, or our 400 guard) -- never a
    # 500 from calling .endswith on a None filename.
    resp = client.post(
        "/upload",
        files={"audio": ("", b"RIFFfake", "audio/wav")},
        headers={"X-Device-Token": "secret"},
    )
    assert resp.status_code in (400, 422)
    assert resp.status_code < 500


def test_upload_path_traversal_filename_stays_in_upload_dir(monkeypatch):
    """SEC-1: a `../` traversal filename must not escape UPLOAD_DIR.

    The storage name is generated server-side from job_id, so the attacker's
    filename is ignored entirely. We assert (a) the upload still succeeds, (b)
    the only file written lives inside UPLOAD_DIR and is named "<job_id>.wav",
    and (c) nothing landed at the traversal target outside the dir.
    """
    main_reloaded, client = fresh_client(monkeypatch, device_token="secret")
    # No-op the background pipeline so the saved WAV survives for inspection.
    stub_noop_process(monkeypatch, main_reloaded)

    upload_dir = main_reloaded.UPLOAD_DIR.resolve()
    evil_name = "_../../../../../../tmp/st_pwned.wav"
    resp = client.post(
        "/upload",
        files={"audio": (evil_name, b"RIFFfake", "audio/wav")},
        headers={"X-Device-Token": "secret"},
    )
    assert resp.status_code == 202
    job_id = resp.json()["job_id"]

    # The saved file is exactly "<job_id>.wav" inside UPLOAD_DIR...
    saved = upload_dir / f"{job_id}.wav"
    assert saved.exists()
    assert saved.resolve().parent == upload_dir
    # ...and the traversal target was never created.
    assert not (upload_dir / ".." / ".." / ".." / ".." / ".." / ".." / "tmp" / "st_pwned.wav").exists()


def test_upload_oversize_body_returns_413(monkeypatch):
    """SEC-2: a body over MAX_UPLOAD_BYTES is rejected with 413, no file left."""
    # Shrink the cap to 1 KiB so we don't have to ship 25 MB through the client.
    # fresh_client reloads main, which reads MAX_UPLOAD_BYTES at import time.
    monkeypatch.setenv("MAX_UPLOAD_BYTES", "1024")
    main_reloaded, client = fresh_client(monkeypatch, device_token="secret")

    big = b"RIFF" + b"\x00" * 5000  # ~5 KB, well over the 1 KiB cap
    resp = client.post(
        "/upload",
        files={"audio": ("thought.wav", big, "audio/wav")},
        headers={"X-Device-Token": "secret"},
    )
    assert resp.status_code == 413
    # Nothing should be left behind in the uploads dir.
    upload_dir = main_reloaded.UPLOAD_DIR
    assert not any(upload_dir.glob("*.wav"))


def test_upload_within_limit_still_accepted(monkeypatch):
    """SEC-2 sanity: a body under the cap streams to disk and is accepted."""
    monkeypatch.setenv("MAX_UPLOAD_BYTES", str(1024 * 1024))
    main_reloaded, client = fresh_client(monkeypatch, device_token="secret")
    stub_noop_process(monkeypatch, main_reloaded)

    resp = client.post(
        "/upload",
        files={"audio": ("thought.wav", b"RIFF" + b"\x00" * 2048, "audio/wav")},
        headers={"X-Device-Token": "secret"},
    )
    assert resp.status_code == 202
    job_id = resp.json()["job_id"]
    saved = main_reloaded.UPLOAD_DIR / f"{job_id}.wav"
    assert saved.exists()
    # The full body (RIFF header + 2048 zero bytes) made it to disk intact.
    assert saved.stat().st_size == 4 + 2048


def test_transcript_text_not_logged_by_default(monkeypatch, caplog):
    """SEC-6: transcript content must not reach the logs at default config."""
    main_reloaded, client = fresh_client(monkeypatch, device_token="secret")
    secret = "MY-SECRET-SHOWER-IDEA-42"
    stub_pipeline(monkeypatch, main_reloaded, transcript=secret)

    with caplog.at_level("INFO"):
        resp = client.post(
            "/upload", files=WAV, headers={"X-Device-Token": "secret"}
        )
        assert resp.status_code == 202

    # The transcript text itself never appears...
    assert secret not in caplog.text
    # ...but a length-only line confirms the stage still logs progress.
    assert "Transcribed" in caplog.text


def test_transcript_preview_logged_when_flag_enabled(monkeypatch, caplog):
    """SEC-6: opting into LOG_TRANSCRIPTS=1 restores a short preview for debugging."""
    monkeypatch.setenv("LOG_TRANSCRIPTS", "1")
    main_reloaded, client = fresh_client(monkeypatch, device_token="secret")
    phrase = "PREVIEW-ME-PLEASE"
    stub_pipeline(monkeypatch, main_reloaded, transcript=phrase)

    with caplog.at_level("INFO"):
        resp = client.post(
            "/upload", files=WAV, headers={"X-Device-Token": "secret"}
        )
        assert resp.status_code == 202

    assert phrase in caplog.text


def test_non_ascii_device_token_is_401_not_typeerror(monkeypatch):
    """Review follow-up: a non-ASCII token must yield a clean 401, never a 500.

    Starlette latin-1 decodes inbound header values, so a raw high byte (0xF6)
    reaches the handler as the str "ö". hmac.compare_digest raises TypeError on a
    non-ASCII str, so the buggy version turned that into an unhandled 500. We
    drive _check_auth directly because httpx refuses to transmit a non-ASCII
    header at all -- the bug lives below the transport, at this function.
    """
    from fastapi import HTTPException

    main_reloaded, _ = fresh_client(monkeypatch, device_token="secret")
    wire_value = bytes([0xF6]).decode("latin-1")  # what the wire byte decodes to
    with pytest.raises(HTTPException) as exc:
        main_reloaded._check_auth(wire_value)
    assert exc.value.status_code == 401  # not a TypeError bubbling up to 500


def test_upload_partial_file_cleaned_on_write_error(monkeypatch):
    """Review follow-up (SEC-2): a non-413 failure mid-stream must not orphan a WAV.

    We make the second chunk read raise a non-HTTPException; the handler should
    unlink the partial file (its except now catches any Exception, not just the
    413 path) and the uploads dir should be left clean.
    """
    import starlette.datastructures as ds

    main_reloaded, _ = fresh_client(monkeypatch, device_token="secret")
    client = TestClient(main_reloaded.app, raise_server_exceptions=False)

    state = {"n": 0}

    async def flaky_read(self, size=-1):
        state["n"] += 1
        if state["n"] == 1:
            return b"PARTIAL-BYTES"  # written to disk
        raise RuntimeError("simulated disk/stream failure")

    monkeypatch.setattr(ds.UploadFile, "read", flaky_read)

    resp = client.post(
        "/upload", files=WAV, headers={"X-Device-Token": "secret"}
    )
    assert resp.status_code >= 500  # the RuntimeError surfaces as a server error
    # ...but no partial WAV is left behind.
    assert not any(main_reloaded.UPLOAD_DIR.glob("*.wav"))


def test_oversize_body_rejected_by_middleware_before_auth(monkeypatch):
    """SEC-2 (C1): MaxBodySizeMiddleware 413s an oversize *declared* body before
    the handler runs at all -- so the body is never parsed/spooled. The guard
    sits ahead of auth on purpose (DoS protection shouldn't require a token), so
    we send no device token and still expect 413, not 401."""
    monkeypatch.setenv("MAX_UPLOAD_BYTES", "1024")
    main_reloaded, client = fresh_client(monkeypatch, device_token="secret")

    big = b"RIFF" + b"\x00" * 5000  # well over the 1 KiB cap
    resp = client.post("/upload", files={"audio": ("t.wav", big, "audio/wav")})
    assert resp.status_code == 413
    assert not any(main_reloaded.UPLOAD_DIR.glob("*.wav"))


def test_max_upload_bytes_bad_value_falls_back_to_default(monkeypatch):
    """S1: a non-integer MAX_UPLOAD_BYTES must not crash the app at import."""
    monkeypatch.setenv("MAX_UPLOAD_BYTES", "25MB")  # not an int
    main_reloaded, _ = fresh_client(monkeypatch, device_token="secret")
    assert main_reloaded.MAX_UPLOAD_BYTES == 25 * 1024 * 1024


def test_upload_cleans_wav_when_store_create_fails(monkeypatch):
    """S3: if the job-row INSERT fails after the WAV is written (e.g. a job_id
    collision or a SQLite error), the WAV must not be left orphaned on disk."""
    main_reloaded, _ = fresh_client(monkeypatch, device_token="secret")
    client = TestClient(main_reloaded.app, raise_server_exceptions=False)

    def boom(*a, **k):
        raise RuntimeError("simulated job-store INSERT failure")

    monkeypatch.setattr(main_reloaded._store, "create", boom)
    resp = client.post("/upload", files=WAV, headers={"X-Device-Token": "secret"})
    assert resp.status_code >= 500
    assert not any(main_reloaded.UPLOAD_DIR.glob("*.wav"))
