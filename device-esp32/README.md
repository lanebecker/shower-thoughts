# ShowerThoughts — ESP32-S3 firmware (v0.3.0, in progress)

MicroPython firmware for the ESP32-S3 port. Goal: feature parity with the Pi
firmware in [`../device/`](../device/) plus deep-sleep battery life. See the full
plan in [`../docs/esp32-port-plan.md`](../docs/esp32-port-plan.md).

> **Status:** All hardware-independent logic for Phase 1 *and* Phase 2 is built
> and host-tested (43 tests), and the on-device modules (`recorder.py`, `main.py`)
> are drafted as flash-ready skeletons. What's left is bench bring-up once the
> board arrives: verify I2S capture, Wi-Fi, real upload, and deep-sleep/wake.

## Modules

| File | Role | Tested on host? |
|------|------|-----------------|
| `wavfile.py` | Build the 44-byte PCM WAV header | ✅ |
| `audio.py` | 32-bit I2S frame → 16-bit PCM (INMP441 top-16-bits) | ✅ |
| `buffer.py` | Pending-WAV listing, newest-N cap, oldest-first order | ✅ |
| `uploader.py` | Hand-built `multipart/form-data` body + `post_wav` | ✅ body builder (POST on-device) |
| `config.py` | Parse `KEY=VALUE` device config | ✅ |
| `leds.py` | RGB state table + `LedController` | ✅ table (controller on-device) |
| `button.py` | Pure press classifier (short / long / none) | ✅ |
| `power.py` | Deep-sleep / retry planning (Phase 2) | ✅ |
| `battery.py` | LiPo ADC voltage + low threshold (Phase 2) | ✅ |
| `rtcstate.py` | Encode/decode small state across deep sleep (Phase 2) | ✅ |
| `recorder.py` | I2S capture → WAV *(skeleton; bench-verify)* | — (hardware) |
| `main.py` | Boot, Wi-Fi, button/LED state machine, deep sleep *(skeleton; bench-verify)* | — (hardware) |

## Tests (run on any machine, no board needed)

```bash
cd device-esp32
pytest -q          # uses the stubs in conftest.py for machine/network/esp32/urequests
```

The pure modules import no hardware at top level; hardware deps are imported
lazily inside functions, so the suite runs under CPython.

## On-device (once the board is here)

Target: **ESP32-S3-DevKitC-1 N16R8**, MicroPython v1.20+ (for I2S).

```bash
pip install esptool mpremote          # on your Mac
# flash MicroPython firmware with esptool, then push files:
mpremote connect auto fs cp *.py :
```

Wiring, the RTC-GPIO wake-button constraint, and the BOM live in
[`../docs/hardware-guide.md`](../docs/hardware-guide.md) and the port plan.
