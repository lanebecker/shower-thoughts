"""
Buffered-recording management for the ESP32 firmware.

Ports the Pi firmware's buffer policy (see ../device/recorder.py): each thought
is written to a directory as ``thought_<timestamp>.wav``; the newest
``max_buffered`` are kept (oldest dropped) so the flash filesystem can't fill;
pending files upload oldest-first. Timestamped names sort chronologically, so
plain string sorting gives oldest-first order.

Pure filesystem logic — only stdlib ``os`` (``uos`` on MicroPython exposes the
same ``listdir``/``remove``), so it runs under CPython for tests and on-device.
Paths are joined with ``/`` rather than ``os.path`` (MicroPython has no os.path).
"""

import os

PREFIX = "thought_"
SUFFIX = ".wav"


def pending_wavs(directory):
    """Buffered recordings in ``directory``, oldest first."""
    names = [
        n for n in os.listdir(directory)
        if n.startswith(PREFIX) and n.endswith(SUFFIX)
    ]
    return sorted(names)


def enforce_cap(directory, max_buffered):
    """Keep only the newest ``max_buffered`` recordings.

    Deletes the oldest files beyond the cap and returns the list of dropped
    names (oldest first). A delete failure is ignored — the goal is just to keep
    the directory from growing without bound.
    """
    names = pending_wavs(directory)
    if len(names) <= max_buffered:
        return []
    dropped = names[:len(names) - max_buffered]
    for n in dropped:
        try:
            os.remove(directory + "/" + n)
        except OSError:
            pass
    return dropped
