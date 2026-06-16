"""
I2S capture from the INMP441 -> 16 kHz mono PCM WAV on the flash filesystem.

HARDWARE MODULE — not exercised by host tests; verify on-device during bench
bring-up. Uses machine.I2S (MicroPython v1.20+ for I2S support). The WAV header
comes from the host-tested `wavfile` module.

INMP441 note: the mic emits 24-bit samples MSB-justified in 32-bit I2S frames.
We capture at 16-bit / mono for simplicity, which works on many setups. If audio
comes back quiet, clipped, or noisy at the bench, the fix is to capture at
bits=32 and keep the top 16 bits of each sample — make that change here and
nowhere else, since the rest of the pipeline is byte-agnostic.

Pin numbers below are placeholders — finalize them in docs/hardware-guide.md and
keep this in sync.
"""

import time
from machine import I2S, Pin

import wavfile

# I2S wiring to the INMP441 (choose free GPIOs; mirror in the hardware guide).
SCK_PIN = 12   # BCLK  (bit clock)
WS_PIN = 13    # LRCL  (word select)
SD_PIN = 11    # DOUT  (mic serial data out)

I2S_ID = 0
_IBUF_BYTES = 40 * 1024   # internal DMA ring buffer


def _make_i2s(sample_rate):
    return I2S(
        I2S_ID,
        sck=Pin(SCK_PIN),
        ws=Pin(WS_PIN),
        sd=Pin(SD_PIN),
        mode=I2S.RX,
        bits=16,
        format=I2S.MONO,
        rate=sample_rate,
        ibuf=_IBUF_BYTES,
    )


def record(path, should_continue, sample_rate=16000, max_seconds=300, chunk=2048):
    """Record PCM to ``path`` until ``should_continue()`` is False or the cap hits.

    Writes a placeholder WAV header first, streams audio in ``chunk``-byte blocks,
    then rewrites the header with the true data length. ``should_continue`` is a
    callable polled between blocks (main.py uses it to watch for the stop/cancel
    press). Returns the number of PCM bytes written.
    """
    audio = _make_i2s(sample_rate)
    block = bytearray(chunk)
    data_len = 0
    start = time.time()
    try:
        with open(path, "wb") as f:
            f.write(wavfile.wav_header(0, sample_rate))   # placeholder; fixed below
            while should_continue():
                if time.time() - start >= max_seconds:
                    break
                n = audio.readinto(block)
                if n:
                    f.write(block[:n] if n != chunk else block)
                    data_len += n
    finally:
        audio.deinit()
    _rewrite_header(path, data_len, sample_rate)
    return data_len


def _rewrite_header(path, data_len, sample_rate):
    """Seek to the start and write the real header now that data_len is known."""
    with open(path, "r+b") as f:
        f.seek(0)
        f.write(wavfile.wav_header(data_len, sample_rate))
