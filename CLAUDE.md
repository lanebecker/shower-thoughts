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
| `DEVICE_TOKEN`      | —             | Must match the device token if set                |
| `AI_PROVIDER`       | `anthropic`   | `anthropic` or `openai`                           |
| `ANTHROPIC_API_KEY` | —             | Required if `AI_PROVIDER=anthropic`               |
| `OPENAI_API_KEY`    | —             | Required if `AI_PROVIDER=openai`                  |
| `NOTES_ADAPTER`     | `apple_notes` | `apple_notes`, `notion`, `obsidian`, `email`, `craft` |

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

1. User presses button → `recorder.py` starts capturing I2S audio at 16 kHz
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
| `backend/adapters/*.py` | One file per destination app |

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

Next milestone: **v0.2.0** — local Whisper option, retry queue, better error recovery.
