"""
Thought structuring via Claude (Anthropic) or GPT-4.
Takes a raw transcript and returns a structured Note object.
"""

import os
import json
import logging
from dataclasses import dataclass
from datetime import datetime

log = logging.getLogger(__name__)

AI_PROVIDER = os.getenv("AI_PROVIDER", "anthropic")  # "anthropic" | "openai"


@dataclass
class Note:
    title:       str
    summary:     str
    full_text:   str
    tags:        list[str]
    recorded_at: str


_SYSTEM_PROMPT = """You are a helpful assistant that structures raw spoken thoughts
recorded in the shower. The input is a raw transcript that may be rambling,
unfiltered, or stream-of-consciousness. Your job is to:

1. Give it a concise, descriptive title (max 8 words)
2. Write a 1-2 sentence summary of the core idea
3. Suggest 2-4 relevant tags (lowercase, no #)

Respond ONLY with valid JSON matching this schema:
{
  "title": "string",
  "summary": "string",
  "tags": ["string"]
}"""


def summarize_thought(transcript: str) -> Note:
    recorded_at = datetime.now().isoformat()
    if AI_PROVIDER == "anthropic":
        structured = _call_claude(transcript)
    else:
        structured = _call_openai(transcript)
    return Note(
        title=structured["title"],
        summary=structured["summary"],
        full_text=transcript,
        tags=structured.get("tags", []),
        recorded_at=recorded_at,
    )


def _call_claude(transcript: str) -> dict:
    import anthropic
    client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
    message = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=512,
        system=_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": transcript}],
    )
    return json.loads(message.content[0].text)


def _call_openai(transcript: str) -> dict:
    from openai import OpenAI
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user",   "content": transcript},
        ],
    )
    return json.loads(response.choices[0].message.content)
