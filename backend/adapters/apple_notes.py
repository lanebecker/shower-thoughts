"""
Apple Notes adapter (macOS only).

Creates notes directly in Apple Notes by driving the Notes app via AppleScript.
The backend must run on a Mac that is signed into iCloud with the Notes app
available.

IMPORTANT: there is no way to create an Apple Note by sending an email. Apple
does not offer an email-to-Notes ingestion address (the old MobileMe feature
was retired years ago). The previous "email" strategy here never actually
landed notes in Apple Notes. If you want thoughts delivered by email instead,
use a dedicated email adapter (NOTES_ADAPTER=email) rather than this one.
"""

import os
import logging
import subprocess
from html import escape as html_escape

from summarizer import Note

log = logging.getLogger(__name__)

# iCloud folder to file thoughts under; auto-created on first run if missing.
NOTES_FOLDER = os.getenv("APPLE_NOTES_FOLDER", "Shower Thoughts")


class AppleNotesAdapter:
    """Sends a Note to Apple Notes on the local Mac via `osascript`."""

    def send(self, note: Note) -> None:
        script = _build_script(note.title, _build_html(note), NOTES_FOLDER)
        result = subprocess.run(
            ["osascript", "-"],
            input=script,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise RuntimeError(f"AppleScript failed: {result.stderr.strip()}")
        log.info("Note created in Apple Notes (folder %r): %r", NOTES_FOLDER, note.title)


def _build_html(note: Note) -> str:
    """Apple Notes renders the body as HTML, so emit HTML (not plain text)."""
    tags = " ".join(f"#{html_escape(t)}" for t in note.tags)
    parts = [
        f"<div><b>{html_escape(note.title)}</b></div>",
        f"<div>\U0001F6BF {html_escape(str(note.recorded_at))}</div>",
        "<div><br></div>",
        f"<div>{html_escape(note.summary)}</div>",
        "<div><br></div>",
        f"<div>{html_escape(note.full_text)}</div>",
    ]
    if tags:
        parts += ["<div><br></div>", f"<div>{tags}</div>"]
    return "".join(parts)


def _osa_quote(s: str) -> str:
    """Escape a Python string for embedding in an AppleScript double-quoted literal."""
    return s.replace("\\", "\\\\").replace('"', '\\"')


def _build_script(title: str, body_html: str, folder: str) -> str:
    t = _osa_quote(title)
    b = _osa_quote(body_html)
    f = _osa_quote(folder)
    return f'''
tell application "Notes"
    tell account "iCloud"
        if not (exists folder "{f}") then
            make new folder with properties {{name:"{f}"}}
        end if
        make new note at folder "{f}" with properties {{name:"{t}", body:"{b}"}}
    end tell
end tell
'''
