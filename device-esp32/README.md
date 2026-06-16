# ShowerThoughts — ESP32-S3 firmware (v0.3.0, in progress)

MicroPython firmware for the ESP32-S3 port. Goal: feature parity with the Pi
firmware in [`../device/`](../device/) plus deep-sleep battery life. See the full
plan in [`../docs/esp32-port-plan.md`](../docs/esp32-port-plan.md).

> **Status:** Phase 1 logic modules + host tests are landing first (hardware-
> independent, so they can be built and verified before the board arrives). The
> on-device pieces (I2S capture, Wi-Fi, real upload, deep sleep) come during bench
> bring-up.

## Modules

| File | Role | Tested on host? |
|------|------|-----------------|
| `wavfile.py` | Build the 44-byte PCM WAV header | ✅ |
| `buffer.py` | Pending-WAV listing, newest-N cap, oldest-first order | ✅ |
| `uploader.py` | Hand-built `multipart/form-data` body (`build_multipart`) + `post_wav` | ✅ body builder (POST is on-device) |
| `config.py` | Parse `KEY=VALUE` device config | ✅ |
| `leds.py` | RGB state table (`levels`/`blink_interval`) + `LedController` | ✅ tables (controller is on-device) |
| `recorder.py` | I2S capture → WAV *(added during bench bring-up)* | — |
| `main.py` | Boot, Wi-Fi, button/LED state machine *(added during bench bring-up)* | — |

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
