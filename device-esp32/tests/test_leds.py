"""Tests for the LED state table."""

import leds


def test_known_states_map_to_expected_colors():
    assert leds.levels("recording") == (True, False, False)   # red
    assert leds.levels("done") == (False, True, False)        # green
    assert leds.levels("processing") == (False, False, True)  # blue


def test_low_battery_is_amber_red_plus_green():
    assert leds.levels("low_battery") == (True, True, False)


def test_unknown_state_is_off():
    assert leds.levels("nonsense") == (False, False, False)


def test_blink_intervals():
    assert leds.blink_interval("uploading") == 0.2
    assert leds.blink_interval("error") == 0.1
    assert leds.blink_interval("recording") is None          # solid
