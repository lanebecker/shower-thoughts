"""
ShowerThoughts ESP32-S3 firmware — entry point. Phase 1: always-on.

HARDWARE MODULE — bench-tested only. Wires the host-tested logic (config, buffer,
uploader, leds) to the on-device pieces (Wi-Fi, button, I2S recorder). Phase 1
stays awake the whole time; deep sleep + wake-on-button arrive in Phase 2.

Button UX (matches the Pi firmware):
  - short press while idle       -> start recording
  - short press while recording  -> stop + upload
  - long press (3 s)             -> cancel (no upload)

Config lives in a `config.txt` (KEY=VALUE) on the device filesystem; see
config.py for keys/defaults. Copy config.example.txt to config.txt and edit.
"""

import os
import time
import network
from machine import Pin

import config as config_mod
import buffer as buf
import leds
import uploader
import recorder

CONFIG_PATH = "config.txt"
RECORDINGS_DIR = "/recordings"

# GPIO assignments (mirror docs/hardware-guide.md).
# NOTE: BUTTON_PIN must be an RTC GPIO (0-21 on the S3) so Phase 2 can wake from
# deep sleep on a press. Pick accordingly before soldering.
BUTTON_PIN = 14
LED_RED_PIN = 4
LED_GREEN_PIN = 5
LED_BLUE_PIN = 6

LONG_PRESS_S = 3.0
DEBOUNCE_S = 0.05


class Button:
    """Active-low momentary button with an internal pull-up (pressed == 0)."""

    def __init__(self, pin_num):
        self._pin = Pin(pin_num, Pin.IN, Pin.PULL_UP)

    def pressed(self):
        return self._pin.value() == 0


def classify_press(button):
    """Block until the in-progress press resolves; return 'short', 'long', or None."""
    time.sleep(DEBOUNCE_S)
    if not button.pressed():
        return None
    t0 = time.time()
    while button.pressed():
        if time.time() - t0 >= LONG_PRESS_S:
            while button.pressed():           # wait for release so it fires once
                time.sleep(0.02)
            return "long"
        time.sleep(0.02)
    return "short"


def ensure_dir(path):
    try:
        os.mkdir(path)
    except OSError:
        pass   # already exists


def load_config():
    try:
        with open(CONFIG_PATH) as f:
            text = f.read()
    except OSError:
        text = ""
    return config_mod.parse_config(text)


def connect_wifi(ssid, password, timeout_s=15):
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    if not wlan.isconnected() and ssid:
        wlan.connect(ssid, password)
        t0 = time.time()
        while not wlan.isconnected():
            if time.time() - t0 > timeout_s:
                return False
            time.sleep(0.2)
    return wlan.isconnected()


def _timestamp():
    t = time.localtime()
    return "%04d%02d%02d_%02d%02d%02d" % (t[0], t[1], t[2], t[3], t[4], t[5])


def _send(path, name, cfg):
    """Upload one WAV; delete on success. Returns True on success."""
    with open(path, "rb") as f:
        data = f.read()          # PSRAM has room; stream from flash if clips grow
    job = uploader.post_wav(
        cfg["BACKEND_URL"] + "/upload",
        data,
        token=cfg["DEVICE_TOKEN"] or None,
        filename=name,
    )
    os.remove(path)
    return job


def flush_pending(cfg):
    """Upload buffered thoughts oldest-first; stop at the first failure."""
    for name in buf.pending_wavs(RECORDINGS_DIR):
        try:
            _send(RECORDINGS_DIR + "/" + name, name, cfg)
        except Exception:
            break   # backend still unreachable — leave the rest for next time


def record_and_upload(button, led, cfg):
    led.set("recording")
    cancelled = {"flag": False}

    def keep_going():
        # Polled between audio blocks. A press ends the recording; a long hold
        # cancels it. (Classifying the press briefly pauses capture — fine for a
        # short tap; revisit at the bench if it clips audio.)
        if button.pressed():
            if classify_press(button) == "long":
                cancelled["flag"] = True
            return False
        return True

    name = "thought_%s.wav" % _timestamp()
    path = RECORDINGS_DIR + "/" + name
    n = recorder.record(
        path,
        keep_going,
        sample_rate=config_mod.as_int(cfg, "SAMPLE_RATE"),
        max_seconds=config_mod.as_int(cfg, "MAX_DURATION_S"),
    )

    if cancelled["flag"] or n == 0:
        try:
            os.remove(path)
        except OSError:
            pass
        led.set("error"); time.sleep(0.5); led.set("off")
        return

    buf.enforce_cap(RECORDINGS_DIR, config_mod.as_int(cfg, "MAX_BUFFERED"))

    led.set("uploading")
    try:
        _send(path, name, cfg)
        led.set("done"); time.sleep(2); led.set("off")
        flush_pending(cfg)                       # opportunistically clear backlog
    except Exception:
        # Thought is safely on flash; the idle loop will retry it later.
        led.set("error"); time.sleep(1)
        led.set("buffered"); time.sleep(0.4); led.set("off")


def boot_animation(led):
    for state in ("recording", "done", "processing"):   # red, green, blue
        led.set(state); time.sleep(0.15)
    led.set("off")


def main():
    ensure_dir(RECORDINGS_DIR)
    cfg = load_config()
    led = leds.LedController(LED_RED_PIN, LED_GREEN_PIN, LED_BLUE_PIN)
    boot_animation(led)

    if connect_wifi(cfg["WIFI_SSID"], cfg["WIFI_PASSWORD"]):
        try:
            import ntptime
            ntptime.settime()           # real timestamps in filenames if reachable
        except Exception:
            pass
    else:
        led.set("error"); time.sleep(1); led.set("off")

    button = Button(BUTTON_PIN)

    while True:
        if button.pressed():
            if classify_press(button) == "short":
                record_and_upload(button, led, cfg)
            # a long press while idle is ignored (matches the Pi)
        elif buf.pending_wavs(RECORDINGS_DIR):
            flush_pending(cfg)
        time.sleep(0.05)


if __name__ == "__main__":
    main()
