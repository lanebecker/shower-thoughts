"""Tests for the pure button-press classifier."""

import button


def test_short_press_when_released_early():
    assert button.classify(0.4, released=True, long_press_s=3.0) == "short"


def test_long_press_when_held_to_threshold():
    assert button.classify(3.0, released=False, long_press_s=3.0) == "long"
    assert button.classify(3.5, released=False, long_press_s=3.0) == "long"


def test_none_while_still_held_below_threshold():
    assert button.classify(1.0, released=False, long_press_s=3.0) is None


def test_long_takes_priority_over_release_at_threshold():
    # main.py detects 'long' while still held, so 'long' wins before release.
    assert button.classify(3.0, released=False, long_press_s=3.0) == "long"
