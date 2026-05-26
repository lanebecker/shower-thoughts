# Roadmap

Version history and planned milestones for ShowerThoughts.

---

## ✅ v0.1.0 — MVP (2026-05-26)

The core loop: press a button, talk, get a note.

- Raspberry Pi Zero 2W firmware with GPIO button and I2S microphone
- RGB LED status feedback (recording / uploading / done / error)
- FastAPI backend with async job processing
- OpenAI Whisper API transcription
- Claude Haiku / GPT-4o-mini summarization (structured title + summary + tags)
- Five pluggable notes adapters: Apple Notes, Notion, Obsidian, Craft, Email
- Craft URL scheme and Shortcuts webhook strategies
- Systemd service for autostart on boot
- Hardware reference design with full BOM (~$57)

**Why this version:** Get to "does the thing work in the shower" as fast as possible. No polish, no retries, no web UI — just the core loop.

---

## v0.2.0 — Resilience

**Why:** The MVP drops recordings if the WiFi hiccups or the backend is down. That's unacceptable for a thought you'll only have once.

Planned:
- Retry queue on the device — if upload fails, WAV is kept and retried on next success
- Persistent job store on the backend (SQLite) instead of in-memory dict
- Graceful handling of Whisper API rate limits and timeouts
- Low-battery LED indicator (I2C ADC reading LiPo voltage)
- `GET /jobs` endpoint to list recent notes from the backend

---

## v0.3.0 — Review UI

**Why:** Sometimes the summary is wrong or the tags are off. Before a note gets dispatched, it'd be useful to see it and optionally edit it.

Planned:
- Simple web UI (served by the backend) showing pending jobs
- Edit title / summary / tags before dispatch
- "Send now" and "discard" actions
- Optional: hold dispatch until reviewed (configurable per adapter)

---

## v0.4.0 — Local Transcription

**Why:** Sending audio to OpenAI means your shower monologue travels to a third-party server. Some people would rather not.

Planned:
- `faster-whisper` (CTranslate2) running locally on the backend
- Fallback to API if local transcription fails or is too slow
- Performance target: transcribe a 60-second recording in under 30 seconds on a Pi 4 or M-series Mac Mini
- Configurable: `WHISPER_BACKEND=local|api`

---

## v0.5.0 — ESP32 Firmware Port

**Why:** The Pi Zero 2W draws ~80 mA at idle, draining a 1000 mAh cell in ~12 hours. An ESP32 in deep sleep draws microamps, enabling weeks of battery life.

Planned:
- MicroPython firmware for ESP32-S3 with INMP441 I2S mic
- Deep sleep between button presses (wake on GPIO interrupt)
- HTTP multipart upload using `urequests`
- Same LED and button UX as Pi version
- Hardware guide updated with ESP32 wiring

---

## v0.6.0 — Multi-Device

**Why:** More than one person in the household, or more than one shower.

Planned:
- Device naming via `DEVICE_NAME` env var
- Device name embedded in note title and tags
- Per-device adapter routing (e.g. person A → Notion, person B → Obsidian)
- Backend `/devices` endpoint for configuration

---

## v1.0.0 — "Just Works"

**Why:** Everything above, polished enough to hand to a non-technical friend with a Raspberry Pi kit.

Planned:
- One-command setup: `curl -sSL install.sh | bash` provisions everything
- Auto-discovery: device finds backend on LAN via mDNS without manual IP config
- Guided web UI for initial adapter setup (OAuth flows where applicable)
- Comprehensive test coverage (unit + integration)
- Published hardware kit recommendation with sourcing links
- Stable API for community adapter plugins
