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

app = FastAPI(title="ShowerThoughts", version="0.2.0")

UPLOAD_DIR   = Path(os.getenv("UPLOAD_DIR", "/tmp/shower_uploads"))
DEVICE_TOKEN = os.getenv("DEVICE_TOKEN", "")
# Uploads are authenticated with a shared DEVICE_TOKEN. If it's unset we reject
# requests by default, so an unconfigured server isn't left wide open on the LAN
# (anyone could POST audio and burn your API credits). Set ALLOW_NO_DEVICE_TOKEN=1
# only for throwaway local testing.
ALLOW_NO_DEVICE_TOKEN = os.getenv("ALLOW_NO_DEVICE_TOKEN", "").lower() in ("1", "true", "yes")
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

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
    if x_device_token != DEVICE_TOKEN:
        raise HTTPException(status_code=401, detail="Invalid device token")


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/upload")
async def upload_audio(
    background_tasks: BackgroundTasks,
    audio: UploadFile = File(...),
    x_device_token: Optional[str] = Header(None),
):
    _check_auth(x_device_token)
    # audio.filename can be None for a multipart part without a filename;
    # coerce so a malformed upload returns a clean 400 rather than a 500.
    if not (audio.filename or "").endswith(".wav"):
        raise HTTPException(status_code=400, detail="Only WAV files accepted")
    job_id    = str(uuid.uuid4())[:8]
    timestamp = datetime.now().isoformat()
    save_path = UPLOAD_DIR / f"{job_id}_{audio.filename}"
    contents  = await audio.read()
    save_path.write_bytes(contents)
    log.info(f"[{job_id}] Received {len(contents)/1024:.1f}KB audio")
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
        log.info(f"[{job_id}] Transcript: {transcript[:100]}...")

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
