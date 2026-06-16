# Architecture

## System Diagram

```
┌──────────────────────────────────────────────────────────────────┐
│                   DEVICE (Raspberry Pi Zero 2W)                  │
│                                                                  │
│  ┌──────────┐    ┌────────────────┐    ┌──────────────────────┐ │
│  │  Button  │───►│  recorder.py   │───►│  WAV file (/tmp/)    │ │
│  │  GPIO17  │    │                │    └──────────┬───────────┘ │
│  └──────────┘    │  GPIO22 red    │               │             │
│                  │  GPIO23 green  │    ┌──────────▼───────────┐ │
│  ┌──────────┐    │  GPIO24 blue   │    │  HTTP POST /upload   │ │
│  │ SPH0645  │───►│  (I2S audio)   │    │  (multipart WAV)     │ │
│  │   Mic    │    └────────────────┘    └──────────┬───────────┘ │
│  └──────────┘                                     │             │
└──────────────────────────────────────────────────────────────────┘
                                                    │ WiFi
                                                    ▼
┌──────────────────────────────────────────────────────────────────┐
│                    BACKEND (FastAPI / Python)                    │
│                                                                  │
│  POST /upload ──► save WAV ──► return job_id                    │
│       │                                                          │
│       └──► background task                                       │
│                    │                                             │
│                    ▼                                             │
│             transcriber.py ──► OpenAI Whisper API               │
│                    │           (returns transcript string)       │
│                    ▼                                             │
│             summarizer.py ──► Claude Haiku / GPT-4o-mini        │
│                    │           (returns Note dataclass)          │
│                    ▼                                             │
│          adapters/registry.py                                    │
│                    │                                             │
│       ┌────────────┼────────────┬────────────┬──────────┐       │
│       ▼            ▼            ▼            ▼          ▼       │
│  apple_notes    notion      obsidian       email      craft      │
└──────────────────────────────────────────────────────────────────┘
```

## Component Reference

### `device/recorder.py`

The firmware that runs continuously on the Pi. It listens for button presses on GPIO17: a short press starts or stops a recording session; a 3-second long press cancels the current recording without uploading. Audio is captured from the SPH0645 I2S microphone via pyaudio at the card's native 48 kHz, downsampled to 16 kHz mono, and saved as a WAV file under `/tmp/shower_thoughts/`. On stop, the WAV is multipart-POSTed to the backend. The RGB LED on GPIO22/23/24 gives immediate visual feedback for each state (recording, uploading, success, error, cancellation). A failed upload is buffered on disk and retried automatically by a background thread.

### `device/install.sh`

One-shot provisioning script for a fresh Pi OS Lite install. Adds the I2S overlays to `/boot/firmware/config.txt` (Bookworm; falls back to `/boot/config.txt` on older images), installs `portaudio19-dev` via apt, creates a Python venv, installs pip dependencies, and registers + enables the `shower-thoughts` systemd service. Run it once; never need to run it again.

### `device/shower-thoughts.service`

Systemd unit that starts `recorder.py` after `network-online.target`. Configured with `Restart=always` so the firmware recovers from crashes. Reads device configuration from `device/.env` via `EnvironmentFile`.

### `backend/main.py`

FastAPI application with three routes: `POST /upload` (accepts a WAV file, saves it, returns a `job_id`, and launches a background processing coroutine), `GET /job/{job_id}` (returns current job status and, when complete, the resulting note), and `GET /health` (liveness check). Job state is held in an in-memory dict — suitable for single-instance use; a future version could swap this for Redis or SQLite.

### `backend/transcriber.py`

Thin wrapper around `openai.audio.transcriptions.create`. Takes a local WAV path, reads the file, and returns a plain transcript string. Local Whisper is stubbed in a comment for future use when running on hardware with enough RAM.

### `backend/summarizer.py`

Sends the transcript to an LLM (Claude Haiku via Anthropic SDK or GPT-4o-mini via OpenAI SDK, controlled by `AI_PROVIDER`) with a system prompt that requests a structured JSON response. Parses the JSON into a `Note` dataclass: `title` (short), `summary` (1–2 sentences), `full_text` (cleaned transcript), `tags` (list of strings), `recorded_at` (ISO timestamp).

### `backend/adapters/registry.py`

Reads `NOTES_ADAPTER` from the environment and returns the appropriate adapter instance. Uses Python `Protocol` typing so any class with a `send(note: Note) -> None` method is a valid adapter.

### `backend/adapters/apple_notes.py`

Drives the macOS Notes app via an AppleScript subprocess (`osascript`), filing each note into the `APPLE_NOTES_FOLDER` iCloud folder (auto-created on first run). **Requires the backend to run on a Mac signed into iCloud.** There is no email-to-Apple-Notes path: Apple offers no inbound notes address, so the old `email` strategy never actually created notes and has been removed. For email delivery to a real inbox, use the `email` adapter instead.

### `backend/adapters/notion.py`

POSTs to `https://api.notion.com/v1/pages` using the Notion Integration token. Writes `Name`, `Summary`, `Tags` (multi-select), and `Recorded` (date) properties, plus the full transcript as a paragraph block in the page body.

### `backend/adapters/obsidian.py`

