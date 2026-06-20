"""
ShowerThoughts Backend API
FastAPI server that receives audio, transcribes, summarizes, and routes to notes.

Endpoints:
  POST /upload      — device uploads a WAV file, gets back a job_id
  GET  /job/{id}    — check job status
  GET  /jobs        — list recent jobs / notes (newest first)
  GET  /health      — liveness check
"""

import os
import hmac
import json
import uuid
import logging
import asyncio
from pathlib import Path
from datetime import datetime
from typing import Optional

from fastapi import FastAPI, UploadFile, File, HTTPException, Header, BackgroundTasks, Query
from fastapi.responses import JSONResponse
from dotenv import load_dotenv

from transcriber import transcribe_audio
from summarizer import summarize_thought
from adapters.registry import get_adapter
from jobs import JobStore

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

app = FastAPI(title="ShowerThoughts", version="0.2.1")

UPLOAD_DIR   = Path(os.getenv("UPLOAD_DIR", "/tmp/shower_uploads"))
DEVICE_TOKEN = os.getenv("DEVICE_TOKEN", "")
# Uploads are authenticated with a shared DEVICE_TOKEN. If it's unset we reject
# requests by default, so an unconfigured server isn't left wide open on the LAN
# (anyone could POST audio and burn your API credits). Set ALLOW_NO_DEVICE_TOKEN=1
# only for throwaway local testing.
ALLOW_NO_DEVICE_TOKEN = os.getenv("ALLOW_NO_DEVICE_TOKEN", "").lower() in ("1", "true", "yes")
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

# Max accepted upload size. The device caps clips at MAX_DURATION_S (~9.6 MB),
# so 25 MB is comfortable headroom while still bounding a hostile/buggy client
# that POSTs a multi-GB body to OOM the single worker (SEC-2). Tunable via env.
MAX_UPLOAD_BYTES = int(os.getenv("MAX_UPLOAD_BYTES", str(25 * 1024 * 1024)))
# Chunk size for streaming the body to disk (1 MiB).
_UPLOAD_CHUNK = 1024 * 1024

# Shower thoughts are personal by definition, so transcript *content* is never
# logged by default -- only its length (SEC-6). Set LOG_TRANSCRIPTS=1 to opt into
# logging a short preview when actively debugging.
LOG_TRANSCRIPTS = os.getenv("LOG_TRANSCRIPTS", "").lower() in ("1", "true", "yes")

# Persistent job store (SQLite). Defaults to a file alongside the uploads dir.
# Job rows survive a backend restart -- the in-memory dict used through v0.1.x
# did not. See jobs.py for the single-worker scope note.
JOBS_DB = os.getenv("JOBS_DB", str(UPLOAD_DIR / "jobs.db"))
_store  = JobStore(JOBS_DB)

if not DEVICE_TOKEN:
    if ALLOW_NO_DEVICE_TOKEN:
        log.warning("DEVICE_TOKEN is not set and ALLOW_NO_DEVICE_TOKEN is enabled — "
                    "uploads are UNAUTHENTICATED. Don't expose this on an untrusted network.")
    else:
        log.warning("DEVICE_TOKEN is not set — uploads will be rejected with 503. "
                    "Set DEVICE_TOKEN (or ALLOW_NO_DEVICE_TOKEN=1 for local testing).")

# NOTE: job processing runs as an in-process FastAPI BackgroundTask, so run a
# SINGLE uvicorn worker. Job *state* now lives in SQLite (see jobs.py) and so
# survives a restart, but the background worker pool does not coordinate across
# processes. Multi-worker is a deliberate non-goal -- see CLAUDE.md invariants.


