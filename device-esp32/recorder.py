"""
I2S capture from the INMP441 -> 16 kHz mono PCM WAV on the flash filesystem.

HARDWARE MODULE — not exercised by host tests; verify on-device during bench
bring-up. Uses machine.I2S (MicroPython v1.20+).

The INMP441 emits 24-bit samples MSB-justified in 32-bit I2S frames, so we
capture at bits=32 and downconvert to 16-bit with the host-tested
``audio.pcm32_to_pcm16`` (keeps the top 16 bits). The WAV header (from the
host-tested ``wavfile``) therefore describes 16-bit data. Timing uses
``time.ticks_ms``/``ticks_diff`` — on MicroPython ``time.time()`` is integer
seconds, too coarse for durations.

Pin numbers are placeholders — keep them in sync with docs/hardware-guide.md.
"""

import time
from machine import I2S, Pin

import wavfile
import audio

# I2S wiring to the INMP441 (choose free GPIOs; mirror in the hardware guide).
SCK_PIN = 12   # BCLK  (bit clock)
WS_PIN = 13    # LRCL  (word select)
SD_PIN = 11    # DOUT  (mic serial data out)

I2S_ID = 0
_IBUF_BYTES = 40 * 1024   # internal DMA ring buffer


def _make_i2s(sample_rate):
    # bits=32: the INMP441 packs its 24 bits MSB-justified into a 32-bit frame.
    return I2S(
        I2S_ID,
        sck=Pin(SCK_PIN),
        ws=Pin(WS_PIN),
        sd=Pin(SD_PIN),
        mode=I2S.RX,
        bits=32,
        format=I2S.MONO,
        rate=sample_rate,
        ibuf=_IBUF_BYTES,
    )


def record(path, should_continue, sample_rate=16000, max_seconds=60, chunk=4096):
    """Record PCM to ``path`` until ``should_continue()`` is False or the cap hits.

    Captures 32-bit frames, downconverts each block to 16-bit, and streams to the
    WAV (placeholder header first, rewritten with the true length at the end).
    ``chunk`` must be a multiple of 4 (whole 32-bit frames). Returns the number of
    16-bit PCM bytes written.
    """
    audio_in = _make_i2s(sample_rate)
    raw = bytearray(chunk)
    mv = memoryview(raw)
    data_len = 0
    start = time.ticks_ms()
    limit_ms = int(max_seconds * 1000)
    try:
        with open(path, "wb") as f:
            f.write(wavfile.wav_header(0, sample_rate))   # placeholder; fixed below
            while should_continue():
                if time.ticks_diff(time.ticks_ms(), start) >= limit_ms:
                    break
                n = audio_in.readinto(raw)
                if n:
                    pcm16 = audio.pcm32_to_pcm16(mv[:n])
                    f.write(pcm16)
                    data_len += len(pcm16)
    finally:
        audio_in.deinit()
    _rewrite_header(path, data_len, sample_rate)
    return data_len


def _rewrite_header(path, data_len, sample_rate):
    """Seek to the start and write the real header now that data_len is known."""
    with open(path, "r+b") as f:
        f.seek(0)
        f.write(wavfile.wav_header(data_len, sample_rate))