Two strategies: `file` (writes a Markdown file with YAML frontmatter directly to a vault path — requires the backend to run on the same machine as the vault) and `webhook` (PUTs the Markdown content to Obsidian's [Local REST API](https://github.com/coddingtonbear/obsidian-local-rest-api) community plugin — works over the local network).

### `backend/adapters/craft.py`

Craft has no public REST API, so this adapter bridges to it via native mechanisms. Strategy `url_scheme` builds a `craftdocs://createdocument?...` deep link and opens it via AppleScript — requires the backend to run on the same Mac where Craft is installed. Strategy `shortcuts` POSTs the note payload as JSON to a local HTTP endpoint served by [Shortery](https://www.numberfive.co/shortery) on a nearby Mac or iPhone, which then opens the Craft URL scheme locally.

## Key Data Flows

### Happy path: button press → note in Apple Notes

1. User presses the button (GPIO17 falling edge)
2. `recorder.py` starts pyaudio stream, LED goes solid red
3. User presses again (or recording hits 300s limit)
4. pyaudio stream closes, WAV written to `/tmp/shower_thoughts/<timestamp>.wav`
5. `recorder.py` POSTs the file to `BACKEND_URL/upload`, LED starts blinking green
6. `main.py` saves the WAV, inserts `{status: "pending"}` into the job store, returns `{job_id: "..."}`
7. Background coroutine calls `transcriber.transcribe_audio(path)` → Whisper API → transcript string
8. Background coroutine calls `summarizer.summarize_thought(transcript)` → LLM → `Note`
9. Background coroutine calls `registry.get_adapter().send(note)` → Apple Notes via AppleScript
10. Job store updated to `{status: "done", note: {...}}`
11. `recorder.py` receives HTTP 200, LED goes solid green

### Error path: backend unreachable

1. Steps 1–4 as above
2. `recorder.py` POSTs to `BACKEND_URL/upload`, gets a connection error (timeout, refused, etc.)
3. LED blinks red briefly, then a slow blue pulse signals the thought is buffered
4. The WAV stays in `/tmp/shower_thoughts/`; a background thread retries it every 60s (and flushes the backlog on next boot) until the backend is reachable. The buffer keeps the newest 50 recordings so a long outage can't fill the SD card.

## Configuration Reference

### Device (`device/.env`)

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `BACKEND_URL` | ✅ | — | Backend base URL, e.g. `http://10.0.1.5:8000` |
| `DEVICE_TOKEN` | ❌ | — | Shared secret sent as `X-Device-Token` header |

### Backend (`backend/.env`)

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `DEVICE_TOKEN` | ❌ | — | If set, rejects uploads without matching header |
| `AI_PROVIDER` | ❌ | `anthropic` | `anthropic` or `openai` |
| `ANTHROPIC_API_KEY` | ✅ if provider=anthropic | — | Anthropic API key |
| `OPENAI_API_KEY` | ✅ if provider=openai | — | OpenAI API key |
| `NOTES_ADAPTER` | ❌ | `apple_notes` | Which adapter to use |
| `APPLE_NOTES_FOLDER` | ❌ | `Shower Thoughts` | iCloud Notes folder, auto-created if missing (macOS only; backend must run on a Mac) |
| `NOTION_API_KEY` | ✅ if adapter=notion | — | Notion integration token |
| `NOTION_DATABASE_ID` | ✅ if adapter=notion | — | Target database ID |
| `OBSIDIAN_STRATEGY` | ❌ | `file` | `file` or `webhook` |
| `OBSIDIAN_VAULT_PATH` | ✅ if strategy=file | — | Absolute path to vault |
| `OBSIDIAN_API_URL` | ✅ if strategy=webhook | — | e.g. `https://127.0.0.1:27123` |
| `OBSIDIAN_API_KEY` | ✅ if strategy=webhook | — | Plugin API key |
| `CRAFT_STRATEGY` | ❌ | `url_scheme` | `url_scheme` or `shortcuts` |
| `CRAFT_SPACE_ID` | ✅ if adapter=craft | — | Your Craft space ID |
| `CRAFT_SHORTCUTS_WEBHOOK_URL` | ✅ if strategy=shortcuts | — | Shortery endpoint URL |

## File Map

```
shower-thoughts/
├── VERSION                          — plain-text semver
├── CHANGELOG.md                     — Keep a Changelog
├── CLAUDE.md                        — developer context for AI agents
├── README.md                        — project overview and quick start
├── .gitignore
├── docs/
│   ├── architecture.md              ← you are here
│   ├── hardware-guide.md            — BOM, wiring, enclosure
│   ├── setup-guide.md               — Pi bring-up and backend install
│   └── roadmap.md                   — versioned feature plan
├── device/
│   ├── recorder.py                  — firmware (runs on Pi)
│   ├── install.sh                   — Pi provisioning script
│   ├── shower-thoughts.service      — systemd unit
│   └── .env.example                 — device config template
└── backend/
    ├── main.py                      — FastAPI app
    ├── transcriber.py               — Whisper API wrapper
    ├── summarizer.py                — LLM summarizer, Note dataclass
    ├── requirements.txt
    ├── .env.example                 — backend config template
    └── adapters/
        ├── __init__.py
        ├── registry.py              — adapter selection
        ├── apple_notes.py
        ├── notion.py
        ├── obsidian.py
        ├── email_adapter.py
        └── craft.py
```

## What's Not Yet Implemented

- **Local Whisper** — transcriber.py has a stub; requires Pi 4 or beefier hardware for acceptable speed
- **Low-battery indicator** — LiPo voltage monitoring via I2C ADC not yet wired
- **Multi-device support** — backend is single-user; no device namespacing on notes
- **Web review UI** — no way to see or edit a note before it's dispatched
- **Voice activity detection** — must manually press button; no auto-start on speech
```
