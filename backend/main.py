"""
ShowerThoughts Backend API
FastAPI server that receives audio, transcribes, summarizes, and routes to notes.

Endpoints:
  POST /upload      — device uploads a WAV file, gets back a job_id
  GET  /job/{id}    — check job status
  GET  /health      — liveness check
"""

import os
import uuid
import logging
import asyncio
from pathlib import Path
from datetime import datetime
from typing import Optional

from fastapi import FastAPI, UploadFile, File, HTTPException, Header, BackgroundTasks
from fastapi.responses import JSONResponse
from dotenv import load_dotenv

from transcriber import transcribe_audio
from summarizer import summarize_thought
from adapters.registry import get_adapter

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

app = FastAPI(title="ShowerThoughts", version="0.1.1")

UPLOAD_DIR   = Path(os.getenv("UPLOAD_DIR", "/tmp/shower_uploads"))
DEVICE_TOKEN = os.getenv("DEVICE_TOKEN", "")
# Uploads are authenticated with a shared DEVICE_TOKEN. If it's unset we reject
# requests by default, so an unconfigured server isn't left wide open on the LAN
# (anyone could POST audio and burn your API credits). Set ALLOW_NO_DEVICE_TOKEN=1
# only for throwaway local testing.
ALLOW_NO_DEVICE_TOKEN = os.getenv("ALLOW_NO_DEVICE_TOKEN", "").lower() in ("1", "true", "yes")
UPLOAD_DIR.mkdir(exist_ok=True)

if not DEVICE_TOKEN:
    if ALLOW_NO_DEVICE_TOKEN:
        log.warning("DEVICE_TOKEN is not set and ALLOW_NO_DEVICE_TOKEN is enabled — "
                    "uploads are UNAUTHENTICATED. Don't expose this on an untrusted network.")
    else:
        log.warning("DEVICE_TOKEN is not set — uploads will be rejected with 503. "
                    "Set DEVICE_TOKEN (or ALLOW_NO_DEVICE_TOKEN=1 for local testing).")

# NOTE: job state is an in-memory dict, so run a SINGLE uvicorn worker. With
# multiple workers each process keeps its own _jobs, so GET /job/{id} can miss a
# job handled by another worker, and a restart drops in-flight jobs. A persistent
# SQLite job store is planned for v0.2.
_jobs: dict[str, dict] = {}


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
    if not audio.filename.endswith(".wav"):
        raise HTTPException(status_code=400, detail="Only WAV files accepted")
    job_id    = str(uuid.uuid4())[:8]
    timestamp = datetime.now().isoformat()
    save_path = UPLOAD_DIR / f"{job_id}_{audio.filename}"
    contents  = await audio.read()
    save_path.write_bytes(contents)
    log.info(f"[{job_id}] Received {len(contents)/1024:.1f}KB audio")
    _jobs[job_id] = {"id": job_id, "status": "queued", "created_at": timestamp}
    background_tasks.add_task(_process_job, job_id, save_path)
    return JSONResponse({"job_id": job_id, "status": "queued"}, status_code=202)


@app.get("/job/{job_id}")
async def get_job(job_id: str, x_device_token: Optional[str] = Header(None)):
    _check_auth(x_device_token)
    job = _jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


async def _process_job(job_id: str, audio_path: Path):
    job = _jobs[job_id]
    try:
        job["status"] = "transcribing"
        transcript = await asyncio.to_thread(transcribe_audio, audio_path)
        job["transcript"] = transcript
        log.info(f"[{job_id}] Transcript: {transcript[:100]}...")

        job["status"] = "summarizing"
        note = await asyncio.to_thread(summarize_thought, transcript)

        job["status"] = "delivering"
        adapter = get_adapter()
        await asyncio.to_thread(adapter.send, note)

        job["status"] = "done"
        log.info(f"[{job_id}] ✅ Done")
    except Exception as e:
        log.exception(f"[{job_id}] Processing failed: {e}")
        job["status"] = "error"
        job["error"]  = str(e)
    finally:
        try:
            audio_path.unlink()
        except Exception:
            pass
