"""Tests for the cross-deep-sleep state encode/decode."""

import rtcstate


def test_roundtrip():
    state = {"battery_low": True, "wakes": 3}
    assert rtcstate.decode(rtcstate.encode(state)) == state


def test_empty_inputs_give_empty_dict():
    assert rtcstate.decode(b"") == {}
    assert rtcstate.decode(None) == {}


def test_invalid_json_gives_empty_dict():
    assert rtcstate.decode(b"not json{{") == {}


def test_non_dict_json_gives_empty_dict():
    assert rtcstate.decode(b"[1, 2, 3]") == {}
