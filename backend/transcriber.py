"""
Audio transcription via OpenAI Whisper API.
Swap this module out if you want local Whisper (whisper.cpp or whisper-python).

Rate limits & timeouts (v0.2.0): the Whisper API can return 429s when you've hit
your account's request/token rate, and a slow network can stall a request. Both
are transient, so transcribe_audio retries with exponential backoff, honoring a
``Retry-After`` header when the API supplies one. Tunables (env vars):

  WHISPER_MAX_RETRIES       total attempts before giving up        (default 3)
  WHISPER_RETRY_BASE_DELAY  base seconds for backoff: base*2**n    (default 2.0)
  WHISPER_TIMEOUT           per-request timeout in seconds         (default 60)
"""

import os
import time
import logging
from pathlib import Path

from openai import OpenAI, RateLimitError, APITimeoutError, APIConnectionError

log = logging.getLogger(__name__)
_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

WHISPER_MAX_RETRIES      = int(os.getenv("WHISPER_MAX_RETRIES", "3"))
WHISPER_RETRY_BASE_DELAY = float(os.getenv("WHISPER_RETRY_BASE_DELAY", "2.0"))
WHISPER_TIMEOUT          = float(os.getenv("WHISPER_TIMEOUT", "60"))

# Transient API failures worth retrying. A plain APIError (e.g. 400 bad audio)
# is NOT retried -- retrying it just wastes time and credits.
_RETRYABLE = (RateLimitError, APITimeoutError, APIConnectionError)


def _retry_after_seconds(exc, fallback: float) -> float:
    """Honor a Retry-After header if the API sent one; else use the fallback."""
    response = getattr(exc, "response", None)
    headers = getattr(response, "headers", None)
    if not headers:
        return fallback
    raw = headers.get("retry-after")
    if raw is None:
        return fallback
    try:
        return max(float(raw), fallback)
    except (TypeError, ValueError):
        return fallback


def transcribe_audio(audio_path: Path) -> str:
    log.info(f"Sending to Whisper: {audio_path.name}")
    last_exc = None
    for attempt in range(1, WHISPER_MAX_RETRIES + 1):
        try:
            with open(audio_path, "rb") as f:
                response = _client.audio.transcriptions.create(
                    model="whisper-1",
                    file=f,
                    language="en",
                    response_format="text",
                    timeout=WHISPER_TIMEOUT,
                )
            return response.strip()
        except _RETRYABLE as exc:
            last_exc = exc
            if attempt >= WHISPER_MAX_RETRIES:
                break
            backoff = WHISPER_RETRY_BASE_DELAY * (2 ** (attempt - 1))
            delay = _retry_after_seconds(exc, backoff)
            log.warning(
                f"Whisper {type(exc).__name__} on attempt {attempt}/"
                f"{WHISPER_MAX_RETRIES}; retrying in {delay:.1f}s"
            )
            time.sleep(delay)
    log.error(f"Whisper failed after {WHISPER_MAX_RETRIES} attempts: {last_exc}")
    raise last_exc


# Local Whisper alternative (uncomment to use — free, private, slower on CPU):
#
# import whisper
# _model = whisper.load_model("base.en")  # or "small.en", "medium.en"
#
# def transcribe_audio(audio_path: Path) -> str:
#     result = _model.transcribe(str(audio_path), language="en")
#     return result["text"].strip()
