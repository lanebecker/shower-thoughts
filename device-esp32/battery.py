"""
Battery monitoring for the ESP32 — pure conversion + threshold, plus a thin read.

The ESP32-S3's built-in ADC reads the LiPo through a 2-resistor divider, so no
ADS1115 is needed here (unlike the Pi / v0.2.0). ``ADC.read_uv()`` returns
microvolts at the pin; multiplying by the divider ratio recovers the battery
voltage. The conversion and the low threshold are pure (tested); ``read_voltage``
takes an ADC-like object (anything with ``read_uv()``) so it's testable with a
fake and never raises into the caller.
"""


def voltage_from_uv(pin_microvolts, divider_ratio=2.0):
    """Battery volts from ADC-pin microvolts and the divider ratio (Vbat / Vpin)."""
    return (pin_microvolts / 1000000.0) * divider_ratio


def is_low(voltage, threshold):
    """True when a successful reading is at/below ``threshold`` (None is not low)."""
    return voltage is not None and voltage <= threshold


def read_voltage(adc, divider_ratio=2.0):
    """Read battery volts from an ADC-like object exposing ``read_uv()``.

    Returns volts, or ``None`` on any read error — a flaky sensor must never take
    down the firmware (same principle as the Pi's v0.2.0 battery monitor).
    """
    try:
        return voltage_from_uv(adc.read_uv(), divider_ratio)
    except Exception:
        return None
