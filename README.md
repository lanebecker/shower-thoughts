# 🚿 ShowerThoughts

[![version](https://img.shields.io/badge/version-0.2.0-blueviolet)](VERSION)

> Press a button. Record your idea. It lands in your notes app, transcribed and summarized, by the time you dry off.

## How it works

```
[Waterproof Button] → [Pi Zero 2W  ·or·  ESP32-S3] → WiFi → [Backend API]
                                                                  ↓
                                                            [Whisper API]
                                                                  ↓
                                                         [Claude / GPT-4o-mini]
                                                                  ↓
                            [Apple Notes / Notion / Obsidian / Craft / Email]
```

## Hardware platforms

ShowerThoughts has **two first-class device builds**, both speaking the exact same
backend contract (`POST /upload`), so the choice is purely about the hardware in
the enclosure:

| | **Raspberry Pi Zero 2W** | **ESP32-S3** |
|-|--------------------------|--------------|
| Status | ✅ **Proven** — shipped since v0.1.0, build it today | 🚧 **In progress** (v0.3.0) — firmware host-tested, on-device bench bring-up pending |
| Firmware | `device/` (Python) | `device-esp32/` (MicroPython) |
| Standby battery (1000 mAh) | ~6–8 h (≈ daily charge) | weeks, by spec (deep sleep) |
| Wake | always-on; ~30–40 s boot | instant wake-on-button |

The **Pi is the reference build** — fully documented and runnable end-to-end right
now. The **ESP32-S3 is the direction the project is heading**: its microamp deep
sleep turns the device from "always plugged in" into "grab it, press, talk, put it
back." The firmware logic is written and host-tested (43 tests); what remains is
bench bring-up on real silicon, so the battery numbers above are *by spec, not yet
measured*. See the [roadmap](docs/roadmap.md) and the
[ESP32 port plan](docs/esp32-port-plan.md) for status.

## Features

- 🎙️ **One-button recording** — short press to start/stop, long press to cancel
- 💡 **LED status feedback** — red (recording), blinking green (uploading), solid green (done), amber (low battery, optional)
- 🗣️ **AI transcription** — OpenAI Whisper API, accurate even with shower acoustics
- 🧠 **Structured summarization** — title, summary, full transcript, and auto-tags via Claude or GPT
- 🔌 **Pluggable destinations** — Apple Notes, Notion, Obsidian, Craft, or plain email
- 🔒 **Privacy-conscious** — audio is used only for the active job and never persisted on the backend afterward (cloud transcription today; on-device Whisper is on the roadmap)

## Hardware (Quick Reference)

The reference **Raspberry Pi** build (the one you can assemble today):

| Part | ~Cost |
|------|-------|
| Raspberry Pi Zero 2W | $15 |
| SPH0645 I2S MEMS microphone | $7 |
| IP67 16mm momentary button | $5 |
| TP4056 + MT3608 + 1000 mAh LiPo | $12 |
| RGB LED + resistors | $1 |
| Polycase WP-23 NEMA 4X polycarbonate enclosure | $20 |
| Suction cup or magnetic mount | $3 |

**Total: ~$65** — See [docs/hardware-guide.md](docs/hardware-guide.md) for the full itemized BOM, wiring diagram, and enclosure tips.

> Optional: add an **ADS1115 I2C ADC** (~$5) + a 2-resistor divider for the low-battery LED indicator. See the hardware guide.
>
> Building the **ESP32-S3** variant instead? It reuses the same enclosure, button, LED, and power path — only the board (ESP32-S3-DevKitC-1 N16R8, ~$5) and mic (INMP441) change, and the ESP32's native ADC reads the battery directly so the ADS1115 isn't needed. Full ESP32 BOM and wiring live in the [hardware guide](docs/hardware-guide.md#esp32-s3-build-recommended-for-battery-life) and the [port plan](docs/esp32-port-plan.md).

## Quick Start

### Device (Raspberry Pi — the proven build)

```bash
git clone https://github.com/lanebecker/shower-thoughts.git
cd shower-thoughts/device

cp .env.example .env
nano .env            # set BACKEND_URL to your server's address

chmod +x install.sh && sudo bash install.sh
sudo reboot
```

### Device (ESP32-S3 — in progress)

The MicroPython firmware lives in [`device-esp32/`](device-esp32/) and the logic is
host-tested today, but on-device flashing/bring-up is still being validated — treat
it as a build-along, not a finished path. See
[`device-esp32/README.md`](device-esp32/README.md) for the current status and the
flashing steps, and the [port plan](docs/esp32-port-plan.md) for what's left before
it becomes the recommended default.

### Backend

```bash
cd shower-thoughts/backend
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
nano .env            # set AI provider keys and NOTES_ADAPTER

uvicorn main:app --host 0.0.0.0 --port 8000
```

The backend exposes a small HTTP API:

| Method & path | Purpose |
|---------------|---------|
| `POST /upload` | Device uploads a WAV, gets back a `job_id` |
| `GET /job/{id}` | Poll a single job's status |
| `GET /jobs?limit=N` | List recent jobs/notes, newest first (default 50, max 200) |
| `GET /health` | Liveness check |

All endpoints except `/health` require the `X-Device-Token` header. Job state is
persisted to SQLite, so it survives a backend restart.

## Notes Adapters

Set `NOTES_ADAPTER` in `backend/.env`:

| Value | Destination |
|-------|-------------|
| `apple_notes` | Apple Notes on macOS via AppleScript (backend must run on a Mac) |
| `notion` | Notion database |
| `obsidian` | Obsidian vault (file write or Local REST API) |
| `craft` | Craft Docs (URL scheme or Shortcuts webhook) |
| `email` | Any email address via SMTP |

See `backend/.env.example` for all adapter-specific variables.

## Button UX

| Press | Action |
|-------|--------|
| Short press (idle) | Start recording — LED solid red |
| Short press (recording) | Stop and upload — LED blinks green |
| Long press 3s (recording) | Cancel — no upload, LED flashes blue |

## Documentation

- [Architecture](docs/architecture.md) — system diagram, component reference, data flows, file map
- [Hardware Guide](docs/hardware-guide.md) — full BOM, wiring, enclosure sealing, for both the Pi and ESP32-S3 builds
- [ESP32 Port Plan](docs/esp32-port-plan.md) — scope, status, and bench checklist for the v0.3.0 ESP32-S3 firmware
- [Setup Guide](docs/setup-guide.md) — Pi bring-up, backend install, systemd, troubleshooting
- [Roadmap](docs/roadmap.md) — versioned feature plan

## Adding an Adapter

1. Create `backend/adapters/your_app.py` with a class implementing `def send(self, note: Note) -> None`
2. Add an `elif` branch in `backend/adapters/registry.py`
3. Document required env vars in `backend/.env.example`

The `Note` dataclass has: `title`, `summary`, `full_text`, `tags[]`, `recorded_at`.

## License

MIT
