"""Tests for the WAV header builder."""

import struct

import wavfile


def test_header_is_44_bytes_and_well_formed():
    h = wavfile.wav_header(1000)
    assert len(h) == 44
    assert h[0:4] == b"RIFF"
    assert h[8:12] == b"WAVE"
    assert h[12:16] == b"fmt "
    assert h[36:40] == b"data"


def test_riff_and_data_sizes_track_data_len():
    data_len = 32000
    h = wavfile.wav_header(data_len)
    riff_size = struct.unpack("<I", h[4:8])[0]
    data_size = struct.unpack("<I", h[40:44])[0]
    assert riff_size == 36 + data_len
    assert data_size == data_len


def test_fmt_fields_for_16k_mono_16bit():
    h = wavfile.wav_header(0, sample_rate=16000, bits=16, channels=1)
    (sub1, fmt, channels, rate, byte_rate, block_align, bits) = struct.unpack(
        "<IHHIIHH", h[16:36]
    )
    assert sub1 == 16          # PCM fmt chunk size
    assert fmt == 1            # PCM
    assert channels == 1
    assert rate == 16000
    assert bits == 16
    assert byte_rate == 16000 * 1 * 16 // 8      # 32000
    assert block_align == 1 * 16 // 8            # 2
