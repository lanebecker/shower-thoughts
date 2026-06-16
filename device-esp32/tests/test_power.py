"""Tests for the deep-sleep / retry planning logic."""

import power


def test_should_enter_sleep_threshold():
    assert power.should_enter_sleep(59, 60) is False
    assert power.should_enter_sleep(60, 60) is True
    assert power.should_enter_sleep(61, 60) is True


def test_timeout_zero_or_negative_disables_sleep():
    assert power.should_enter_sleep(10000, 0) is False
    assert power.should_enter_sleep(10000, -5) is False


def test_sleep_duration_indefinite_without_backlog_or_timer():
    assert power.sleep_duration_ms(False, True, 60) is None      # no backlog
    assert power.sleep_duration_ms(True, False, 60) is None      # timer disabled
    assert power.sleep_duration_ms(True, True, 0) is None        # no interval


def test_sleep_duration_timed_when_backlog_and_timer_enabled():
    assert power.sleep_duration_ms(True, True, 60) == 60000
    assert power.sleep_duration_ms(True, True, 1) == 1000
