# v0.3.0 — ESP32-S3 Firmware Port (Plan)

Status: **in progress** (2026-06-16) — all hardware-independent logic for Phase 1
*and* Phase 2 is built and host-tested in `device-esp32/` (43 tests: `wavfile`,
`audio`, `buffer`, `uploader` body, `config`, `leds`, `button`, `power`, `battery`,
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
| `audio.py` | 32-bit I2S frame → 16-bit PCM (keep INMP441's top 16 bits) | ✅ pure |
| `buffer.py` | Pending-WAV listing, newest-N cap, oldest-first ordering (ports the Pi logic) | ✅ pure |
| `uploader.py` | Multipart body + streaming envelope + POST | ✅ builders are pure; POST is hardware-ish |
| `config.py` | Load Wi-Fi creds / `BACKEND_URL` / `DEVICE_TOKEN` / thresholds; safe typed coercion | ✅ parsing |
| `leds.py` | RGB state table → pin levels (recording/uploading/done/error/buffered/low-battery) | ✅ table |
| `button.py` | Press classifier (short / long / none) | ✅ pure |
| `power.py` | Deep-sleep / retry planning | ✅ pure |
| `battery.py` | LiPo ADC → volts + low threshold | ✅ pure |
| `rtcstate.py` | Encode/decode small state across deep sleep | ✅ pure |
| `recorder.py` | I2S capture (INMP441) → 16 kHz mono WAV to flash | hardware |
| `main.py` | Boot, Wi-Fi connect, button + LED state machine, sleep orchestration | hardware |
| `tests/` | Host pytest over the pure modules (43 tests) | — |

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

## Review outcomes (2026-06-16 deep review)

Addressed in code:
- **Clock resolution** — all on-device timing uses `time.ticks_ms`/`ticks_diff`
  (MicroPython's `time.time()` is integer seconds, too coarse for long-press/timeouts).
- **INMP441 24-bit-in-32-bit** — `recorder.py` captures at `bits=32` and downconverts
  with the host-tested `audio.pcm32_to_pcm16` (keeps the top 16 bits).
- **Upload success** — `uploader.post_wav` decides success on HTTP status, not on a
  parseable body, so a 2xx with odd JSON can't trigger a re-upload (duplicate) loop.
- **RAM** — default `MAX_DURATION_S` lowered to 60 s (~1.9 MB) so the in-RAM upload
  is PSRAM-safe; `multipart_envelope` added as the basis for the streaming path.
- **Robustness** — config coercion falls back to defaults (a bad `config.txt` can't
  brick a headless boot); a stuck/shorted button can't hang the loop (`MAX_HOLD_S`);
  empty/corrupt buffered WAVs are skipped, not shipped; filenames carry a counter to
  avoid same-second collisions.

## Open questions / bench-only items

- **Deep sleep ↔ retry reconciliation** — default is flush-on-wake (best battery);
  timed wake-to-retry is opt-in (`TIMER_WAKE`). Revisit if delivery latency annoys.
- **Streaming upload** — for clips beyond ~60 s, implement a socket-level streaming
  POST using `multipart_envelope` + `Content-Length`; can't be verified without the board.
- **Wake button pull-up** — internal pull-ups are off in deep sleep; an external
  ~100 kΩ pull-up on the (RTC-GPIO) button is needed for reliable wake. In the wiring.
- **Wake-cause auto-record** — on a button wake, ideally start recording immediately
  (check `machine.wake_reason()`) instead of falling through `flush_pending` first.
  Left as a bench task to avoid shipping untested wake-reason handling.
- **ADC accuracy / `read_uv` calibration** — the low-battery cue is in the accurate
  ADC region; full-charge voltage reporting is approximate and needs a calibrated build.
- **Capture throughput** — if the per-block `audio.pcm32_to_pcm16` loop can't keep up
  with 16 kHz on-device, optimize (viper / `memoryview.cast`) — verify against `test_audio`.

## References (verified Jun 2026)

- ESP32-S3-DevKitC-1 N16R8 spec — Espressif/board docs
- MicroPython I2S examples — github.com/miketeachman/micropython-i2s-examples
- MicroPython deep-sleep wake sources (`esp32.wake_on_ext0`) — Random Nerd Tutorials
- Multipart body construction — standard `multipart/form-data` (hand-built for `urequests`)
