"""
Persistent job store backed by SQLite.

Replaces the in-memory ``_jobs`` dict used through v0.1.x, which lost every
in-flight job whenever uvicorn restarted (and made ``GET /job/{id}`` return 404
for anything the current process hadn't handled). Job rows now live on disk, so
they survive a backend restart.

Scope note (v0.2.0): job *processing* still runs as an in-process FastAPI
BackgroundTask, so the backend is still meant to run as a SINGLE uvicorn worker.
SQLite is shared by all processes, so cross-worker reads would mostly work, but
multi-worker is a deliberate non-goal here -- see CLAUDE.md invariants.

The store is intentionally tiny and dependency-free (stdlib ``sqlite3``). Each
operation opens its own short-lived connection, which keeps it trivially safe to
call from different threads (FastAPI runs blocking work via ``asyncio.to_thread``).
"""

import json
import sqlite3
import logging
from pathlib import Path
from datetime import datetime
from typing import Optional

log = logging.getLogger(__name__)

# Columns a caller is allowed to write via update(). Guards against an
# accidental (or injected) key turning into arbitrary SQL, since we build the
# UPDATE statement from the dict keys.
_UPDATABLE = {
    "status",
    "transcript",
    "error",
    "title",
    "summary",
    "tags",
    "recorded_at",
}

_SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    id          TEXT PRIMARY KEY,
    status      TEXT NOT NULL,
    created_at  TEXT NOT NULL,
    updated_at  TEXT,
    transcript  TEXT,
    error       TEXT,
    title       TEXT,
    summary     TEXT,
    tags        TEXT,          -- JSON-encoded list[str]
    recorded_at TEXT
);
"""


class JobStore:
    """A minimal persistent store for upload jobs, backed by SQLite."""

    def __init__(self, db_path):
        self.db_path = str(db_path)
        # Make sure the parent directory exists (db_path may be like
        # /tmp/shower_uploads/jobs.db where the dir is created elsewhere too).
        parent = Path(self.db_path).expanduser().parent
        parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=10)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.executescript(_SCHEMA)

    def create(self, job_id: str, created_at: str, status: str = "queued") -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO jobs (id, status, created_at, updated_at) "
                "VALUES (?, ?, ?, ?)",
                (job_id, status, created_at, created_at),
            )

    def update(self, job_id: str, **fields) -> None:
        """Update one or more columns on a job. Unknown keys are rejected."""
        if not fields:
            return
        bad = set(fields) - _UPDATABLE
        if bad:
            raise ValueError(f"Cannot update unknown job field(s): {sorted(bad)}")
        fields["updated_at"] = datetime.now().isoformat()
        assignments = ", ".join(f"{col} = ?" for col in fields)
        values = list(fields.values())
        values.append(job_id)
        with self._connect() as conn:
            conn.execute(f"UPDATE jobs SET {assignments} WHERE id = ?", values)

    def get(self, job_id: str) -> Optional[dict]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM jobs WHERE id = ?", (job_id,)
            ).fetchone()
        return self._row_to_dict(row) if row else None

    def list_recent(self, limit: int = 50) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM jobs ORDER BY created_at DESC, id DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [self._row_to_dict(r) for r in rows]

    @staticmethod
    def _row_to_dict(row: sqlite3.Row) -> dict:
        d = {k: row[k] for k in row.keys() if row[k] is not None}
        if "tags" in d:
            try:
                d["tags"] = json.loads(d["tags"])
            except (ValueError, TypeError):
                # Leave the raw value if it somehow isn't valid JSON.
                pass
        return d
