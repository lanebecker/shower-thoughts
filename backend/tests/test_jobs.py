"""
Tests for the SQLite-backed JobStore in jobs.py.

These hit a real on-disk SQLite file (in a per-test tmp dir) -- no mocking,
because the whole point of the store is durable on-disk behavior.
"""

import json

import pytest

from jobs import JobStore


def test_create_and_get(tmp_path):
    store = JobStore(tmp_path / "jobs.db")
    store.create("abc123", "2026-06-16T08:00:00")
    job = store.get("abc123")
    assert job["id"] == "abc123"
    assert job["status"] == "queued"
    assert job["created_at"] == "2026-06-16T08:00:00"


def test_get_unknown_returns_none(tmp_path):
    store = JobStore(tmp_path / "jobs.db")
    assert store.get("nope") is None


def test_update_fields_and_tags_roundtrip(tmp_path):
    store = JobStore(tmp_path / "jobs.db")
    store.create("j1", "2026-06-16T08:00:00")
    store.update("j1", status="summarizing", transcript="hello there")
    store.update(
        "j1",
        status="done",
        title="A Title",
        summary="A summary",
        tags=json.dumps(["alpha", "beta"]),
        recorded_at="2026-06-16T08:01:00",
    )
    job = store.get("j1")
    assert job["status"] == "done"
    assert job["transcript"] == "hello there"
    assert job["title"] == "A Title"
    # tags is stored as JSON text and returned as a parsed list.
    assert job["tags"] == ["alpha", "beta"]
    assert "updated_at" in job


def test_update_rejects_unknown_field(tmp_path):
    store = JobStore(tmp_path / "jobs.db")
    store.create("j1", "2026-06-16T08:00:00")
    with pytest.raises(ValueError):
        store.update("j1", bogus="value")


def test_none_fields_are_omitted(tmp_path):
    store = JobStore(tmp_path / "jobs.db")
    store.create("j1", "2026-06-16T08:00:00")
    job = store.get("j1")
    # Columns that were never set should not appear in the dict.
    assert "error" not in job
    assert "title" not in job


def test_list_recent_orders_newest_first_and_limits(tmp_path):
    store = JobStore(tmp_path / "jobs.db")
    store.create("old", "2026-06-16T08:00:00")
    store.create("mid", "2026-06-16T09:00:00")
    store.create("new", "2026-06-16T10:00:00")
    ids = [j["id"] for j in store.list_recent()]
    assert ids == ["new", "mid", "old"]
    assert [j["id"] for j in store.list_recent(limit=1)] == ["new"]


def test_persists_across_instances(tmp_path):
    """A fresh store pointed at the same file sees prior rows (restart sim)."""
    db = tmp_path / "jobs.db"
    JobStore(db).create("survivor", "2026-06-16T08:00:00")
    # Simulate a backend restart: brand-new JobStore, same file.
    reopened = JobStore(db)
    assert reopened.get("survivor")["id"] == "survivor"
