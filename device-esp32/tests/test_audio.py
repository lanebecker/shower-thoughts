"""Tests for the 32-bit -> 16-bit I2S sample conversion."""

import audio


def test_keeps_high_halfword_of_each_frame():
    # One 32-bit LE frame: low halfword 0xABCD, high halfword 0x1234.
    # Bytes (LE): CD AB 34 12  ->  keep top 16 bits -> 34 12
    assert audio.pcm32_to_pcm16(b"\xCD\xAB\x34\x12") == b"\x34\x12"


def test_multiple_frames():
    frame1 = b"\x00\x00\x00\x80"   # high halfword 0x8000
    frame2 = b"\xFF\xFF\xFF\x7F"   # high halfword 0x7FFF
    out = audio.pcm32_to_pcm16(frame1 + frame2)
    assert out == b"\x00\x80\xFF\x7F"
    assert len(out) == 4           # 2 frames -> 2 samples -> 4 bytes


def test_empty_input():
    assert audio.pcm32_to_pcm16(b"") == b""


def test_trailing_partial_frame_is_dropped():
    # 6 bytes = 1 whole frame + 2 stray bytes; only the whole frame converts.
    assert audio.pcm32_to_pcm16(b"\xCD\xAB\x34\x12\x99\x99") == b"\x34\x12"


def test_accepts_memoryview():
    mv = memoryview(bytearray(b"\xCD\xAB\x34\x12"))
    assert audio.pcm32_to_pcm16(mv) == b"\x34\x12"
