"""
Unit tests for the optional low-battery monitor in device/recorder.py.

The ADS1115 is reached via smbus2, which is imported lazily inside
_read_battery_voltage. Tests either mock that function or inject a fake smbus2
module, so no I2C hardware or library is required.
"""

import sys
from types import ModuleType, SimpleNamespace

import pytest

import recorder


@pytest.fixture(autouse=True)
def _reset_state():
    recorder._state = recorder.State.IDLE
    recorder._battery_low = False
    yield
    recorder._state = recorder.State.IDLE
    recorder._battery_low = False


# ── pure conversion ─────────────────────────────────────────────

def test_voltage_from_raw_with_default_divider():
    # Vadc = 2.0 V -> code 16000; divider 2.0 -> 4.0 V battery.
    assert recorder._battery_voltage_from_raw(16000) == pytest.approx(4.0, abs=1e-3)


def test_battery_is_low_threshold():
    assert recorder._battery_is_low(3.4) is True
    assert recorder._battery_is_low(3.5) is True          # at threshold counts as low
    assert recorder._battery_is_low(3.9) is False
    assert recorder._battery_is_low(None) is False        # failed read is not "low"


# ── cue gating ────────────────────────────────────────────────

def test_low_cue_runs_only_when_idle(monkeypatch):
    calls = []
    monkeypatch.setattr(recorder, "_led_solid", lambda **kw: calls.append(kw))
    monkeypatch.setattr(recorder, "_led_off", lambda: None)
    monkeypatch.setattr(recorder.time, "sleep", lambda s: None)

    recorder._state = recorder.State.RECORDING
    recorder._battery_low_cue()
    assert calls == []                       # must not touch the LED mid-recording

    recorder._state = recorder.State.IDLE
    recorder._battery_low_cue()
    assert len(calls) == 2                    # amber double-blink
    assert all(c.get("r") and c.get("g") for c in calls)  # red+green = amber


# ── orchestration ────────────────────────────────────────────

def test_check_sets_low_and_cues(monkeypatch):
    monkeypatch.setattr(recorder, "_read_battery_voltage", lambda: 3.3)
    cued = []
    monkeypatch.setattr(recorder, "_battery_low_cue", lambda: cued.append(True))

    v = recorder._check_battery_once()
    assert v == 3.3
    assert recorder._battery_low is True
    assert cued == [True]


def test_check_clears_low_when_recovered(monkeypatch):
    recorder._battery_low = True
    monkeypatch.setattr(recorder, "_read_battery_voltage", lambda: 4.0)
    monkeypatch.setattr(recorder, "_battery_low_cue", lambda: pytest.fail("no cue when OK"))

    v = recorder._check_battery_once()
    assert v == 4.0
    assert recorder._battery_low is False


def test_check_handles_failed_read(monkeypatch):
    monkeypatch.setattr(recorder, "_read_battery_voltage", lambda: None)
    monkeypatch.setattr(recorder, "_battery_low_cue", lambda: pytest.fail("no cue on None"))
    # Must not crash and must not flip the flag on a failed read.
    assert recorder._check_battery_once() is None
    assert recorder._battery_low is False


# ── end-to-end read via a fake smbus2 ──────────────────────────

class _FakeSMBus:
    """Minimal smbus2.SMBus stand-in returning a fixed conversion result."""

    last_config = None

    def __init__(self, bus):
        self.bus = bus

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def write_i2c_block_data(self, addr, reg, data):
        _FakeSMBus.last_config = (addr, reg, tuple(data))

    def read_i2c_block_data(self, addr, reg, n):
        # 0x3E80 = 16000 -> 2.0 V at ADC -> 4.0 V battery (divider 2.0)
        return [0x3E, 0x80]


def test_read_battery_voltage_via_fake_smbus(monkeypatch):
    fake_mod = ModuleType("smbus2")
    fake_mod.SMBus = _FakeSMBus
    monkeypatch.setitem(sys.modules, "smbus2", fake_mod)
    monkeypatch.setattr(recorder.time, "sleep", lambda s: None)

    v = recorder._read_battery_voltage()
    assert v == pytest.approx(4.0, abs=1e-3)
    # Config register write happened with the start bit set.
    addr, reg, data = _FakeSMBus.last_config
    assert reg == recorder._ADS1115_REG_CONFIG
    assert data[0] & 0x80                      # OS start bit


def test_read_battery_voltage_returns_none_without_smbus(monkeypatch):
    # Simulate smbus2 not installed: importing it raises ImportError.
    monkeypatch.setitem(sys.modules, "smbus2", None)
    assert recorder._read_battery_voltage() is None
