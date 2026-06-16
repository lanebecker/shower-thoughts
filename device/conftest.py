"""
Test bootstrap for device/recorder.py.

recorder.py imports RPi.GPIO and pyaudio at module top (and runs
dotenv.load_dotenv() on import). Neither hardware module is installed off-Pi,
so we inject lightweight fakes into sys.modules BEFORE recorder can be imported.

Placing this conftest.py inside device/ also puts device/ on sys.path, so
`import recorder` resolves from the tests.
"""

import os
import sys
from types import ModuleType

os.environ.setdefault("BACKEND_URL", "http://test:8000")


# RPi.GPIO fake
_rpi = ModuleType("RPi")
_gpio = ModuleType("RPi.GPIO")

_gpio.BCM = "BCM"
_gpio.IN = "IN"
_gpio.OUT = "OUT"
_gpio.HIGH = 1
_gpio.LOW = 0
_gpio.PUD_UP = "PUD_UP"
_gpio.FALLING = "FALLING"


def _noop(*args, **kwargs):
    return None


_gpio.setmode = _noop
_gpio.setwarnings = _noop
_gpio.setup = _noop
_gpio.output = _noop
_gpio.add_event_detect = _noop
_gpio.cleanup = _noop
_gpio.input = lambda *a, **k: _gpio.HIGH

_rpi.GPIO = _gpio
sys.modules["RPi"] = _rpi
sys.modules["RPi.GPIO"] = _gpio


# pyaudio fake
_pyaudio = ModuleType("pyaudio")
_pyaudio.paInt16 = 8


class _FakePyAudio:
    def __init__(self, *args, **kwargs):
        pass

    def get_device_count(self):
        return 0

    def get_device_info_by_index(self, i):
        return {"maxInputChannels": 0, "name": "fake"}

    def open(self, *args, **kwargs):
        raise RuntimeError("audio capture not supported in tests")

    def terminate(self):
        pass


_pyaudio.PyAudio = _FakePyAudio
sys.modules["pyaudio"] = _pyaudio
