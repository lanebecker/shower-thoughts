# CLAUDE.md — ShowerThoughts

Developer and AI agent context for the `lanebecker/shower-thoughts` repository.

---

## Commands

### Backend

```bash
# Install dependencies
cd backend
pip install -r requirements.txt

# Copy and configure environment
cp .env.example .env
# Edit .env with your API keys and adapter config

# Run the backend server
uvicorn main:app --reload --port 8000

# Health check
curl http://localhost:8000/health
```

### Device (Raspberry Pi)

```bash
# One-shot install (run on the Pi)
cd device
chmod +x install.sh
./install.sh

# Configure
cp .env.example .env
nano .env   # set BACKEND_URL and optionally DEVICE_TOKEN

# Run manually (for testing)
python recorder.py

# Systemd status
sudo systemctl status shower-thoughts
sudo journalctl -u shower-thoughts -f
```

### Tests

```bash
# From repo root
cd backend
pip install pytest
pytest tests/
```

---

## Configuration

All runtime config lives in `.env` files — never committed.

### Device (`device/.env`)

| Variable       | Default | Description                                      |
|----------------|---------|--------------------------------------------------|
| `BACKEND_URL`  | —       | Full URL of the backend, e.g. `http://10.0.1.5:8000` |
| `DEVICE_TOKEN` | —       | Optional shared secret for request auth          |

### Backend (`backend/.env`)

| Variable            | Default       | Description                                       |
|---------------------|---------------|---------------------------------------------------|
| `DEVICE_TOKEN`      | —             | **Required by default** — uploads return 503 if unset (see `ALLOW_NO_DEVICE_TOKEN`) |
| `ALLOW_NO_DEVICE_TOKEN` | —         | Set `1` to permit unauthenticated uploads (local testing only)     |
| `AI_PROVIDER`       | `anthropic`   | `anthropic` or `openai`                           |
| `ANTHROPIC_API_KEY` | —             | Required if `AI_PROVIDER=anthropic`               |
| `OPENAI_API_KEY`    | —             | Required regardless — Whisper transcription always uses it          |
| `NOTES_ADAPTER`     | `apple_notes` | `apple_notes`, `notion`, `obsidian`, `email`, `craft` |
| `APPLE_NOTES_FOLDER`| `Shower Thoughts` | iCloud folder for the Apple Notes adapter (macOS; auto-created) |

