# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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

[Unreleased]: https://github.com/lanebecker/shower-thoughts/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/lanebecker/shower-thoughts/releases/tag/v0.1.0
