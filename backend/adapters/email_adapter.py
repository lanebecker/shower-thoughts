"""
Email adapter — sends each thought to a plain email address over SMTP.

Use this for any "notes via email" workflow. NOTE: this is NOT a way to create
Apple Notes — Apple offers no email-to-Notes address. For Apple Notes use
NOTES_ADAPTER=apple_notes with the backend running on a Mac.

Required env vars: EMAIL_TO, SMTP_HOST, SMTP_USER, SMTP_PASS
Optional env vars: SMTP_PORT (default 587), EMAIL_FROM (default SMTP_USER)
"""

import os
import ssl
import logging
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

from summarizer import Note

log = logging.getLogger(__name__)

# Built once at import: create_default_context() loads the system CA bundle, so
# there's no reason to rebuild it on every send (SEC-5). A default context is
# stateless across uses, so sharing one instance is safe.
_SSL_CONTEXT = ssl.create_default_context()


class EmailAdapter:
    def send(self, note: Note) -> None:
        host      = os.getenv("SMTP_HOST")
        port      = int(os.getenv("SMTP_PORT", "587"))
        user      = os.getenv("SMTP_USER")
        password  = os.getenv("SMTP_PASS")
        to_addr   = os.getenv("EMAIL_TO")
        from_addr = os.getenv("EMAIL_FROM", user or "")
        if not all([host, user, password, to_addr]):
            raise EnvironmentError("Set SMTP_HOST, SMTP_USER, SMTP_PASS, and EMAIL_TO")

        tags = ", ".join(f"#{t}" for t in note.tags)
        body = (
            f"\U0001F6BF Shower Thought — {note.recorded_at}\n\n"
            f"{note.summary}\n\n"
            f"---\n{note.full_text}\n\n"
            f"Tags: {tags}"
        )
        msg = MIMEMultipart()
        msg["From"]    = from_addr
        msg["To"]      = to_addr
        msg["Subject"] = f"\U0001F4A1 {note.title}"
        msg.attach(MIMEText(body, "plain"))

        # timeout guards the worker thread against a hung/half-open SMTP socket
        # (SEC-3) -- without it a stuck connection blocks the job forever.
        with smtplib.SMTP(host, port, timeout=15) as server:
            # Pass a default SSL context so the STARTTLS upgrade validates the
            # SMTP host's certificate against the system CA store (SEC-5).
            # Without it the "encrypted" channel can be silently MITM'd/stripped.
            server.starttls(context=_SSL_CONTEXT)
            server.login(user, password)
            server.sendmail(from_addr, [to_addr], msg.as_string())
        log.info(f"Thought emailed to {to_addr}: '{note.title}'")
