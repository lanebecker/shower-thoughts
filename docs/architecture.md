# Architecture

## System Diagram

```
┌──────────────────────────────────────────────────────┐
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
└────────────────────────────────────────────────────┘
                                                    │ WiFi
                                                    ▼
┌─────────────────────────────────────────────────────┐
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
└─────────────────────────────────────────────────────┘
```

> **Two device implementations, one backend contract.** The diagram shows the
> Raspberry Pi firmware (`device/`), the proven reference build. A second firmware
> for the **ESP32-S3** (`device-esp32/`, MicroPython) is in progress for v0.3.0 and
> speaks the *same* `POST /upload` multipart contract — so everything from the
> backend rightward is identical regardless of which board is in the enclosure. The
> ESP32 port adds microamp deep sleep (weeks of standby vs. the Pi's hours); its
> logic is host-tested but on-device bring-up is still pending. See
> [`esp32-port-plan.md`](esp32-port-plan.md). The component reference below
> describes the Pi firmware; the ESP32 module map lives in the port plan.

## Component Reference

### `device/recorder.py`

The firmware that runs continuously on the Pi. It listens for button presses on GPIO17: a short press starts or stops a recording session; a 3-second long press cancels the current recording without uploading. Audio is captured from the SPH0645 I2S microphone via pyaudio at the card's native 48 kHz, downsampled to 16 kHz mono, and saved as a WAV file under `/tmp/shower_thoughts/`. On stop, the WAV is multipart-POSTed to the backend. The RGB LED on GPIO22/23/24 gives immediate visual feedback for each state (recording, uploading, success, error, cancellation). A failed upload is buffered on disk and retried automatically by a background thread. An optional I2C battery monitor (ADS1115) samples the LiPo voltage and flashes an amber idle cue when it drops below a threshold; it is off unless `BATTERY_MONITOR` is set and never crashes recording if the sensor is missing or flaky.

### `device/install.sh`

One-shot provisioning script for a fresh Pi OS Lite install. Adds the I2S overlays to `/boot/firmware/config.txt` (Bookworm; falls back to `/boot/config.txt` on older images), installs `portaudio19-dev` via apt, creates a Python venv, installs pip dependencies, and registers + enables the `shower-thoughts` systemd service. Run it once; never need to run it again.

### `device/shower-thoughts.service`

Systemd unit that starts `recorder.py` after `network-online.target`. Configured with `Restart=always` so the firmware recovers from crashes. Reads device configuration from `device/.env` via `EnvironmentFile`.

### `backend/main.py`

FastAPI application with four routes: `POST /upload` (accepts a WAV file, saves it, persists a `queued` job, returns a `job_id`, and launches a background processing coroutine), `GET /job/{job_id}` (returns current job status and, when complete, the resulting note), `GET /jobs` (lists recent jobs/notes, newest first), and `GET /health` (liveness check). Job state is persisted to SQLite via `backend/jobs.py`, so it survives a backend restart. Job *processing* still runs as an in-process BackgroundTask, so the backend runs as a single uvicorn worker.

The upload path is hardened (v0.2.1): the stored filename is generated server-side as `<job_id>.wav` so the client-supplied name can't traverse out of `UPLOAD_DIR`; an ASGI middleware rejects an oversize *declared* `Content-Length` with a **413** before the body is buffered, and the handler caps the copy at `MAX_UPLOAD_BYTES` (default 25 MB) as a second layer (bound chunked uploads that omit `Content-Length` with a reverse-proxy body cap such as nginx `client_max_body_size`); the `X-Device-Token` check is a constant-time byte comparison; and transcript content is kept out of the logs unless `LOG_TRANSCRIPTS=1`. The outbound notes adapters — including the `osascript` subprocess used by the default Apple Notes adapter — set timeouts so a hung destination can't stall the worker.

### `backend/jobs.py`

A minimal persistent job store backed by SQLite (stdlib `sqlite3`). Replaces the in-memory dict used through v0.1.x, which lost in-flight jobs on restart. Exposes `create`, `update`, `get`, and `list_recent`; each call uses its own short-lived connection, so it's safe to call from background threads. Tags are stored as JSON and returned as a list.

### `backend/transcriber.py`

Thin wrapper around `openai.audio.transcriptions.create`. Takes a local WAV path, reads the file, and returns a plain transcript string. Local Whisper is stubbed in a comment for future use when running on hardware with enough RAM. Rate-limited or timed-out Whisper calls are retried with exponential backoff (honoring `Retry-After`), tunable via `WHISPER_MAX_RETRIES`, `WHISPER_RETRY_BASE_DELAY`, and `WHISPER_TIMEOUT`.

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

### `backend/adapters/email_adapter.py`

Delivers each note to any inbox over generic SMTP (`NOTES_ADAPTER=email`). Configured via `EMAIL_TO`, `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASS`, and optional `EMAIL_FROM`. Unlike `apple_notes`, this is real email to a real inbox — not a path into Apple Notes.

### `backend/adapters/craft.py`

Craft has no public REST API, so this adapter bridges to it via native mechanisms. Strategy `url_scheme` builds a `craftdocs://createdocument?...` deep link and opens it via AppleScript — requires the backend to run on the same Mac where Craft is installed. Strategy `shortcuts` POSTs the note payload as JSON to a local HTTP endpoint served by [Shortery](https://www.numberfive.co/shortery) on a nearby Mac or iPhone, which then opens the Craft URL scheme locally.

## Key Data Flows

### Happy path: button press → note in Apple Notes

1. User presses the button (GPIO17 falling edge)
2. `recorder.py` starts pyaudio stream, LED goes solid red
3. User presses again (or recording hits 300s limit)
4. pyaudio stream closes, WAV written to `/tmp/shower_thoughts/<timestamp>.wav`
5. `recorder.py` POSTs the file to `BACKEND_URL/upload`, LED starts blinking green
6. `main.py` saves the WAV, persists a `queued` job to the SQLite store (`jobs.py`), returns `{job_id: "..."}`
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
| `BATTERY_MONITOR` | ❌ | — | Set `1` to enable the optional low-battery LED (needs an I2C ADS1115) |
| `BATTERY_LOW_THRESHOLD` | ❌ | `3.5` | Volts at/below which the amber low-battery cue shows |
| `BATTERY_CHECK_INTERVAL_S` | ❌ | `300` | How often to sample the battery (seconds) |
| `BATTERY_I2C_BUS` / `BATTERY_I2C_ADDR` / `BATTERY_ADC_CHANNEL` / `BATTERY_DIVIDER_RATIO` | ❌ | `1` / `0x48` / `0` / `2.0` | ADS1115 bus, address, single-ended channel, and divider ratio |

### Backend (`backend/.env`)

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `DEVICE_TOKEN` | ❌ | — | Required by default; rejects uploads with 503 if unset (see `ALLOW_NO_DEVICE_TOKEN`) |
| `ALLOW_NO_DEVICE_TOKEN` | ❌ | — | Set `1` to allow uploads with no token (local testing only) |
| `UPLOAD_DIR` | ❌ | `/tmp/shower_uploads` | Directory for uploaded WAVs (and the default job DB) |
| `MAX_UPLOAD_BYTES` | ❌ | `26214400` (25 MB) | Max upload size; oversize declared `Content-Length` rejected with 413 before buffering (handler caps the copy too) |
| `LOG_TRANSCRIPTS` | ❌ | — | Set `1` to log a short transcript preview; default logs only the transcript length |
| `AI_PROVIDER` | ❌ | `anthropic` | `anthropic` or `openai` |
| `ANTHROPIC_API_KEY` | ✅ if provider=anthropic | — | Anthropic API key |
| `OPENAI_API_KEY` | ✅ (always — Whisper) | — | OpenAI API key; required for Whisper regardless of `AI_PROVIDER` |
| `JOBS_DB` | ❌ | `$UPLOAD_DIR/jobs.db` | SQLite path for the persistent job store |
| `WHISPER_MAX_RETRIES` | ❌ | `3` | Whisper retry attempts on rate-limit/timeout |
| `WHISPER_RETRY_BASE_DELAY` | ❌ | `2.0` | Base seconds for Whisper backoff (`base * 2**n`) |
| `WHISPER_TIMEOUT` | ❌ | `60` | Per-request Whisper timeout (seconds) |
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
| `EMAIL_TO` | ✅ if adapter=email | — | Destination inbox address |
| `SMTP_HOST` / `SMTP_PORT` | ✅ if adapter=email | — / `587` | SMTP server host and port |
| `SMTP_USER` / `SMTP_PASS` | ✅ if adapter=email | — | SMTP credentials |
| `EMAIL_FROM` | ❌ | = `SMTP_USER` | From address |

## File Map

```
shower-thoughts/
├── VERSION                          — plain-text semver
├── CHANGELOG.md                     — Keep a Changelog
├── CLAUDE.md                        — developer context for AI agents
├── README.md                        — project overview and quick start
├── requirements-dev.txt             — test deps (pytest, httpx)
├── .gitignore
├── .github/workflows/tests.yml      — CI: runs both test suites
├── docs/
│   ├── architecture.md              ← you are here
│   ├── hardware-guide.md            — BOM, wiring, enclosure (Pi + ESP32-S3)
│   ├── setup-guide.md               — Pi bring-up and backend install
│   ├── esp32-port-plan.md           — v0.3.0 ESP32-S3 firmware scope + bench checklist
│   └── roadmap.md                   — versioned feature plan
├── device/                          — Raspberry Pi firmware (proven reference build)
│   ├── recorder.py                  — firmware (runs on Pi)
│   ├── install.sh                   — Pi provisioning script
│   ├── firstrun.sh                  — guided hardware bring-up check
│   ├── shower-thoughts.service      — systemd unit
│   ├── requirements.txt             — device deps (pyaudio, RPi.GPIO, smbus2, …)
│   ├── .env.example                 — device config template
│   ├── conftest.py                  — test stubs for RPi.GPIO / pyaudio
│   └── tests/
│       ├── test_recorder.py         — buffer/flush/upload helpers
│       └── test_battery.py          — optional low-battery monitor
├── device-esp32/                    — ESP32-S3 firmware (MicroPython, v0.3.0 in progress)
│   ├── *.py                         — wavfile/audio/buffer/uploader/config/leds/
│   │                                  button/power/battery/rtcstate + recorder/main
│   ├── conftest.py                  — host stubs for machine/network/esp32/urequests
│   └── tests/                       — 43 host tests over the pure logic modules
└── backend/
    ├── main.py                      — FastAPI app
    ├── jobs.py                      — SQLite persistent job store
    ├── transcriber.py               — Whisper API wrapper (with retry)
    ├── summarizer.py                — LLM summarizer, Note dataclass
    ├── requirements.txt
    ├── .env.example                 — backend config template
    ├── conftest.py                  — test fixtures (dummy keys, isolated paths)
    ├── tests/
    │   ├── test_main.py             — API + /jobs + restart persistence
    │   ├── test_jobs.py             — JobStore unit tests
    │   ├── test_transcriber.py      — Whisper retry tests
    │   ├── test_summarizer.py
    │   ├── test_registry.py
    │   ├── test_adapters.py
    │   └── test_apple_notes_escaping.py
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

- **ESP32-S3 on-device bring-up** — the MicroPython firmware (`device-esp32/`) is host-tested but not yet flashed/validated on real hardware; deep sleep, wake-on-button, I2S capture, and live upload are bench-pending (v0.3.0)
- **Local Whisper** — transcriber.py has a stub; requires Pi 4 or beefier hardware for acceptable speed
- **Multi-device support** — backend is single-user; no device namespacing on notes
- **Web review UI** — no way to see or edit a note before it's dispatched
- **Voice activity detection** — must manually press button; no auto-start on speech
