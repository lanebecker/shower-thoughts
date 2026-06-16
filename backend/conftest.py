"""
Pytest configuration for the ShowerThoughts backend test suite.

Placed in backend/ so pytest adds backend/ to sys.path (rootdir insertion),
which makes `import main`, `import summarizer`, and `from adapters... import`
resolve the same way they do when the app runs from backend/.

Dummy API keys are set at import time, BEFORE the app modules are imported,
because transcriber.py instantiates `OpenAI()` at module import and summarizer's
provider calls read keys from the environment. For the same reason we point
UPLOAD_DIR and the SQLite JOBS_DB at a writable temp dir at import time -- main.py
opens the JobStore at import, before any per-test fixture runs.
"""

import os
import tempfile

import pytest

os.environ.setdefault("OPENAI_API_KEY", "test-key")
os.environ.setdefault("ANTHROPIC_API_KEY", "test-key")

_TEST_TMP = tempfile.mkdtemp(prefix="st-test-")
os.environ.setdefault("UPLOAD_DIR", os.path.join(_TEST_TMP, "uploads"))
os.environ.setdefault("JOBS_DB", os.path.join(_TEST_TMP, "jobs.db"))


@pytest.fixture(autouse=True)
def _isolated_paths(tmp_path, monkeypatch):
    """Point UPLOAD_DIR and the SQLite JOBS_DB at per-test temp paths.

    Keeps tests from sharing an uploads dir or a single jobs.db across tests.
    Set before any test reloads main, so the reloaded app picks these up. (The
    import-time defaults above cover the very first import during collection.)
    """
    monkeypatch.setenv("UPLOAD_DIR", str(tmp_path / "uploads"))
    monkeypatch.setenv("JOBS_DB", str(tmp_path / "jobs.db"))
