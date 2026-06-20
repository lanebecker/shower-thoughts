"""
Obsidian adapter — writes a Markdown file into an Obsidian vault.

Strategies:
  "file"    — write directly to a local vault folder
  "webhook" — POST to Obsidian's Local REST API plugin

Required env vars (file): OBSIDIAN_VAULT_PATH
Required env vars (webhook): OBSIDIAN_API_URL, OBSIDIAN_API_KEY
"""

import os
import re
import logging
import requests
import urllib3
from pathlib import Path
from summarizer import Note

log = logging.getLogger(__name__)

STRATEGY        = os.getenv("OBSIDIAN_STRATEGY", "file")
OBSIDIAN_FOLDER = os.getenv("OBSIDIAN_FOLDER", "Shower Thoughts")

# The Obsidian Local REST API plugin serves HTTPS with a self-signed certificate,
# so the webhook call below uses verify=False. Silence the resulting urllib3
# warning since this is a trusted loopback/LAN endpoint, not a public URL.
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


class ObsidianAdapter:
    def send(self, note: Note) -> None:
        content  = _build_markdown(note)
        filename = _safe_filename(note.title, note.recorded_at)
        if STRATEGY == "webhook":
            _send_webhook(filename, content)
        else:
            _write_file(filename, content)


def _build_markdown(note: Note) -> str:
    tags_yaml = "\n".join(f"  - {t}" for t in note.tags)
    return f"""---
title: "{note.title}"
date: {note.recorded_at}
tags:\n{tags_yaml}
source: shower_thoughts
---

# {note.title}

> {note.summary}

## Full Transcript

{note.full_text}
"""


def _safe_filename(title: str, recorded_at: str) -> str:
    date_prefix = recorded_at[:10]
    safe_title  = re.sub(r'[^\w\s-]', '', title).strip().replace(' ', '-')
    return f"{date_prefix}-{safe_title}.md"


def _write_file(filename: str, content: str):
    vault_path = os.getenv("OBSIDIAN_VAULT_PATH")
    if not vault_path:
        raise EnvironmentError("Set OBSIDIAN_VAULT_PATH")
    folder = Path(vault_path) / OBSIDIAN_FOLDER
    folder.mkdir(parents=True, exist_ok=True)
    (folder / filename).write_text(content, encoding="utf-8")
    log.info(f"Obsidian note written: {filename}")


def _send_webhook(filename: str, content: str):
    api_url = os.getenv("OBSIDIAN_API_URL", "https://127.0.0.1:27123")
    api_key = os.getenv("OBSIDIAN_API_KEY", "")
    path    = f"{OBSIDIAN_FOLDER}/{filename}"
    resp = requests.put(
        f"{api_url}/vault/{path}",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "text/markdown"},
        data=content.encode("utf-8"),
        verify=False,
        # timeout guards the worker thread against a hung webhook socket (SEC-3).
        timeout=15,
    )
    resp.raise_for_status()
    log.info(f"Obsidian webhook: note created at {path}")
