"""
Test bootstrap for the ESP32 firmware logic.

Placing this conftest in device-esp32/ puts the directory on sys.path, so the
tests can ``import wavfile`` etc. the same way they resolve on-device. The pure
modules (wavfile, buffer, uploader's body builder, config, leds' tables) import
no hardware at top level; the hardware paths (urequests, machine) are imported
lazily inside functions. We still stub those MicroPython-only modules here so an
accidental import can't blow up the host test run.
"""

import sys
from types import ModuleType

for _name in ("machine", "network", "esp32", "urequests"):
    if _name not in sys.modules:
        _mod = ModuleType(_name)
        sys.modules[_name] = _mod

# Give the machine stub a minimal Pin so leds.LedController could be constructed
# in a future hardware-ish test if desired.
if not hasattr(sys.modules["machine"], "Pin"):
    class _Pin:
        OUT = "OUT"
        IN = "IN"

        def __init__(self, *a, **k):
            self._v = 0

        def value(self, v=None):
            if v is None:
                return self._v
            self._v = v

    sys.modules["machine"].Pin = _Pin
