"""
Audio transcription via OpenAI Whisper API.
Swap this module out if you want local Whisper (whisper.cpp or whisper-python).
"""

import os
import logging
from pathlib import Path
from openai import OpenAI

log = logging.getLogger(__name__)
_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


def transcribe_audio(audio_path: Path) -> str:
    log.info(f"Sending to Whisper: {audio_path.name}")
    with open(audio_path, "rb") as f:
        response = _client.audio.transcriptions.create(
            model="whisper-1",
            file=f,
            language="en",
            response_format="text",
        )
    return response.strip()


# Local Whisper alternative (uncomment to use — free, private, slower on CPU):
#
# import whisper
# _model = whisper.load_model("base.en")  # or "small.en", "medium.en"
#
# def transcribe_audio(audio_path: Path) -> str:
#     result = _model.transcribe(str(audio_path), language="en")
#     return result["text"].strip()
