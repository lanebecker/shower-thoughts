"""
Pytest configuration for the ShowerThoughts backend test suite.

Placed in backend/ so pytest adds backend/ to sys.path (rootdir insertion),
which makes `import main`, `import summarizer`, and `from adapters... import`
resolve the same way they do when the app runs from backend/.

Dummy API keys are set at import time, BEFORE the app modules are imported,
because transcriber.py instantiates `OpenAI()` at module import and summarizer's
provider calls read keys from the environment.
"""

import os

os.environ.setdefault("OPENAI_API_KEY", "test-key")
os.environ.setdefault("ANTHROPIC_API_KEY", "test-key")
