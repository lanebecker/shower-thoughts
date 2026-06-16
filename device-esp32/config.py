"""
Device configuration parsing — pure, host-testable.

Mirrors the Pi's ``.env`` keys plus ESP32-specific ones (Wi-Fi creds, idle-sleep
timeout, battery ADC). On-device, main.py reads the config file's text and passes
it here; tests pass a string. Format is simple ``KEY=VALUE`` lines:

  - blank lines and whole-line ``#`` comments are ignored
  - surrounding single/double quotes around a value are stripped
  - values are taken verbatim otherwise (no inline-comment stripping, so a value
    may safely contain ``#``)

Unset keys fall back to DEFAULTS. ``as_int`` / ``as_float`` coerce typed values.
"""

DEFAULTS = {
    "BACKEND_URL": "",
    "DEVICE_TOKEN": "",
    "WIFI_SSID": "",
    "WIFI_PASSWORD": "",
    "SAMPLE_RATE": "16000",
    "MAX_BUFFERED": "50",
    "MAX_DURATION_S": "300",
    "IDLE_SLEEP_S": "0",           # idle seconds before deep sleep; 0 = always-on (Phase 2 opt-in)
    "RETRY_INTERVAL_S": "0",       # >0 + TIMER_WAKE: periodic wake to retry a backlog
    "TIMER_WAKE": "",              # "1" to enable timed wake-to-retry while a backlog exists
    "BATTERY_LOW_THRESHOLD": "3.5",
    "BATTERY_ADC_PIN": "",         # empty = battery monitor disabled
    "BATTERY_DIVIDER_RATIO": "2.0",
}


def parse_config(text):
    """Parse ``KEY=VALUE`` config text into a dict layered over DEFAULTS."""
    cfg = dict(DEFAULTS)
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key = key.strip()
        val = val.strip()
        if len(val) >= 2 and val[0] in "\"'" and val[-1] == val[0]:
            val = val[1:-1]
        cfg[key] = val
    return cfg


def as_int(cfg, key):
    return int(cfg[key])


def as_float(cfg, key):
    return float(cfg[key])
