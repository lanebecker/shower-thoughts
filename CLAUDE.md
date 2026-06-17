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
# From repo root — install runtime + dev deps, then run both suites
pip install -r backend/requirements.txt -r requirements-dev.txt
(cd backend && pytest) && (cd device && pytest)
```

---

## Configuration

All runtime config lives in `.env` files — never committed.

### Device (`device/.env`)

| Variable       | Default | Description                                      |
|----------------|---------|--------------------------------------------------|
| `BACKEND_URL`  | —       | Full URL of the backend, e.g. `http://10.0.1.5:8000` |
| `DEVICE_TOKEN` | —       | Optional shared secret for request auth          |
| `BATTERY_MONITOR` | —    | Set `1` to enable the optional low-battery LED (needs an I2C ADS1115) |
| `BATTERY_LOW_THRESHOLD` | `3.5` | Volts at/below which the amber low-battery cue shows |
| `BATTERY_CHECK_INTERVAL_S` | `300` | Battery sample interval (seconds) |
| `BATTERY_I2C_BUS` / `BATTERY_I2C_ADDR` / `BATTERY_ADC_CHANNEL` / `BATTERY_DIVIDER_RATIO` | `1` / `0x48` / `0` / `2.0` | ADS1115 bus, address, channel, divider ratio |

### Backend (`backend/.env`)

| Variable            | Default       | Description                                       |
|---------------------|---------------|---------------------------------------------------|
| `DEVICE_TOKEN`      | —             | **Required by default** — uploads return 503 if unset (see `ALLOW_NO_DEVICE_TOKEN`) |
| `ALLOW_NO_DEVICE_TOKEN` | —         | Set `1` to permit unauthenticated uploads (local testing only)     |
| `AI_PROVIDER`       | `anthropic`   | `anthropic` or `openai`                           |
| `ANTHROPIC_API_KEY` | —             | Required if `AI_PROVIDER=anthropic`               |
| `OPENAI_API_KEY`    | —             | Required regardless — Whisper transcription always uses it          |
| `JOBS_DB`           | `$UPLOAD_DIR/jobs.db` | SQLite path for the persistent job store (survives restart) |
| `WHISPER_MAX_RETRIES` | `3`         | Whisper retry attempts on rate-limit/timeout before failing |
| `WHISPER_RETRY_BASE_DELAY` | `2.0`  | Base seconds for Whisper backoff (`base * 2**n`)  |
| `WHISPER_TIMEOUT`   | `60`          | Per-request Whisper timeout, seconds              |
| `NOTES_ADAPTER`     | `apple_notes` | `apple_notes`, `notion`, `obsidian`, `email`, `craft` |
| `APPLE_NOTES_FOLDER`| `Shower Thoughts` | iCloud folder for the Apple Notes adapter (macOS; auto-created) |

Adapter-specific vars are documented in `backend/.env.example` and in each adapter source file.

---

## Architecture

```
┌───────────────────────────────────────────────────┐
│                        DEVICE (Pi Zero 2W)                  │
│                                                             │
│   [Button] ──► [recorder.py] ──► WAV file ──► HTTP POST    │
│                     │                                       │
│                  [LED RGB]   (status feedback)              │
└──────────────────────────────────────────────────┘
                              │
                              ▼ POST /upload (multipart WAV)
┌────────────────────────────────────────────────┐
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
└───────────────────────────────────────────────────┘
```

### Key data flow (happy path)

1. User presses button → `recorder.py` captures I2S audio at the card's native 48 kHz (downsampled to 16 kHz before upload)
2. User presses button again → recording stops, WAV saved to `/tmp/shower_thoughts/`
3. `recorder.py` POSTs the WAV to `BACKEND_URL/upload`; LED blinks green
4. Backend saves file, records a `queued` job in the SQLite store (`jobs.py`), returns `job_id`, spawns background task
5. `transcriber.py` sends WAV to Whisper API → returns transcript string
6. `summarizer.py` sends transcript to Claude Haiku (or GPT-4o-mini) → returns structured `Note`
7. `adapters/registry.py` loads the configured adapter and calls `.send(note)`
8. Note appears in the destination app; LED goes solid green on device

> **Two device firmwares, one backend contract.** The diagram above is the
> Raspberry Pi firmware (`device/`) — the proven reference build. An ESP32-S3
> firmware (`device-esp32/`, MicroPython) is in progress for v0.3.0 and speaks the
> *same* `POST /upload` multipart contract, so the backend and everything downstream
> are board-agnostic. Treat both `device/` and `device-esp32/` as first-class; see
> the Roadmap note below for the platform-priority direction.

### Source files

