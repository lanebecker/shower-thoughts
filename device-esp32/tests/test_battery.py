"""Tests for the ESP32 battery conversion + threshold + read."""

import pytest

import battery


def test_voltage_from_uv_applies_divider():
    # 2.1 V at the pin through a /2 divider == 4.2 V battery (full LiPo).
    assert battery.voltage_from_uv(2100000, 2.0) == pytest.approx(4.2, abs=1e-6)
    # Unity divider returns the pin voltage as-is.
    assert battery.voltage_from_uv(1750000, 1.0) == pytest.approx(1.75, abs=1e-6)


def test_is_low_threshold_and_none():
    assert battery.is_low(3.4, 3.5) is True
    assert battery.is_low(3.5, 3.5) is True       # at threshold counts as low
    assert battery.is_low(3.9, 3.5) is False
    assert battery.is_low(None, 3.5) is False     # failed read is not "low"


class _FakeADC:
    def __init__(self, uv):
        self._uv = uv

    def read_uv(self):
        return self._uv


class _BrokenADC:
    def read_uv(self):
        raise OSError("adc fault")


def test_read_voltage_with_fake_adc():
    adc = _FakeADC(1800000)             # 1.8 V pin
    assert battery.read_voltage(adc, 2.0) == pytest.approx(3.6, abs=1e-6)


def test_read_voltage_swallows_errors():
    assert battery.read_voltage(_BrokenADC(), 2.0) is None
