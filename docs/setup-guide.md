# Setup Guide

End-to-end instructions for building and running a ShowerThoughts unit. Covers Pi hardware bring-up, backend install, and systemd configuration.

---

## Part 1: Raspberry Pi Setup

### 1.1 Flash the OS

1. Download [Raspberry Pi Imager](https://www.raspberrypi.com/software/)
2. Choose **Raspberry Pi OS Lite (64-bit)** — no desktop needed
3. Click the gear icon and configure:
   - Hostname: `showerthoughts`
   - Enable SSH with password or public key auth
   - Set your WiFi SSID and password
4. Flash to a microSD card (8 GB or larger)

### 1.2 First Boot

Insert the card, power on the Pi, and SSH in:

```bash
ssh pi@showerthoughts.local
# or use the Pi's IP address if mDNS isn't working on your network
```

Update the system first:

```bash
sudo apt update && sudo apt upgrade -y
```

### 1.3 Wire the Hardware

Follow the wiring diagram in [docs/hardware-guide.md](hardware-guide.md). Key connections:

- SPH0645 I2S mic → GPIO 18 (BCLK), 19 (LRCLK), 20 (DATA), 3.3V, GND
- Button → GPIO17 and GND
- RGB LED → GPIO 22 (R), 23 (G), 24 (B) through 330Ω resistors, common cathode to GND

### 1.4 Run the Installer

Clone the repo on the Pi and run the install script:

```bash
git clone https://github.com/lanebecker/shower-thoughts.git ~/shower-thoughts
cd ~/shower-thoughts/device
chmod +x install.sh
sudo bash install.sh
```

The script will:
- Add the I2S overlays (`dtparam=i2s=on`, `dtoverlay=i2s-mmap`, `dtoverlay=googlevoicehat-soundcard`) to `/boot/firmware/config.txt` (or `/boot/config.txt` on pre-Bookworm images)
- Install `portaudio19-dev` via apt
- Create a Python venv at `device/venv/`
- Install pip dependencies
- Register and enable the `shower-thoughts` systemd service

### 1.5 Configure the Device

```bash
cp .env.example .env
nano .env
```

Set `BACKEND_URL` to the address of your backend server (e.g. `http://10.0.1.5:8000`). If you're using device token auth, set `DEVICE_TOKEN` to the same value you'll use on the backend.

### 1.6 Reboot and Verify

```bash
sudo reboot
```

After reboot, verify the I2S mic is recognized:

```bash
arecord -l
# Should show: card 0: sndrpigooglevoi [snd_rpi_googlevoicehat_soundcar], device 0: ...
```

Test a recording:

```bash
# The card runs at a fixed 48 kHz; plughw lets ALSA resample to 16 kHz for this test.
arecord -D plughw:0 -c1 -f S16_LE -r 16000 -d 5 /tmp/test.wav
aplay /tmp/test.wav
# You should hear yourself speak
```

Check the service:

```bash
sudo systemctl status shower-thoughts
journalctl -u shower-thoughts -f
# Press the button — you should see log output
```

---

## Part 2: Backend Setup

The backend can run on any machine that's reachable from the Pi over your LAN — a Mac Mini, NAS, Raspberry Pi 4, home server, or a cloud VPS. Python 3.10+ required.

### 2.1 Clone and Install

```bash
git clone https://github.com/lanebecker/shower-thoughts.git
cd shower-thoughts/backend

python3 -m venv venv
source venv/bin/activate      # Windows: venv\Scripts\activate

pip install -r requirements.txt
```

### 2.2 Configure

```bash
cp .env.example .env
nano .env
```

Minimum required configuration:

```bash
# Pick one AI provider
AI_PROVIDER=anthropic
ANTHROPIC_API_KEY=sk-ant-...

# Pick a notes adapter (Apple Notes requires the backend to run on a Mac)
NOTES_ADAPTER=apple_notes
APPLE_NOTES_FOLDER=Shower Thoughts
```

See `.env.example` for the full list of variables for all adapters.

### 2.3 Run the Backend

```bash
uvicorn main:app --host 0.0.0.0 --port 8000
```

Verify it's up:

```bash
curl http://localhost:8000/health
# {"status": "ok"}
```

### 2.4 Run as a Service (optional)

On a Mac, create a launchd plist at `~/Library/LaunchAgents/com.showerthoughts.backend.plist`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.showerthoughts.backend</string>
    <key>ProgramArguments</key>
    <array>
        <string>/path/to/venv/bin/uvicorn</string>
        <string>main:app</string>
        <string>--host</string>
        <string>0.0.0.0</string>
        <string>--port</string>
        <string>8000</string>
    </array>
    <key>WorkingDirectory</key>
    <string>/path/to/shower-thoughts/backend</string>
    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>/path/to/venv/bin:/usr/local/bin:/usr/bin:/bin</string>
    </dict>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>/tmp/showerthoughts-backend.log</string>
    <key>StandardErrorPath</key>
    <string>/tmp/showerthoughts-backend.err</string>
</dict>
</plist>
```

Load it:

```bash
launchctl load ~/Library/LaunchAgents/com.showerthoughts.backend.plist
```

On Linux, create a systemd unit analogous to `device/shower-thoughts.service`.

---

## Part 3: Notes Adapter Setup

### Apple Notes (recommended)

Apple Notes works by driving the Notes app via AppleScript, so **the backend must run on a Mac** signed into iCloud with Notes enabled. (There is no email-to-Apple-Notes address — emailing iCloud does *not* create a note.)

1. Confirm the backend host is a Mac signed into iCloud with the Notes app available
2. Set `NOTES_ADAPTER=apple_notes`
3. (Optional) Set `APPLE_NOTES_FOLDER` — defaults to `Shower Thoughts`; the folder is created automatically on first run
4. The first time the backend creates a note, macOS prompts to let it control Notes — click **OK**. If the backend runs headless under launchd, launch it once interactively first to grant this, or pre-approve it in **System Settings → Privacy & Security → Automation**

Each note arrives as a new Apple Note in the chosen folder of your iCloud account.

### Notion

1. Go to [www.notion.so/my-integrations](https://www.notion.so/my-integrations) and create a new integration
2. Copy the **Internal Integration Token** → `NOTION_API_KEY`
3. In Notion, open your target database and share it with the integration (Share → Invite)
4. Copy the database ID from the URL: `notion.so/workspace/<database_id>?v=...` → `NOTION_DATABASE_ID`
5. Your database needs these properties: `Name` (title), `Summary` (text), `Tags` (multi-select), `Recorded` (date)

### Obsidian

**File strategy** (backend on same machine as vault):

1. Set `NOTES_ADAPTER=obsidian`, `OBSIDIAN_STRATEGY=file`
2. Set `OBSIDIAN_VAULT_PATH` to the absolute path of your vault

**Webhook strategy** (over local network):

1. Install [Local REST API](https://github.com/coddingtonbear/obsidian-local-rest-api) from the Obsidian community plugins
2. Enable it and copy the API key from the plugin settings
3. Set `NOTES_ADAPTER=obsidian`, `OBSIDIAN_STRATEGY=webhook`
4. Set `OBSIDIAN_API_URL=https://127.0.0.1:27123` and `OBSIDIAN_API_KEY`

### Craft

Craft has no public REST API, so the adapter bridges via native macOS mechanisms.

**URL scheme strategy** (backend runs on your Mac):

1. Set `NOTES_ADAPTER=craft`, `CRAFT_STRATEGY=url_scheme`
2. In Craft: **Settings → (your space name) → Space Info** → copy the Space ID
3. Set `CRAFT_SPACE_ID=<your-space-id>`
4. Craft will auto-launch if it's not already running

**Shortcuts strategy** (backend on a Linux server, Craft on a Mac/iPhone):

1. On your Mac or iPhone, create a new Apple Shortcut named "ShowerThoughts to Craft"
2. Add action: **Get Variable** → Shortcut Input (Dictionary)
3. Add action: **URL** → build `craftdocs://createdocument?spaceId=[space_id]&title=[title]&content=[markdown]`
4. Add action: **Open URL**
5. Install [Shortery](https://www.numberfive.co/shortery) on macOS and expose the shortcut as an HTTP endpoint
6. Set `CRAFT_STRATEGY=shortcuts`, `CRAFT_SHORTCUTS_WEBHOOK_URL=http://<mac-ip>:<port>`

---

## Troubleshooting

### No audio device found (`arecord -l` shows nothing)

- Check that `dtoverlay=googlevoicehat-soundcard` is in `/boot/firmware/config.txt` (or `/boot/config.txt` on pre-Bookworm; the installer adds it, but it only takes effect after reboot)
- Verify SPH0645 BCLK/LRCLK/DATA wires are in the right GPIO pins
- Run `dmesg | grep snd` to see if the driver loaded

### Recording is silent or pure static

- Confirm SEL pin on SPH0645 is tied to GND (selects LEFT channel; floating = unreliable)
- Check 3.3V supply to the mic breakout
- Try `arecord -D plughw:0 -f S16_LE -r 16000 -d 5` (with `plughw` instead of `hw`) to bypass format conversion issues

### Button not detected

- Check GPIO17 is connected to one terminal of the button and GND to the other
- Test with: `python3 -c "import RPi.GPIO as GPIO; GPIO.setmode(GPIO.BCM); GPIO.setup(17, GPIO.IN, pull_up_down=GPIO.PUD_UP); print(GPIO.input(17))"`
- Expected: `1` when not pressed, `0` when pressed

### LED not lighting up

- Verify common cathode is on GND
- Test: `python3 -c "import RPi.GPIO as GPIO; GPIO.setmode(GPIO.BCM); GPIO.setup(22, GPIO.OUT); GPIO.output(22, GPIO.HIGH)"` — should light red LED

### Backend upload fails (device logs show connection error)

- Confirm backend is running: `curl http://<server-ip>:8000/health`
- Confirm Pi can reach the backend: `curl http://<server-ip>:8000/health` from the Pi
- Check firewall rules on the backend machine (port 8000 must be open on the LAN)

### Note never appears in destination app

- Check backend logs: `uvicorn` prints job progress to stdout
- Try posting a test job manually: `curl -X POST http://localhost:8000/upload -F "file=@/path/to/test.wav"`
- Check adapter-specific env vars are set in `backend/.env`
