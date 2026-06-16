"""Tests for summarizer.summarize_thought and the Note dataclass."""

import summarizer
from summarizer import Note, summarize_thought


def test_note_dataclass_fields():
    note = Note(
        title="T",
        summary="S",
        full_text="F",
        tags=["a"],
        recorded_at="2026-06-15T10:00:00",
    )
    assert note.title == "T"
    assert note.summary == "S"
    assert note.full_text == "F"
    assert note.tags == ["a"]
    assert note.recorded_at == "2026-06-15T10:00:00"


def test_summarize_anthropic(monkeypatch):
    monkeypatch.setattr(summarizer, "AI_PROVIDER", "anthropic")
    monkeypatch.setattr(
        summarizer,
        "_call_claude",
        lambda transcript: {"title": "T", "summary": "S", "tags": ["a", "b"]},
    )
    note = summarize_thought("raw")
    assert note.title == "T"
    assert note.summary == "S"
    assert note.tags == ["a", "b"]
    assert note.full_text == "raw"
    assert isinstance(note.recorded_at, str)
    assert note.recorded_at  # non-empty ISO-ish string


def test_summarize_openai_used_when_selected(monkeypatch):
    monkeypatch.setattr(summarizer, "AI_PROVIDER", "openai")

    def _fail_claude(transcript):
        raise AssertionError("_call_claude should not be used when provider=openai")

    monkeypatch.setattr(summarizer, "_call_claude", _fail_claude)
    monkeypatch.setattr(
        summarizer,
        "_call_openai",
        lambda transcript: {"title": "OT", "summary": "OS", "tags": ["o"]},
    )
    note = summarize_thought("raw text")
    assert note.title == "OT"
    assert note.summary == "OS"
    assert note.tags == ["o"]
    assert note.full_text == "raw text"


def test_summarize_missing_tags_defaults_empty(monkeypatch):
    monkeypatch.setattr(summarizer, "AI_PROVIDER", "anthropic")
    monkeypatch.setattr(
        summarizer,
        "_call_claude",
        lambda transcript: {"title": "T", "summary": "S"},
    )
    note = summarize_thought("raw")
    assert note.tags == []
