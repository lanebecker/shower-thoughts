# v0.3.0 — ESP32-S3 Firmware Port (Plan)

Status: **in progress** (2026-06-16) — all hardware-independent logic for Phase 1
*and* Phase 2 is built and host-tested in `device-esp32/` (34 tests: `wavfile`,
`buffer`, `uploader` body, `config`, `leds`, `button`, `power`, `battery`,
`rtcstate`), and `recorder.py`/`main.py` are flash-ready skeletons wired to it.
What remains is on-device bench bring-up. This document scopes the v0.3.0 milestone from
[`roadmap.md`](roadmap.md): a MicroPython firmware for the ESP32-S3 that reaches
feature parity with the Raspberry Pi firmware in [`../device/`](../device/) and
adds the deep-sleep battery win that motivates the port.

The Pi firmware stays as a first-class target; the ESP32 firmware lands in a new
`device-esp32/` directory. The **backend contract does not change** — the ESP32
speaks the same `POST /upload` (multipart WAV + `X-Device-Token`) the Pi does.

---

## Why

The Pi Zero 2W idles at ~80 mA (≈ daily charging) and boots in 30–40 s, so you
can't power it down between uses. An ESP32-S3 deep-sleeps at ~10 µA (weeks of
standby) and wakes from a button press in milliseconds. That turns the device
from "always plugged in" into "grab it, press, talk, put it back."

## Decisions (locked 2026-06-16)

| Decision | Choice | Why |
|----------|--------|-----|
| Runtime | **MicroPython** | Closest to the existing Python firmware; fastest to write/maintain; logic is host-testable under CPython. |
| Board | **ESP32-S3-DevKitC-1 N16R8** | 16 MB flash + 8 MB PSRAM gives room to buffer audio in PSRAM and store WAVs in a flash filesystem for retry. |
| Sequencing | **MVP-first, then deep sleep** | Deep sleep is the riskiest subsystem; prove record→upload→LED on an always-on build first, then add power management. |

---

## Hardware

### BOM (verified specs Jun 2026; prices approximate — confirm at order time)

| Part | Notes |
|------|-------|
| ESP32-S3-DevKitC-1 **N16R8** | Dual-core LX7 @ 240 MHz, 16 MB flash, 8 MB PSRAM, 512 KB SRAM, Wi-Fi b/g/n + BLE 5.0, USB-C. MicroPython-compatible. |
| INMP441 I2S MEMS microphone | Replaces the Pi's SPH0645; standard MicroPython I2S target. |
| RGB LED + 3× resistors | Reused from the Pi build. |
| Momentary button | Reused — but **must be on an RTC-capable GPIO** (see constraint below). |
| LiPo cell + TP4056 charger | Reused; the ESP32 runs happily from 3.7 V LiPo. |
| USB-C cable | For flashing. |

> The ESP32's **built-in ADC reads the LiPo voltage directly** (through a divider),
> so the **ADS1115 from v0.2.0 is NOT needed** on this platform.

### Wiring constraints to honor

- **Wake-on-button needs an RTC GPIO.** Deep-sleep external wake (`esp32.wake_on_ext0`)
  only works on RTC GPIOs (GPIO0–GPIO21 on the S3). The button must be wired to
  one of these, or wake-on-press won't work. Pick the button pin with that in mind.
- **I2S pins** (BCLK / WS / SD) for the INMP441 — any free GPIOs; finalize in the
  hardware guide alongside the wiring table.
- **Audio buffering uses PSRAM**, then streams to a LittleFS flash partition for
  any WAV that needs to survive for retry (a 60 s/16 kHz/mono/16-bit clip ≈ 1.9 MB,
  too big for the 512 KB SRAM but fine for 8 MB PSRAM / 16 MB flash).

---

## Firmware architecture (`device-esp32/`)

Modules are split so the **pure logic is testable off-device** (under CPython),
exactly like the Pi suite mocks `RPi.GPIO`/`pyaudio`. Hardware modules import
`machine`/`network`/`esp32` **lazily** so the logic modules import fine on a host.

| Module | Role | Host-testable? |
|--------|------|----------------|
| `wavfile.py` | Build a WAV header for given rate/width/channels/length | ✅ pure |
| `buffer.py` | Pending-WAV listing, newest-N cap, oldest-first ordering (ports the Pi logic) | ✅ pure |
| `uploader.py` | Hand-build the `multipart/form-data` body (boundary + headers) and POST | ✅ body builder is pure; POST is hardware-ish |
| `config.py` | Load Wi-Fi creds / `BACKEND_URL` / `DEVICE_TOKEN` / thresholds (from a config file or NVS) | ✅ parsing |
| `leds.py` | RGB state table → pin levels (recording/uploading/done/error/buffered/low-battery) | ✅ table |
| `recorder.py` | I2S capture (INMP441) → 16 kHz mono WAV to flash | hardware |
| `main.py` | Boot, Wi-Fi connect, button + LED state machine, sleep orchestration | hardware |
| `tests/` | Host pytest over the pure modules | — |

