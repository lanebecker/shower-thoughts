"""
Craft adapter — creates a new document in Craft Docs.

Craft has no public REST API, so two strategies are supported:

Strategy A: "url_scheme" (macOS only)
  Opens craftdocs://createdocument via AppleScript.
  Backend must run on the same Mac as Craft.

Strategy B: "shortcuts" (macOS / iOS)
  POSTs note data to a local Apple Shortcuts webhook listener.
  Use Shortery (https://www.numberfive.co/shortery) to expose the Shortcut as HTTP.

Required env vars:
  CRAFT_SPACE_ID               — Craft → Settings → tap space name → copy ID
  CRAFT_SHORTCUTS_WEBHOOK_URL  — (shortcuts strategy only)
"""

import os
import logging
import subprocess
import requests
from urllib.parse import quote
from summarizer import Note

log = logging.getLogger(__name__)

STRATEGY       = os.getenv("CRAFT_STRATEGY", "url_scheme")
CRAFT_SPACE_ID = os.getenv("CRAFT_SPACE_ID", "")


class CraftAdapter:
    def send(self, note: Note) -> None:
        if STRATEGY == "shortcuts":
            _send_shortcuts(note)
        else:
            _send_url_scheme(note)


def _build_markdown(note: Note) -> str:
    tags_inline = "  ".join(f"#{t}" for t in note.tags)
    return f"""## {note.summary}\n\n{note.full_text}\n\n---\n*Recorded: {note.recorded_at}*\n{tags_inline}\n"""


def _send_url_scheme(note: Note):
    if not CRAFT_SPACE_ID:
        raise EnvironmentError("Set CRAFT_SPACE_ID")
    title   = f"🚿 {note.title}"
    content = _build_markdown(note)
    url = (
        f"craftdocs://createdocument"
        f"?spaceId={quote(CRAFT_SPACE_ID, safe='')}"
        f"&title={quote(title, safe='')}"
        f"&content={quote(content, safe='')}"
    )
    # timeout so a wedged osascript can't pin a worker thread forever (SEC-3).
    try:
        result = subprocess.run(
            ["osascript", "-e", f'open location "{url}"'],
            capture_output=True,
            text=True,
            timeout=15,
        )
    except subprocess.TimeoutExpired:
        raise RuntimeError("AppleScript timed out (Craft unresponsive?)")
    if result.returncode != 0:
        raise RuntimeError(f"AppleScript failed: {result.stderr.strip()}")
    log.info(f"Craft document created: '{note.title}'")


def _send_shortcuts(note: Note):
    webhook_url = os.getenv("CRAFT_SHORTCUTS_WEBHOOK_URL")
    if not webhook_url:
        raise EnvironmentError("Set CRAFT_SHORTCUTS_WEBHOOK_URL")
    payload = {
        "title":       f"🚿 {note.title}",
        "summary":     note.summary,
        "full_text":   note.full_text,
        "tags":        note.tags,
        "recorded_at": note.recorded_at,
        "space_id":    CRAFT_SPACE_ID,
        "markdown":    _build_markdown(note),
    }
    resp = requests.post(webhook_url, json=payload, timeout=15)
    resp.raise_for_status()
    log.info(f"Craft note dispatched via Shortcuts webhook: '{note.title}'")
