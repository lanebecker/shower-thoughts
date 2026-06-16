#!/usr/bin/env bash
#
# ShowerThoughts — guided first-run / bring-up check.
# Walks the v0.1 prototype checklist interactively and reports pass/fail.
#
# Run ON THE PI, from the device/ directory:   bash firstrun.sh
#
# Safe and idempotent: it only reads state, records a short test clip to /tmp,
# briefly blinks the LED, and curls the backend. It changes nothing permanent.

set -u

BUTTON_PIN=17
LED_RED=22
LED_GREEN=23
LED_BLUE=24
ENV_FILE="${ENV_FILE:-.env}"

# Load BACKEND_URL / DEVICE_TOKEN from .env if present.
if [ -f "$ENV_FILE" ]; then
    set -a; . "$ENV_FILE"; set +a
fi
BACKEND_URL="${BACKEND_URL:-}"

pass=0; fail=0; skip=0
ok()   { printf '  \033[32m\xe2\x9c\x93 PASS\033[0m %s\n' "$1"; pass=$((pass+1)); }
bad()  { printf '  \033[31m\xe2\x9c\x97 FAIL\033[0m %s\n' "$1"; fail=$((fail+1)); }
warn() { printf '  \033[33m\xe2\x80\xa2 SKIP\033[0m %s\n' "$1"; skip=$((skip+1)); }
ask()  { local a; read -r -p "    $1 [y/N] " a < /dev/tty; [ "$a" = "y" ] || [ "$a" = "Y" ]; }

echo "ShowerThoughts first-run check"
echo "============================="

# 0. Platform sanity
if grep -qi raspberry /proc/cpuinfo 2>/dev/null || [ -e /proc/device-tree/model ]; then
    ok "Running on a Raspberry Pi"
else
    warn "Doesn't look like a Raspberry Pi - hardware checks may not be meaningful"
fi

# 1. I2S microphone recognized
echo; echo "1) I2S microphone"
if command -v arecord >/dev/null 2>&1; then
    if arecord -l 2>/dev/null | grep -qiE 'googlevoicehat|snd_rpi'; then
        ok "Sound card detected by 'arecord -l'"
    else
        bad "No googlevoicehat/snd_rpi card in 'arecord -l' (overlay inactive? reboot after install.sh)"
    fi
else
    warn "arecord not installed (sudo apt install alsa-utils)"
fi

# 2. Record + playback
echo; echo "2) Record & playback"
TEST_WAV=/tmp/shower_firstrun.wav
if command -v arecord >/dev/null 2>&1; then
    echo "    Recording 4s (speak now)..."
    if arecord -D plughw:0 -c1 -f S16_LE -r 16000 -d 4 "$TEST_WAV" >/dev/null 2>&1; then
        command -v aplay >/dev/null 2>&1 && aplay "$TEST_WAV" >/dev/null 2>&1
        if ask "Did you hear your voice clearly (not silence/static)?"; then
            ok "Mic capture works"
        else
            bad "Mic capture unclear (check SEL->GND selects LEFT, 3.3V, wiring)"
        fi
    else
        bad "arecord failed (check overlay + wiring)"
    fi
else
    warn "arecord not available"
fi

# 3. Button on GPIO17
echo; echo "3) Button (GPIO$BUTTON_PIN)"
if python3 - "$BUTTON_PIN" <<'PY'
import sys, time
try:
    import RPi.GPIO as GPIO
except Exception as e:
    print("    RPi.GPIO unavailable:", e); sys.exit(2)
pin = int(sys.argv[1])
GPIO.setmode(GPIO.BCM); GPIO.setup(pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)
print("    Press the button within 8 seconds...")
hit = False; t = time.time()
while time.time() - t < 8:
    if GPIO.input(pin) == 0:
        hit = True; break
    time.sleep(0.05)
GPIO.cleanup()
sys.exit(0 if hit else 1)
PY
then ok "Button press detected"; else bad "Button not detected (check GPIO17<->GND)"; fi

# 4. RGB LED
echo; echo "4) RGB LED"
python3 - "$LED_RED" "$LED_GREEN" "$LED_BLUE" <<'PY'
import sys, time
try:
    import RPi.GPIO as GPIO
except Exception as e:
    print("    RPi.GPIO unavailable:", e); sys.exit(2)
pins = [int(x) for x in sys.argv[1:4]]
GPIO.setmode(GPIO.BCM)
for p in pins:
    GPIO.setup(p, GPIO.OUT); GPIO.output(p, GPIO.LOW)
for p in pins:
    GPIO.output(p, GPIO.HIGH); time.sleep(0.5); GPIO.output(p, GPIO.LOW)
GPIO.cleanup()
PY
if ask "Did the LED cycle red, then green, then blue?"; then
    ok "LED works"
else
    bad "LED did not cycle (check 330R resistors, common cathode->GND, pins 22/23/24)"
fi

# 5. Backend reachable
echo; echo "5) Backend reachability"
if [ -z "$BACKEND_URL" ]; then
    bad "BACKEND_URL not set in $ENV_FILE"
elif command -v curl >/dev/null 2>&1; then
    if curl -fsS --max-time 5 "$BACKEND_URL/health" 2>/dev/null | grep -q '"status"'; then
        ok "Backend healthy at $BACKEND_URL"
    else
        bad "No healthy response from $BACKEND_URL/health (backend running? firewall open?)"
    fi
else
    warn "curl not installed"
fi

# 6. End-to-end reminder
echo; echo "6) End-to-end (manual)"
echo "    sudo systemctl start shower-thoughts, press button, speak, press again,"
echo "    and confirm a note appears in your configured notes app."

echo; echo "============================="
printf 'Summary: \033[32m%d pass\033[0m, \033[31m%d fail\033[0m, \033[33m%d skip\033[0m\n' "$pass" "$fail" "$skip"
[ "$fail" -eq 0 ]
