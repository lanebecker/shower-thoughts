"""
RGB LED state vocabulary — pure mapping plus a thin hardware controller.

The per-state (red, green, blue) levels and blink interval are pure data (unit
tested and kept identical to the Pi firmware's LED language). ``LedController``
drives ``machine.Pin`` and is hardware (lazy import, exercised on-device only).
"""

# state -> (red, green, blue, blink_interval_seconds_or_None)
STATES = {
    "off":         (False, False, False, None),
    "recording":   (True,  False, False, None),   # solid red
    "uploading":   (False, True,  False, 0.2),    # blinking green
    "done":        (False, True,  False, None),   # solid green
    "processing":  (False, False, True,  None),   # solid blue
    "buffered":    (False, False, True,  None),   # blue cue (pulsed by caller)
    "error":       (True,  False, False, 0.1),    # fast red blink
    "low_battery": (True,  True,  False, 0.15),   # amber blink (red + green)
}


def levels(state):
    """Return the ``(r, g, b)`` booleans for ``state`` (unknown -> off)."""
    r, g, b, _ = STATES.get(state, STATES["off"])
    return (r, g, b)


def blink_interval(state):
    """Return the blink interval (seconds) for ``state``, or ``None`` if solid."""
    return STATES.get(state, STATES["off"])[3]


class LedController:
    """Drives a common-cathode RGB LED on three GPIOs. Hardware path."""

    def __init__(self, red_pin, green_pin, blue_pin):
        from machine import Pin  # lazy: only on-device
        self._r = Pin(red_pin, Pin.OUT)
        self._g = Pin(green_pin, Pin.OUT)
        self._b = Pin(blue_pin, Pin.OUT)

    def set(self, state):
        r, g, b = levels(state)
        self._r.value(1 if r else 0)
        self._g.value(1 if g else 0)
        self._b.value(1 if b else 0)
