"""Tests for the individual notes adapters. All external I/O is mocked."""

import ssl

import pytest

import summarizer
from summarizer import Note

from adapters import apple_notes, obsidian, notion, email_adapter, craft


def make_note():
    return Note(
        title="Idea",
        summary="A summary",
        full_text="full text here",
        tags=["x", "y"],
        recorded_at="2026-06-15T10:00:00",
    )


# --------------------------------------------------------------------------- #
# apple_notes
# --------------------------------------------------------------------------- #


class _FakeProc:
    def __init__(self, returncode=0, stderr=""):
        self.returncode = returncode
        self.stderr = stderr


def test_apple_notes_send_success(monkeypatch):
    calls = []

    def fake_run(args, **kwargs):
        calls.append((args, kwargs))
        return _FakeProc(returncode=0, stderr="")

    monkeypatch.setattr(apple_notes.subprocess, "run", fake_run)
    monkeypatch.setattr(apple_notes, "NOTES_FOLDER", "Shower Thoughts")

    apple_notes.AppleNotesAdapter().send(make_note())

    assert len(calls) == 1
    args, kwargs = calls[0]
    assert args == ["osascript", "-"]
    assert "input" in kwargs
    # SEC-3: the osascript subprocess must carry a timeout (default adapter).
    assert kwargs.get("timeout") == 15
    script = kwargs["input"]
    assert "Idea" in script  # title
    assert "Shower Thoughts" in script  # folder


def test_apple_notes_send_failure_raises(monkeypatch):
    monkeypatch.setattr(
        apple_notes.subprocess,
        "run",
        lambda args, **kwargs: _FakeProc(returncode=1, stderr="boom"),
    )
    with pytest.raises(RuntimeError):
        apple_notes.AppleNotesAdapter().send(make_note())


def test_apple_notes_timeout_raises_runtimeerror(monkeypatch):
    """SEC-3: a wedged osascript (TimeoutExpired) becomes a clean RuntimeError so
    the job goes to error instead of pinning the worker thread forever."""
    import subprocess as _sp

    def fake_run(args, **kwargs):
        raise _sp.TimeoutExpired(cmd=args, timeout=kwargs.get("timeout"))

    monkeypatch.setattr(apple_notes.subprocess, "run", fake_run)
    with pytest.raises(RuntimeError):
        apple_notes.AppleNotesAdapter().send(make_note())


# --------------------------------------------------------------------------- #
# obsidian — file strategy
# --------------------------------------------------------------------------- #


def test_obsidian_file_strategy_writes_md(monkeypatch, tmp_path):
    monkeypatch.setenv("OBSIDIAN_VAULT_PATH", str(tmp_path))
    monkeypatch.setattr(obsidian, "STRATEGY", "file")
    monkeypatch.setattr(obsidian, "OBSIDIAN_FOLDER", "Shower Thoughts")

    obsidian.ObsidianAdapter().send(make_note())

    folder = tmp_path / "Shower Thoughts"
    md_files = list(folder.glob("*.md"))
    assert len(md_files) == 1
    text = md_files[0].read_text(encoding="utf-8")
    assert "Idea" in text  # title
    assert "A summary" in text  # summary


# --------------------------------------------------------------------------- #
# obsidian — webhook strategy
# --------------------------------------------------------------------------- #


class _FakeResp:
    def __init__(self, status_code=200):
        self.status_code = status_code

    def raise_for_status(self):
        return None


def test_obsidian_webhook_puts_to_local_rest_api(monkeypatch):
    calls = []

    def fake_put(url, **kwargs):
        calls.append((url, kwargs))
        return _FakeResp(status_code=200)

    monkeypatch.setattr(obsidian.requests, "put", fake_put)
    monkeypatch.delenv("OBSIDIAN_API_URL", raising=False)  # use default
    monkeypatch.delenv("OBSIDIAN_API_KEY", raising=False)

    obsidian._send_webhook("f.md", "# x")

    assert len(calls) == 1
    url, kwargs = calls[0]
    assert "127.0.0.1:27123" in url
    assert kwargs.get("verify") is False
    # SEC-3: the webhook PUT must carry an explicit timeout.
    assert kwargs.get("timeout") == 15


# --------------------------------------------------------------------------- #
# notion
# --------------------------------------------------------------------------- #


