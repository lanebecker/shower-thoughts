# 🚿 ShowerThoughts

[![version](https://img.shields.io/badge/version-0.1.0-blueviolet)](VERSION)

> Press a button. Record your idea. It lands in your notes app, transcribed and summarized, by the time you dry off.

## How it works

```
[Waterproof Button] → [RPi Zero 2W] → WiFi → [Backend API]
                                                    ↓
                                              [Whisper API]
                                                    ↓
                                           [Claude / GPT-4o-mini]
                                                    ↓
                              [Apple Notes / Notion / Obsidian / Craft / Email]
```

## Features

- 🎙️ **One-button recording** — short press to start/stop, long press to cancel
- 💡 **LED status feedback** — red (recording), blinking green (uploading), solid green (done)
- 🗣️ **AI transcription** — OpenAI Whisper API, accurate even with shower acoustics
- 🧠 **Structured summarization** — title, summary, full transcript, and auto-tags via Claude or GPT
- 🔌 **Pluggable destinations** — Apple Notes, Notion, Obsidian, Craft, or plain email
- 🔒 **Local-first** — audio is never stored longer than the current processing job

## Hardware (Quick Reference)

| Part | ~Cost |
|------|-------|
| Raspberry Pi Zero 2W | $15 |
| SPH0645 I2S MEMS microphone | $7 |
| IP67 16mm momentary button | $5 |
| TP4056 + MT3608 + 1000 mAh LiPo | $12 |
| RGB LED + resistors | $1 |
| Polycase WP-50 IP65 enclosure | $12 |
| Suction cup or magnetic mount | $3 |

**Total: ~$55** — See [docs/hardware-guide.md](docs/hardware-guide.md) for full BOM, wiring diagram, and enclosure tips.

## Quick Start

### Device (Raspberry Pi)

```bash
git clone https://github.com/lanebecker/shower-thoughts.git
cd shower-thoughts/device

cp .env.example .env
nano .env            # set BACKEND_URL to your server's address

chmod +x install.sh && sudo bash install.sh
sudo reboot
```

### Backend

```bash
cd shower-thoughts/backend
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
nano .env            # set AI provider keys and NOTES_ADAPTER

uvicorn main:app --host 0.0.0.0 --port 8000
```

## Notes Adapters

Set `NOTES_ADAPTER` in `backend/.env`:

| Value | Destination |
|-------|-------------|
| `apple_notes` | Apple Notes via iCloud email or AppleScript |
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
- [Hardware Guide](docs/hardware-guide.md) — full BOM, wiring, enclosure sealing, ESP32 alternative
- [Setup Guide](docs/setup-guide.md) — Pi bring-up, backend install, systemd, troubleshooting
- [Roadmap](docs/roadmap.md) — versioned feature plan

## Adding an Adapter

1. Create `backend/adapters/your_app.py` with a class implementing `def send(self, note: Note) -> None`
2. Add an `elif` branch in `backend/adapters/registry.py`
3. Document required env vars in `backend/.env.example`

The `Note` dataclass has: `title`, `summary`, `full_text`, `tags[]`, `recorded_at`.

## License

MIT