> `urequests` has **no multipart support**, so `uploader.py` constructs the body
> by hand (boundary, `Content-Disposition`, the WAV bytes, closing boundary). This
> is the main reason to factor the body builder out — it's the fiddliest bit and
> the one most worth unit-testing.

---

## Phase 1 — MVP (always-on)

Goal: flash it and prove *press button → speak → note appears*, end to end.

1. Project scaffold + `config.py` (Wi-Fi/backend/token) + Wi-Fi connect on boot.
2. `recorder.py`: I2S capture from the INMP441 → 16 kHz mono WAV written to LittleFS.
   (No downsampling needed — I2S is configurable, unlike the Pi's fixed-48 kHz card.)
3. `uploader.py`: hand-built multipart `POST /upload` with `X-Device-Token`; parse
   the `202` + `job_id`.
4. Button state machine (short press start/stop, 3 s long-press cancel) + `leds.py`
   states; boot animation.
5. Basic error handling; flash + bench bring-up.

## Phase 2 — Power & resilience (the v0.3.0 payoff)

6. **Deep sleep after idle**; **wake on button** via `esp32.wake_on_ext0` (RTC GPIO).
   Note: `machine.deepsleep()` resets the chip on wake (re-runs `main.py` from the
   top), so the boot path must be fast and idempotent.
7. **Persist pending state across sleep** — small flags in RTC memory
   (`machine.RTC().memory()`), buffered WAVs on flash (LittleFS).
8. **Reconcile buffering/retry with sleep.** The Pi retries every 60 s in a
   background thread; a deep-sleeping ESP32 can't (radio off). Options to decide at
   build time: (a) flush the backlog on next wake [simplest, best battery];
   (b) periodic `deepsleep(ms)` timer-wake to retry [promptness, costs battery];
   (c) light sleep while a backlog exists. Default plan: **(a)**, with (b) as a
   configurable opt-in.
9. **Battery monitor** via the ESP32's native ADC + divider → low-battery LED cue
   (no ADS1115). Ports the v0.2.0 threshold/cue logic.
10. Expand the hardware guide's ESP32 section to first-class (wiring table, BOM,
    flashing), and mark the roadmap item shipped.

---

## Testing & CI

- **Host tests** (`device-esp32/tests/`) run under CPython via pytest, mocking
  `machine`/`network`/`esp32` (lazy imports keep the pure modules importable). Cover:
  WAV header bytes, buffer cap + ordering, multipart body shape, config parsing,
  LED state mapping, and the sleep/retry decision logic.
- Add a CI job mirroring the existing backend/device jobs in
  [`.github/workflows/tests.yml`](../.github/workflows/tests.yml).
- **On-device only** (needs the board, done by Lane at the bench): I2S capture,
  Wi-Fi, real upload, deep-sleep/wake, battery ADC. The agent can't flash or run
  hardware — it writes the code + host tests; bring-up is a human loop.

## Tooling (on Lane's Mac)

- MicroPython firmware for ESP32-S3 (v1.20+ for I2S support), flashed with
  `esptool`.
- `mpremote` (or Thonny) to push files and open a REPL.
- `brew install esptool` / `pip install mpremote`.

---

## Risks & open questions

- **Deep sleep ↔ retry reconciliation** (item 8) is the core design tension; the
  default (flush-on-wake) is simplest and most battery-friendly but delays delivery
  of buffered thoughts until the next press. Revisit if that feels bad in use.
- **Multipart in `urequests`** is hand-rolled; chunked/streamed upload of a ~2 MB
  WAV may need care to avoid loading it all into RAM at once (stream from flash).
- **RTC-GPIO button constraint** must be reflected in the wiring before anyone
  solders.
- **MicroPython memory headroom** for large recordings — rely on PSRAM + streaming
  to flash, not SRAM.

## References (verified Jun 2026)

- ESP32-S3-DevKitC-1 N16R8 spec — Espressif/board docs
- MicroPython I2S examples — github.com/miketeachman/micropython-i2s-examples
- MicroPython deep-sleep wake sources (`esp32.wake_on_ext0`) — Random Nerd Tutorials
- Multipart body construction — standard `multipart/form-data` (hand-built for `urequests`)
