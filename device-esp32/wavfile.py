"""
WAV (PCM) header construction — pure, no hardware dependencies.

The INMP441 feeds 16 kHz / mono / 16-bit PCM over I2S. recorder.py streams the
raw PCM samples to a file; this module builds the 44-byte canonical WAV header
that describes them. Kept dependency-free (only stdlib `struct`) so it imports
and runs identically under CPython (host tests) and MicroPython (on-device).
"""

import struct


def wav_header(data_len, sample_rate=16000, bits=16, channels=1):
    """Return the 44-byte canonical PCM WAV header for ``data_len`` bytes of audio.

    ``data_len`` is the number of PCM data bytes that will follow the header.
    """
    byte_rate = sample_rate * channels * bits // 8
    block_align = channels * bits // 8
    return b"".join([
        b"RIFF",
        struct.pack("<I", 36 + data_len),   # ChunkSize = 36 + Subchunk2Size
        b"WAVE",
        b"fmt ",
        struct.pack(
            "<IHHIIHH",
            16,           # Subchunk1Size (PCM)
            1,            # AudioFormat (1 = PCM)
            channels,
            sample_rate,
            byte_rate,
            block_align,
            bits,
        ),
        b"data",
        struct.pack("<I", data_len),
    ])
