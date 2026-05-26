# 🚿 ShowerThoughts

> Press a button. Record your idea. It lands in your notes app, transcribed and summarized, by the time you dry off.

---

## How It Works

```
[Waterproof Button] → [RPi Zero 2W] → WAV file
      ↓
[Home WiFi] → [Backend API]
      ↓
[Whisper] → transcript
      ↓
[Claude/GPT] → title + summary + tags
      ↓
[Notes Adapter] → Apple Notes / Notion / Obsidian / Craft
```

---

## Project Structure

```
shower_thoughts/
├── device/
│   ├── recorder.py          ← runs on the Raspberry Pi
│   ├── .env.example         ← copy to .env, set BACKEND_URL
│   ├── install.sh           ← setup script for the Pi
│   └── shower-thoughts.service  ← systemd unit for autostart
│
└── backend/
    ├── main.py              ← FastAPI server
    ├── transcriber.py       ← Whisper API (or local Whisper)
    ├── summarizer.py        ← Claude/GPT structures the thought
    ├── requirements.txt
    ├── .env.example         ← copy to .env, fill in API keys
    └── adapters/
        ├── registry.py      ← picks adapter from NOTES_ADAPTER env var
        ├── apple_notes.py   ← email-to-iCloud or AppleScript
        ├── notion.py        ← Notion database page
        ├── obsidian.py      ← Markdown file or Local REST API
        └── craft.py         ← craftdocs:// URL scheme or Shortcuts webhook
```

---

## Hardware (Quick Reference)

| Part | What to buy | ~Cost |
|------|------------|-------|
| Compute | Raspberry Pi Zero 2W (with headers) | $15 |
| Microphone | Adafruit SPH0645 I2S MEMS Mic | $7 |
| Button | IP67 16mm stainless momentary switch | $5 |
| Power | TP4056 + MT3608 module + 2000mAh LiPo | $10 |
| LEDs | RGB LED + 3× 330Ω resistors | $1 |
| Enclosure | Polycase WP-50 (IP65) | $12 |
| Mounting | Suction cup or magnetic mount | $5 |

See **hardware_guide.md** for full wiring, alternative parts, and ESP32 notes.

---

## Device Setup (on the Pi)

```bash
# 1. Flash Raspberry Pi OS Lite to SD card, enable SSH + WiFi in Imager
# 2. SSH in, then:
git clone https://github.com/lanebecker/shower-thoughts ~/shower_thoughts
cd ~/shower_thoughts/device
cp .env.example .env
nano .env            # set BACKEND_URL to your server's IP

bash install.sh      # installs deps, enables I2S, registers systemd service
sudo reboot

# After reboot, test audio:
arecord -D hw:0 -f S16_LE -r 16000 -d 5 test.wav && aplay test.wav

# Start the service manually first time:
sudo systemctl start shower-thoughts
journalctl -u shower-thoughts -f   # watch logs
```

---

## Backend Setup

```bash
cd shower_thoughts/backend
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
nano .env   # fill in API keys and notes adapter config

uvicorn main:app --host 0.0.0.0 --port 8000
```

For always-on hosting, run this on a home server (Mac Mini, NAS, old laptop) or deploy to Railway / Fly.io / a cheap VPS.

---

## Notes Adapter Setup

### Apple Notes (recommended)
1. Set `NOTES_ADAPTER=apple_notes` and `APPLE_NOTES_STRATEGY=email`
2. Set `APPLE_NOTES_EMAIL` to your `notes@icloud.com` address
3. Create a Gmail App Password (not your real password) for SMTP
4. Done — every thought arrives as a new Apple Note automatically

### Notion
1. Create a Notion integration at https://www.notion.so/my-integrations
2. Share your target database with the integration
3. Copy the database ID from the URL
4. Set `NOTES_ADAPTER=notion`, `NOTION_API_KEY`, `NOTION_DATABASE_ID`

Your database should have these properties: `Name` (title), `Summary` (text), `Tags` (multi-select), `Recorded` (date).

### Obsidian
1. Install the [Local REST API](https://github.com/coddingtonbear/obsidian-local-rest-api) community plugin
2. Set `NOTES_ADAPTER=obsidian`, `OBSIDIAN_STRATEGY=webhook`, `OBSIDIAN_API_URL`, `OBSIDIAN_API_KEY`

Or use `OBSIDIAN_STRATEGY=file` if the backend runs on the same machine as your vault.

### Craft
Craft doesn't have a public REST API, so there are two paths:

**url_scheme (recommended if backend runs on your Mac):**
1. Set `NOTES_ADAPTER=craft`, `CRAFT_STRATEGY=url_scheme`
2. Find your Space ID: Craft → Settings → tap your space name → copy the ID
3. Set `CRAFT_SPACE_ID=your-space-id`
4. Craft will launch automatically when a note arrives

**shortcuts (backend on a Linux server, Craft on a nearby Mac/iPhone):**
1. Create an Apple Shortcut that receives a Dictionary input and opens a `craftdocs://createdocument?...` URL built from the dictionary values
2. Expose it as a local HTTP endpoint using [Shortery](https://www.numberfive.co/shortery) (macOS) or Toolbox for Shortcuts (iOS)
3. Set `CRAFT_STRATEGY=shortcuts`, `CRAFT_SHORTCUTS_WEBHOOK_URL=http://<mac-ip>:8888`

---

## Adding a New Adapter

1. Create `backend/adapters/your_app.py` implementing a `send(note: Note)` method
2. Add a new `elif` branch in `backend/adapters/registry.py`
3. Document any required env vars in `.env.example`

The `Note` dataclass has: `title`, `summary`, `full_text`, `tags[]`, `recorded_at`.

---

## Button UX

| Press | Action |
|-------|--------|
| Short press (idle) | Start recording — LED turns solid red |
| Short press (recording) | Stop and upload — LED blinks green |
| Long press 3s (recording) | Cancel — no upload, LED flashes red |

---

## Cost Estimate (total BOM)

~$55 for a single unit at maker quantities. Sub-$30 if you use ESP32 instead of Pi.

---

## TODO / Future Ideas

- [ ] Retry queue for failed uploads (offline resilience)
- [ ] Low-battery indicator (read voltage via I2C ADC)
- [ ] Local Whisper on a beefier Pi 4 for offline/private transcription
- [ ] Companion iOS widget showing today's thoughts
- [ ] Multiple-device support (family shower thoughts... wholesome)
- [ ] Voice activity detection to auto-start recording