def _check_auth(x_device_token: Optional[str]):
    if not DEVICE_TOKEN:
        if ALLOW_NO_DEVICE_TOKEN:
            return
        raise HTTPException(
            status_code=503,
            detail="Server has no DEVICE_TOKEN configured. Set DEVICE_TOKEN "
                   "(or ALLOW_NO_DEVICE_TOKEN=1 for local testing).",
        )
    # Constant-time comparison so the check can't be timing-probed byte by byte
    # (SEC-4). Compare the UTF-8 *bytes*: hmac.compare_digest raises TypeError on
    # a str containing non-ASCII chars, and inbound header values are latin-1
    # decoded, so a raw high byte in X-Device-Token would otherwise turn a clean
    # 401 into an unhandled 500. Encoding both sides sidesteps that entirely.
    if not hmac.compare_digest((x_device_token or "").encode("utf-8"), DEVICE_TOKEN.encode("utf-8")):
        raise HTTPException(status_code=401, detail="Invalid device token")


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/upload")
async def upload_audio(
    background_tasks: BackgroundTasks,
    audio: UploadFile = File(...),
    x_device_token: Optional[str] = Header(None),
    content_length: Optional[int] = Header(None),
):
    _check_auth(x_device_token)
    # Cheap early reject: if the client declares an oversize body, 413 before we
    # read a single byte. Content-Length is client-supplied (may be absent or
    # lie), so this is only an optimization -- the streaming guard below is the
    # real enforcement.
    if content_length is not None and content_length > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="Upload too large")
    # audio.filename can be None for a multipart part without a filename;
    # coerce so a malformed upload returns a clean 400 rather than a 500.
    if not (audio.filename or "").endswith(".wav"):
        raise HTTPException(status_code=400, detail="Only WAV files accepted")
    # 48 bits of randomness (12 hex). job_id is both the DB primary key and the
    # entire on-disk filename (SEC-1), so a birthday collision would 500 on the
    # INSERT and overwrite a WAV; 12 hex keeps that probability negligible.
    job_id    = uuid.uuid4().hex[:12]
    timestamp = datetime.now().isoformat()
    # Storage name is generated entirely server-side. audio.filename is
    # attacker-controlled and must never participate in the path -- a crafted
    # name like "_../../../home/pi/.ssh/authorized_keys.wav" would otherwise
    # escape UPLOAD_DIR (SEC-1, path traversal). job_id is a server-side uuid4
    # slice, so the name is a fixed "<8 hex>.wav" with no traversal surface.
    save_path = UPLOAD_DIR / f"{job_id}.wav"
    # Defense in depth: assert the resolved path stays inside UPLOAD_DIR before
    # writing, so any future change to the naming scheme can't silently regress.
    if not save_path.resolve().is_relative_to(UPLOAD_DIR.resolve()):
        raise HTTPException(status_code=400, detail="Invalid upload path")
    # Stream the body to disk in bounded chunks rather than buffering the whole
    # upload in RAM (SEC-2). We count bytes as we go and abort with 413 the
    # instant the cap is exceeded, deleting the partial file so a rejected
    # upload leaves nothing behind.
    written = 0
    try:
        with save_path.open("wb") as dst:
            while True:
                chunk = await audio.read(_UPLOAD_CHUNK)
                if not chunk:
                    break
                written += len(chunk)
                if written > MAX_UPLOAD_BYTES:
                    raise HTTPException(status_code=413, detail="Upload too large")
                dst.write(chunk)
    except Exception:
        # Any failure before the job is enqueued -- the 413 guard, a disk error,
        # or a mid-stream client disconnect -- must not leave a partial WAV
        # behind. _process_job's finally-unlink never runs (we haven't scheduled
        # it yet), so we clean up here and re-raise.
        save_path.unlink(missing_ok=True)
        raise
    log.info(f"[{job_id}] Received {written/1024:.1f}KB audio")
    _store.create(job_id, timestamp)
    background_tasks.add_task(_process_job, job_id, save_path)
    return JSONResponse({"job_id": job_id, "status": "queued"}, status_code=202)


@app.get("/job/{job_id}")
async def get_job(job_id: str, x_device_token: Optional[str] = Header(None)):
    _check_auth(x_device_token)
    job = _store.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@app.get("/jobs")
async def list_jobs(
    limit: int = Query(50, ge=1, le=200),
    x_device_token: Optional[str] = Header(None),
):
    _check_auth(x_device_token)
    return {"jobs": _store.list_recent(limit)}


async def _process_job(job_id: str, audio_path: Path):
    try:
        _store.update(job_id, status="transcribing")
        transcript = await asyncio.to_thread(transcribe_audio, audio_path)
        _store.update(job_id, transcript=transcript)
        if LOG_TRANSCRIPTS:
            log.info(f"[{job_id}] Transcript ({len(transcript)} chars): {transcript[:100]}...")
        else:
            log.info(f"[{job_id}] Transcribed {len(transcript)} chars")

        _store.update(job_id, status="summarizing")
        note = await asyncio.to_thread(summarize_thought, transcript)
        _store.update(
            job_id,
            title=note.title,
            summary=note.summary,
            tags=json.dumps(note.tags),
            recorded_at=note.recorded_at,
        )

        _store.update(job_id, status="delivering")
        adapter = get_adapter()
        await asyncio.to_thread(adapter.send, note)

        _store.update(job_id, status="done")
        log.info(f"[{job_id}] ✅ Done")
    except Exception as e:
        log.exception(f"[{job_id}] Processing failed: {e}")
        _store.update(job_id, status="error", error=str(e))
    finally:
        try:
            audio_path.unlink()
        except Exception:
            pass