def test_notion_send_posts_page(monkeypatch):
    calls = []

    def fake_post(url, **kwargs):
        calls.append((url, kwargs))
        return _FakeResp(status_code=200)

    monkeypatch.setenv("NOTION_API_KEY", "secret-key")
    monkeypatch.setenv("NOTION_DATABASE_ID", "db-123")
    monkeypatch.setattr(notion.requests, "post", fake_post)

    notion.NotionAdapter().send(make_note())

    assert len(calls) == 1
    url, kwargs = calls[0]
    assert url == "https://api.notion.com/v1/pages"
    # SEC-3: the Notion POST must carry an explicit timeout.
    assert kwargs.get("timeout") == 15
    headers = kwargs["headers"]
    assert headers["Authorization"] == "Bearer secret-key"
    props = kwargs["json"]["properties"]
    assert "Name" in props
    assert "Summary" in props
    assert "Tags" in props
    assert "Recorded" in props


def test_notion_missing_env_raises(monkeypatch):
    monkeypatch.delenv("NOTION_API_KEY", raising=False)
    monkeypatch.delenv("NOTION_DATABASE_ID", raising=False)
    with pytest.raises(EnvironmentError):
        notion.NotionAdapter().send(make_note())


# --------------------------------------------------------------------------- #
# email
# --------------------------------------------------------------------------- #


class _FakeSMTP:
    instances = []

    def __init__(self, host, port, timeout=None):
        self.host = host
        self.port = port
        self.timeout = timeout
        self.sent = []
        _FakeSMTP.instances.append(self)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def starttls(self, context=None):
        self.starttls_context = context

    def login(self, user, password):
        self.user = user
        self.password = password

    def sendmail(self, from_addr, to_addrs, msg):
        self.sent.append((from_addr, to_addrs, msg))


def test_email_send_calls_sendmail(monkeypatch):
    _FakeSMTP.instances = []
    monkeypatch.setattr(email_adapter.smtplib, "SMTP", _FakeSMTP)
    monkeypatch.setenv("SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("SMTP_USER", "user@example.com")
    monkeypatch.setenv("SMTP_PASS", "pw")
    monkeypatch.setenv("EMAIL_TO", "dest@example.com")

    email_adapter.EmailAdapter().send(make_note())

    assert len(_FakeSMTP.instances) == 1
    smtp = _FakeSMTP.instances[0]
    # SEC-3: the SMTP connection must be opened with an explicit timeout.
    assert smtp.timeout == 15
    # SEC-5: STARTTLS must be upgraded with a real SSL context (cert validation).
    assert isinstance(smtp.starttls_context, ssl.SSLContext)
    assert len(smtp.sent) == 1
    from_addr, to_addrs, msg = smtp.sent[0]
    assert to_addrs == ["dest@example.com"]


def test_email_missing_env_raises(monkeypatch):
    monkeypatch.delenv("SMTP_HOST", raising=False)
    monkeypatch.delenv("SMTP_USER", raising=False)
    monkeypatch.delenv("SMTP_PASS", raising=False)
    monkeypatch.delenv("EMAIL_TO", raising=False)
    with pytest.raises(EnvironmentError):
        email_adapter.EmailAdapter().send(make_note())


# --------------------------------------------------------------------------- #
# craft — url_scheme strategy
# --------------------------------------------------------------------------- #


def test_craft_url_scheme_invokes_osascript(monkeypatch):
    calls = []

    def fake_run(args, **kwargs):
        calls.append((args, kwargs))
        return _FakeProc(returncode=0, stderr="")

    monkeypatch.setenv("CRAFT_SPACE_ID", "space-abc")
    monkeypatch.setattr(craft, "CRAFT_SPACE_ID", "space-abc")
    monkeypatch.setattr(craft.subprocess, "run", fake_run)

    craft._send_url_scheme(make_note())

    assert len(calls) == 1
    args, kwargs = calls[0]
    # SEC-3: the osascript subprocess must carry a timeout.
    assert kwargs.get("timeout") == 15
    joined = " ".join(args)
    assert "open location" in joined
    assert "craftdocs://" in joined


def test_craft_url_scheme_missing_space_id_raises(monkeypatch):
    monkeypatch.setattr(craft, "CRAFT_SPACE_ID", "")
    with pytest.raises(EnvironmentError):
        craft._send_url_scheme(make_note())


# --------------------------------------------------------------------------- #
# craft — shortcuts strategy
# --------------------------------------------------------------------------- #


def test_craft_shortcuts_posts_payload(monkeypatch):
    calls = []

    def fake_post(url, **kwargs):
        calls.append((url, kwargs))
        return _FakeResp(status_code=200)

    monkeypatch.setenv("CRAFT_SHORTCUTS_WEBHOOK_URL", "https://hook.example.com/x")
    monkeypatch.setattr(craft.requests, "post", fake_post)

    craft._send_shortcuts(make_note())

    assert len(calls) == 1
    url, kwargs = calls[0]
    assert url == "https://hook.example.com/x"
    payload = kwargs["json"]
    assert "title" in payload
    assert "markdown" in payload