Adapter-specific vars are documented in `backend/.env.example` and in each adapter source file.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                        DEVICE (Pi Zero 2W)                  │
│                                                             │
│   [Button] ──► [recorder.py] ──► WAV file ──► HTTP POST    │
│                     │                                       │
│                  [LED RGB]   (status feedback)              │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼ POST /upload (multipart WAV)
┌─────────────────────────────────────────────────────────────┐
│                       BACKEND (FastAPI)                     │
│                                                             │
│   /upload ──► job queue ──► transcriber.py                  │
│                                  │                          │
│                                  ▼                          │
│                           summarizer.py                     │
│                          (Claude / GPT)                     │
│                                  │                          │
│                                  ▼                          │
│                         adapters/registry.py                │
│                                  │                          │
│          ┌───────────┬───────────┼───────────┬──────────┐  │
│          ▼           ▼           ▼           ▼          ▼  │
│     Apple Notes   Notion     Obsidian     Email       Craft │
└─────────────────────────────────────────────────────────────┘
```

### Key data flow (happy path)

1. User presses button → `recorder.py` captures I2S audio at the card's native 48 kHz (downsampled to 16 kHz before upload)
2. User presses button again → recording stops, WAV saved to `/tmp/shower_thoughts/`
3. `recorder.py` POSTs the WAV to `BACKEND_URL/upload`; LED blinks green
4. Backend saves file, returns `job_id`, spawns background task
5. `transcriber.py` sends WAV to Whisper API → returns transcript string
6. `summarizer.py` sends transcript to Claude Haiku (or GPT-4o-mini) → returns structured `Note`
7. `adapters/registry.py` loads the configured adapter and calls `.send(note)`
8. Note appears in the destination app; LED goes solid green on device

### Source files

| File | Role |
|------|------|
| `device/recorder.py` | GPIO, audio capture, HTTP upload |
| `device/install.sh` | Pi provisioning (I2S, systemd) |
| `backend/main.py` | FastAPI routes and job management |
| `backend/transcriber.py` | Whisper API wrapper |
| `backend/summarizer.py` | LLM summarization, `Note` dataclass |
| `backend/adapters/registry.py` | Adapter selection via env var |
| `backend/adapters/*.py` | One file per destination app (incl. `email_adapter.py`) |

---

## Invariants — do not regress

Deliberate decisions from the v0.1.1 hardening pass. Changing any of them reintroduces a real bug that was already fixed, so confirm with the maintainer before "fixing" one.

- **Apple Notes is AppleScript-only and macOS-only.** There is no email-to-Apple-Notes address (Apple offers no inbound notes ingestion). Do **not** re-add an `email`/SMTP strategy to `apple_notes`. The default `apple_notes` adapter requires the backend to run on a Mac signed into iCloud. For email delivery, use the separate `email` adapter.
- **Capture at 48 kHz, then downsample to 16 kHz.** The `googlevoicehat-soundcard` overlay (for the SPH0645) is fixed at 48 kHz. `recorder.py` records at 48 kHz and downsamples via `audioop.ratecv`. Do **not** open the PyAudio stream at 16 kHz — it fights the card.
- **Boot config path is `/boot/firmware/config.txt`** on Raspberry Pi OS Bookworm. `install.sh` writes there and falls back to `/boot/config.txt` only on older images. Don't hard-code the old path.
- **The I2S overlay is `googlevoicehat-soundcard`** (with `dtparam=i2s=on` and `dtoverlay=i2s-mmap`). There is no stock `i2s-mems` overlay — don't reintroduce it.
- **`DEVICE_TOKEN` is required by default.** An unset token rejects uploads with 503 unless `ALLOW_NO_DEVICE_TOKEN=1`. Don't revert to open-by-default.
- **Run a single uvicorn worker.** Job state is an in-memory dict; multiple workers break `GET /job/{id}` and lose jobs on restart. Multi-worker waits on the SQLite store (v0.2.0).
- **The device buffers failed uploads and retries them** (background thread, 60s interval, newest-50 cap, slow-blue LED cue). Do **not** delete a WAV on upload failure — only on success.
- **The Obsidian webhook uses `verify=False` on purpose** (the Local REST API plugin serves a self-signed cert on localhost); the urllib3 warning is intentionally silenced.
- **`audioop` is stdlib only through Python 3.12** (removed in 3.13+). Pi OS Bookworm ships 3.11. If you move to 3.13+, swap to `soxr` or `scipy.signal.resample_poly`.
- **The enclosure is the Polycase WP-23** (gray polycarbonate, NEMA 4X / IP65), which replaced the discontinued WP-50. Keep the BOM and docs consistent on this part.
- **All repo changes go through the GitHub API, never local `git push`** — see GitHub Push Workflow below.

---

## Testing

Unit tests live in `backend/tests/`. To add a test for a new adapter, mock `requests.post` (or the relevant HTTP call) and assert the payload shape.

There are no device-side unit tests; test `recorder.py` manually on the Pi with a real button press and watch `journalctl`.

---

## GitHub Push Workflow

This repo uses the GitHub API directly (not `git push`) for all file changes. The standard workflow:

1. Read the current file SHA via `get_file_contents`
2. Base64-encode the new content
3. Call `create_or_update_file` with the SHA to update, or omit SHA to create
4. For multi-file changes, use `push_files` with a branch ref

The `main` branch is the only branch; no PRs needed for solo work. The repo was initialized with a seed commit so `push_files` has a ref to target.

---

## Roadmap

See [`docs/roadmap.md`](docs/roadmap.md) for the full versioned plan.

Next milestone: **v0.2.0 — Backend durability**: persistent SQLite job store, `GET /jobs`, Whisper rate-limit handling, and a low-battery LED. (Device-side retry/buffering already shipped in v0.1.1; local transcription is v0.4.0 and the ESP32-S3 port is v0.3.0.)