| File | Role |
|------|------|
| `device/recorder.py` | GPIO, audio capture, HTTP upload (Raspberry Pi firmware) |
| `device/install.sh` | Pi provisioning (I2S, systemd) |
| `device-esp32/*.py` | ESP32-S3 MicroPython firmware (v0.3.0, in progress; host-tested logic + flash-ready `recorder.py`/`main.py`) |
| `backend/main.py` | FastAPI routes (`/upload`, `/job/{id}`, `/jobs`, `/health`) and job orchestration |
| `backend/jobs.py` | `JobStore` — persistent SQLite job store (replaces the in-memory dict) |
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
- **Run a single uvicorn worker.** As of v0.2.0 job *state* lives in SQLite (`jobs.py`), so it survives a restart — but job *processing* is an in-process FastAPI BackgroundTask that doesn't coordinate across processes. Multi-worker is a deliberate non-goal; don't add `--workers N` expecting it to work.
- **The device buffers failed uploads and retries them** (background thread, 60s interval, newest-50 cap, slow-blue LED cue). Do **not** delete a WAV on upload failure — only on success.
- **The low-battery monitor is opt-in and must never crash recording.** It's disabled unless `BATTERY_MONITOR` is set; `smbus2` is imported lazily and every I2C error is swallowed (read returns `None`), so a missing or flaky ADS1115 can't take down the firmware. Don't move the import to module top or let it raise.
- **The Obsidian webhook uses `verify=False` on purpose** (the Local REST API plugin serves a self-signed cert on localhost); the urllib3 warning is intentionally silenced.
- **`audioop` is stdlib only through Python 3.12** (removed in 3.13+). Pi OS Bookworm ships 3.11. If you move to 3.13+, swap to `soxr` or `scipy.signal.resample_poly`.
- **The enclosure is the Polycase WP-23** (gray polycarbonate, NEMA 4X / IP65), which replaced the discontinued WP-50. Keep the BOM and docs consistent on this part.
- **Repo changes are local-first** (as of 2026-06-16): edit the local clone, run the suites, then a human runs `git commit && git push`. The GitHub API is the backup. See GitHub Push Workflow below.

---

## Testing

The backend has a pytest suite in `backend/tests/` (`test_main.py`, `test_summarizer.py`, `test_registry.py`, `test_adapters.py`, `test_jobs.py`, `test_transcriber.py`, with `backend/conftest.py` supplying dummy API keys and isolating `UPLOAD_DIR`/`JOBS_DB` per test). Every external call (OpenAI/Anthropic, `subprocess`, `requests`, `smtplib`) is mocked, so it needs no real credentials or hardware. Run it with `pip install -r backend/requirements.txt -r requirements-dev.txt && cd backend && pytest`. CI runs it on every push (`.github/workflows/tests.yml`).

**Test discipline (do not skip):** any change to backend behavior must add or update the relevant tests *in the same change*, and the full suite must pass before and after. A new endpoint, module, or adapter needs new tests — e.g. a new adapter gets a test mirroring the existing ones: mock its I/O, assert the payload shape and the missing-env error. Don't push code with red or missing tests.

To add a test for a new adapter, mock `requests.post` (or the relevant HTTP call) and assert the payload shape.

The device firmware is also unit-tested in `device/tests/` (`test_recorder.py` and `test_battery.py`, with `device/conftest.py` stubbing `RPi.GPIO`/`pyaudio`): buffer cap, pending-WAV ordering, retry-flush order + stop-on-failure, `_post_wav` success/failure, and the optional battery monitor (raw→volts conversion, threshold, cue gating, read-failure safety, end-to-end read via a fake `smbus2`). Run with `cd device && pytest`; CI runs both suites. For hardware bring-up, run `bash device/firstrun.sh` on the Pi — a guided walk through the prototype checklist (mic, button, LED, backend reachability, end-to-end).

---

## GitHub Push Workflow

**Default: local-first** (as of 2026-06-16; faster than the API). The standard loop:

1. Edit files in the local clone (it lives inside the connected Cowork project folder, so the agent's file tools can reach it).
2. Run both test suites in the sandbox: `(cd backend && pytest) && (cd device && pytest)`.
3. Hand the human a single `git add -A && git commit -m "…" && git push` to run on their Mac.

The agent's sandbox never runs `git`: git's lock/hardlink operations fail on the FUSE-mounted folder ("could not lock config file … Operation not permitted"), and the sandbox can't authenticate a push. So cloning, committing, tagging, and pushing are all done by the human on their Mac (native filesystem, their credentials via `gh`/Keychain).

**Backup — GitHub API** (use when away from the Mac or no local clone is available):

1. Read the current file SHA via `get_file_contents`
2. Base64-encode the new content
3. Call `create_or_update_file` with the SHA to update, or omit SHA to create
4. For multi-file changes, use `push_files` with a branch ref

The `main` branch is the only branch; no PRs needed for solo work. Note the API tools can create/update files but **cannot create tags or releases** — tag releases locally (`git tag vX.Y.Z && git push origin vX.Y.Z`) or via the GitHub Releases UI.

---

## Roadmap

See [`docs/roadmap.md`](docs/roadmap.md) for the full versioned plan.

**v0.2.0 — Backend durability** ✅ complete (2026-06-16): persistent SQLite job store, `GET /jobs`, Whisper rate-limit/timeout handling, and the optional low-battery LED (I2C ADS1115) all shipped. Next milestones: ESP32-S3 port (v0.3.0), local transcription (v0.4.0).

**v0.3.0 — ESP32-S3 port** 🚧 in progress: hardware-independent logic is host-tested (43 tests in `device-esp32/`); `recorder.py`/`main.py` are flash-ready skeletons; on-device bench bring-up (I2S, Wi-Fi, upload, deep-sleep/wake) is pending.

**Platform-priority direction (decided 2026-06-17):** the ESP32-S3 is intended to become the **recommended primary platform** once v0.3.0 is bench-verified, on the strength of its deep-sleep battery win. Until then, **the Pi stays the proven reference build and both targets are documented as first-class** — the formal primary/secondary swap (demoting the Pi, version-bumping, rewriting quick-starts around the ESP32) is deliberately deferred so we don't demote a working platform for an unverified one. When writing docs, keep the ESP32's battery/standby numbers framed as *by spec, not yet measured*. Don't mark v0.3.0 shipped or call the Pi "legacy" until Lane confirms a green bench bring-up.
