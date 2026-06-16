"""
Audio sample conversion — pure, host-testable.

The INMP441 emits 24-bit samples MSB-justified in 32-bit I2S frames, so the
firmware captures at 32-bit and keeps the top 16 bits of each frame to get the
16-bit PCM the WAV / Whisper pipeline expects.

Implemented with explicit byte indexing rather than ``array``/``memoryview.cast``
so the behavior is identical on CPython (tests) and MicroPython and for any
buffer type (bytes / bytearray / memoryview). If this Python-level loop can't
keep up with the 16 kHz stream on-device, optimize it at the bench (e.g.
``@micropython.viper`` or ``memoryview.cast('h')[1::2]``) — but verify the
output bytes match these tests first.
"""


def pcm32_to_pcm16(raw32):
    """Convert little-endian 32-bit I2S frames to 16-bit PCM (top 16 bits each).

    ``raw32`` is bytes/bytearray/memoryview; its length should be a multiple of 4
    (whole frames). A trailing partial frame is dropped. Returns 16-bit
    little-endian PCM bytes (half the usable input length).
    """
    frames = len(raw32) // 4
    out = bytearray(frames * 2)
    for i in range(frames):
        out[2 * i] = raw32[4 * i + 2]       # low byte of the top 16 bits
        out[2 * i + 1] = raw32[4 * i + 3]   # high byte
    return bytes(out)
