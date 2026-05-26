"""
Apple Notes adapter — two strategies:

Strategy A (recommended): SMTP → iCloud Mail → Apple Notes
  Set APPLE_NOTES_EMAIL to your notes@icloud.com address.

Strategy B: macOS-only AppleScript.
  Only works if the backend is running on a Mac.
"""

import os
import logging
import smtplib
import subprocess
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from summarizer import Note

log = logging.getLogger(__name__)
STRATEGY = os.getenv("APPLE_NOTES_STRATEGY", "email")


class AppleNotesAdapter:
    def send(self, note: Note) -> None:
        if STRATEGY == "applescript":
            _send_applescript(note)
        else:
            _send_email(note)


def _send_email(note: Note):
    smtp_host  = os.getenv("SMTP_HOST", "smtp.gmail.com")
    smtp_port  = int(os.getenv("SMTP_PORT", "587"))
    smtp_user  = os.getenv("SMTP_USER")
    smtp_pass  = os.getenv("SMTP_PASS")
    dest_email = os.getenv("APPLE_NOTES_EMAIL")
    if not all([smtp_user, smtp_pass, dest_email]):
        raise EnvironmentError("Set SMTP_USER, SMTP_PASS, APPLE_NOTES_EMAIL")
    tags_str = ", ".join(f"#{t}" for t in note.tags)
    body = f"""🚿 Shower Thought — {note.recorded_at}\n\n{note.summary}\n\n---\n{note.full_text}\n\nTags: {tags_str}"""
    msg = MIMEMultipart()
    msg["From"]    = smtp_user
    msg["To"]      = dest_email
    msg["Subject"] = f"💡 {note.title}"
    msg.attach(MIMEText(body, "plain"))
    with smtplib.SMTP(smtp_host, smtp_port) as server:
        server.starttls()
        server.login(smtp_user, smtp_pass)
        server.sendmail(smtp_user, dest_email, msg.as_string())
    log.info(f"Note emailed to {dest_email}: '{note.title}'")


def _send_applescript(note: Note):
    tags_str = ", ".join(note.tags)
    body = f"🚿 {note.recorded_at}\n\n{note.summary}\n\n{note.full_text}\n\nTags: {tags_str}"
    escaped_title = note.title.replace('"', '\\"')
    escaped_body  = body.replace('"', '\\"').replace("\n", "\\n")
    script = f'''
    tell application "Notes"
        tell account "iCloud"
            make new note at folder "Shower Thoughts" with properties {{
                name: "{escaped_title}", body: "{escaped_body}"
            }}
        end tell
    end tell
    '''
    result = subprocess.run(["osascript", "-e", script], capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"AppleScript failed: {result.stderr}")
    log.info(f"Note created in Apple Notes: '{note.title}'")
