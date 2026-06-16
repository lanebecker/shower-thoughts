"""
Small persistent state across deep sleep — pure encode/decode (JSON).

``machine.deepsleep()`` resets the chip (main.py re-runs from the top on wake),
but ``machine.RTC().memory()`` survives sleep. We keep a tiny JSON blob there —
e.g. whether the low-battery cue already fired, or a wake counter — so the
firmware doesn't repeat itself on every wake. These helpers are pure; main.py
does the actual ``RTC().memory()`` read/write.
"""

import json


def encode(state):
    """Serialize a small dict to bytes for RTC memory."""
    return json.dumps(state).encode()


def decode(raw):
    """Deserialize RTC-memory bytes back to a dict; ``{}`` on empty/invalid."""
    if not raw:
        return {}
    try:
        data = json.loads(raw)
    except (ValueError, TypeError):
        return {}
    return data if isinstance(data, dict) else {}
