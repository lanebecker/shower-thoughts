"""Tests for config parsing."""

import config


def test_defaults_applied_when_unset():
    cfg = config.parse_config("")
    assert cfg["SAMPLE_RATE"] == "16000"
    assert cfg["MAX_BUFFERED"] == "50"
    assert cfg["BACKEND_URL"] == ""


def test_overrides_comments_and_blank_lines():
    text = """
    # this is a comment
    BACKEND_URL=http://10.0.1.5:8000

    DEVICE_TOKEN=secret
    MAX_BUFFERED=10
    """
    cfg = config.parse_config(text)
    assert cfg["BACKEND_URL"] == "http://10.0.1.5:8000"
    assert cfg["DEVICE_TOKEN"] == "secret"
    assert cfg["MAX_BUFFERED"] == "10"


def test_quotes_stripped_and_hash_in_value_preserved():
    cfg = config.parse_config('WIFI_PASSWORD="p@ss#word"')
    assert cfg["WIFI_PASSWORD"] == "p@ss#word"     # inline '#' is NOT a comment here


def test_typed_coercion():
    cfg = config.parse_config("MAX_BUFFERED=10\nBATTERY_LOW_THRESHOLD=3.6")
    assert config.as_int(cfg, "MAX_BUFFERED") == 10
    assert config.as_float(cfg, "BATTERY_LOW_THRESHOLD") == 3.6


def test_as_int_falls_back_on_malformed_value():
    cfg = config.parse_config("MAX_BUFFERED=notanumber")
    assert config.as_int(cfg, "MAX_BUFFERED") == 50      # default, not a crash


def test_as_float_falls_back_on_malformed_value():
    cfg = config.parse_config("BATTERY_DIVIDER_RATIO=oops")
    assert config.as_float(cfg, "BATTERY_DIVIDER_RATIO") == 2.0


def test_max_duration_default_is_ram_safe():
    assert config.parse_config("")["MAX_DURATION_S"] == "60"
