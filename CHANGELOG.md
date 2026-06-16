# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

Changes on `main` since the v0.1.1 tag (not yet released — promote to v0.1.2 when tagging).

### Added

- **Backend test suite** (`backend/tests/`: `test_main`, `test_summarizer`, `test_registry`, `test_adapters`, `test_apple_notes_escaping`) plus `requirements-dev.txt`, and **device-firmware tests** (`device/tests/test_recorder.py` with `device/conftest.py` stubbing `RPi.GPIO`/`pyaudio`) — 37 tests, every external call mocked.
- **CI** (`.github/workflows/tests.yml`) — runs both suites on every push and PR.
- **`device/firstrun.sh`** — a guided, interactive hardware bring-up check (mic, button, LED, backend reachability, end-to-end).

### Fixed

- **Systemd unit** (`device/shower-thoughts.service`) paths corrected from `shower_thoughts` to `shower-thoughts` to match the clone directory, so the service actually starts.

### Changed

- Expanded `CLAUDE.md` with an "Invariants — do not regress" section and Testing / test-discipline notes (kept mirrored to the local project file).

## [0.1.1] - 2026-06-15

Hardening and correctness pass over the v0.1.0 MVP: the core loop now survives a
network outage, the device actually provisions on current Raspberry Pi OS, the
default notes path works, and the docs match the code.

### Added

- **Device-side buffering + background retry** (`device/recorder.py`) — a failed upload is kept on disk and retried every 60s by a background thread; the backlog is also flushed on boot and after a successful live upload. A slow blue LED pulse signals buffered thoughts, and the buffer keeps the newest 50 recordings so a long outage can't fill the SD card.
- **Email notes adapter** (`backend/adapters/email_adapter.py`) — generic SMTP delivery, so `NOTES_ADAPTER=email` works instead of crashing on import.
- **Hardware safety guidance** — MT3608 "set the output voltage before connecting the Pi" warning, a note that feeding 5V into the GPIO pin bypasses the input polyfuse, and a PTFE pressure-equalization vent recommendation for the enclosure.

### Changed

- **Apple Notes adapter** is now AppleScript-only (macOS), auto-creates its target folder, and renders the note body as HTML. The non-functional "email to `notes@icloud.com`" strategy (never a real Apple feature) was removed; `apple_notes` is documented as requiring the backend to run on a Mac.
- **I2S capture** records at the card's native 48 kHz and downsamples to 16 kHz (the `googlevoicehat-soundcard` overlay is fixed at 48 kHz).
- **`install.sh`** writes overlays to `/boot/firmware/config.txt` on Raspberry Pi OS Bookworm, falling back to `/boot/config.txt` on older images.
- **Backend auth is secure by default** — uploads are rejected with 503 when `DEVICE_TOKEN` is unset; opt out for local testing with `ALLOW_NO_DEVICE_TOKEN=1`.
- **Enclosure** standardized on the Polycase WP-23 (gray polycarbonate, NEMA 4X / IP65, 4.5 × 3.5 × 2.1 in) across all docs; corrected the BOM total to ~$65.
- **README** "Local-first" claim reworded to "Privacy-conscious" to reflect that audio is sent to cloud Whisper/LLM for the active job.
- **Roadmap re-sequenced** — retry/buffering folded into v0.1.0; the ESP32-S3 port pulled forward to v0.3.0 (battery + boot-time win); local transcription → v0.4.0, review UI → v0.5.0.
- Corrected the battery estimate to ~6–8 hours of standby and documented the boot-time tradeoff that motivates the ESP32 path.

### Fixed

- Setup/architecture docs referenced a nonexistent `i2s-mems` overlay and a `hw:0 -r 16000` test command that fails against the 48 kHz card; corrected to `googlevoicehat-soundcard` and `plughw:0`.
- Silenced the Obsidian webhook's repeated `InsecureRequestWarning` for the Local REST API's self-signed certificate.
- Documented the single-worker constraint of the in-memory job store.

### Security

- Upload and job endpoints now require `DEVICE_TOKEN` by default, so an unconfigured backend is no longer left open on the LAN.

## [0.1.0] - 2026-05-26

### Added

- **Device firmware** (`device/recorder.py`) — Raspberry Pi Zero 2W Python script for waterproof button-triggered audio recording
  - Short press to start/stop recording; 3-second long press to cancel
  - RGB LED status: solid red (recording), blinking green (uploading), solid green (success), solid blue (cancellation)
  - I2S MEMS microphone capture at 16 kHz mono via pyaudio, max 300 seconds per recording
  - WAV upload to backend via HTTP POST with optional device token auth
  - Boot animation (RGB cycle) to confirm device is live
- **Device installer** (`device/install.sh`) — one-shot script for I2S dtoverlay, portaudio, venv creation, systemd enable
- **Systemd unit** (`device/shower-thoughts.service`) — starts after network, auto-restarts on failure
- **Backend API** (`backend/main.py`) — FastAPI service with `POST /upload`, `GET /job/{id}`, `GET /health`; async background job processing
- **Transcription** (`backend/transcriber.py`) — OpenAI Whisper API integration; local whisper stubbed for future use
- **Summarization** (`backend/summarizer.py`) — structured `Note` output (title, summary, full_text, tags, recorded_at) via Claude Haiku or GPT-4o-mini
- **Pluggable notes adapter system** (`backend/adapters/`) — registry pattern; swap destinations via `NOTES_ADAPTER` env var
  - **Apple Notes adapter** — SMTP-to-iCloud or macOS AppleScript strategies
  - **Notion adapter** — creates pages in a Notion database via REST API
  - **Obsidian adapter** — writes Markdown files to vault directory or Local REST API plugin
  - **Email adapter** — generic SMTP fallback for any notes-via-email workflow
  - **Craft adapter** — craftdocs:// URL scheme via AppleScript, or Shortcuts webhook via Shortery (macOS / iOS)
- **Hardware reference design** — Raspberry Pi Zero 2W + SPH0645 I2S microphone + LiPo power + IP65 Polycase enclosure; full BOM ~$55

[Unreleased]: https://github.com/lanebecker/shower-thoughts/compare/v0.1.1...HEAD
[0.1.1]: https://github.com/lanebecker/shower-thoughts/compare/v0.1.0...v0.1.1
[0.1.0]: https://github.com/lanebecker/shower-thoughts/releases/tag/v0.1.0
