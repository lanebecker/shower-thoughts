# Roadmap

Version history and planned milestones for ShowerThoughts.

---

## ✅ v0.1.0 — MVP (2026-05-26)

The core loop: press a button, talk, get a note.

- Raspberry Pi Zero 2W firmware with GPIO button and I2S microphone
- RGB LED status feedback (recording / uploading / done / error / buffered)
- FastAPI backend with async job processing
- OpenAI Whisper API transcription
- Claude Haiku / GPT-4o-mini summarization (structured title + summary + tags)
- Five pluggable notes adapters: Apple Notes, Notion, Obsidian, Craft, Email
- Craft URL scheme and Shortcuts webhook strategies
- Systemd service for autostart on boot
- Device-side buffering + background retry — a thought survives a WiFi/backend outage and uploads itself once the network returns
- Hardware reference design with full BOM (~$65)

**Why this version:** Get to "does the thing work in the shower" as fast as possible — including *not losing a thought* when the network blips, because that's the whole point of the device.

---

## ✅ v0.2.0 — Backend durability (2026-06-16)

**Why:** The device never loses a recording, but the backend kept job state in memory, so a restart forgot in-flight jobs.

- ✅ Persistent job store on the backend (SQLite, `backend/jobs.py`) instead of the in-memory dict — job state survives a backend restart
- ✅ Graceful handling of Whisper API rate limits and timeouts (exponential backoff, honors `Retry-After`, configurable via `WHISPER_*` env vars)
- ✅ `GET /jobs` endpoint to list recent notes from the backend
- ✅ Low-battery LED indicator — optional I2C ADS1115 reads the LiPo voltage and flashes an amber idle cue below threshold (`BATTERY_MONITOR`)

> Single-worker note: SQLite makes job state durable, but job *processing* still
> runs as an in-process BackgroundTask, so the backend stays single-worker by
> design. Multi-worker remains a deliberate non-goal.

---

## v0.3.0 — ESP32 firmware port

**Why:** The Pi Zero 2W has two real-world problems as a battery device. It idles around 80 mA, so a 1000 mAh cell lasts only ~6–8 hours of standby (a roughly daily charge), and it takes ~30–40 s to boot — so you can't power it down between uses to save that battery. An ESP32-S3 fixes both at once: microamp deep sleep for weeks of standby, and instant wake-on-button. That makes the device genuinely livable, so it's pulled ahead of the nice-to-haves.

Planned:
- MicroPython (or C) firmware for ESP32-S3 with INMP441 I2S mic
- Deep sleep between button presses (wake on GPIO interrupt)
- HTTP multipart upload using `urequests`
- Same LED + button UX, including the device-side buffering/retry behavior
- Hardware guide updated with ESP32 wiring as a first-class option

---

## v0.4.0 — Local transcription

**Why:** Sending audio to OpenAI means your shower monologue travels to a third-party server. Local transcription keeps it on your own hardware — and upgrades the "privacy-conscious" claim to a genuinely local one.

Planned:
- `faster-whisper` (CTranslate2) running locally on the backend
- Fallback to the API if local transcription fails or is too slow
- Performance target: transcribe a 60-second recording in under 30 seconds on a Pi 4 or M-series Mac Mini
- Configurable: `WHISPER_BACKEND=local|api`

---

## v0.5.0 — Review UI

**Why:** Sometimes the summary is wrong or the tags are off. Before a note gets dispatched, it'd be useful to see it and optionally edit it.

Planned:
- Simple web UI (served by the backend) showing pending jobs
- Edit title / summary / tags before dispatch
- "Send now" and "discard" actions
- Optional: hold dispatch until reviewed (configurable per adapter)

---

## v0.6.0 — Multi-device

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
