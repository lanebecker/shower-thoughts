"""
ShowerThoughts ESP32-S3 firmware — entry point.

HARDWARE MODULE — bench-tested only. Wires the host-tested logic (config, buffer,
uploader, leds, button, power, battery, rtcstate) to the on-device pieces (Wi-Fi,
GPIO, I2S recorder, deep sleep).

Button UX (matches the Pi firmware):
  - short press while idle       -> start recording
  - short press while recording  -> stop + upload
  - long press (3 s)             -> cancel (no upload)

Power (Phase 2, opt-in): with IDLE_SLEEP_S > 0 the device deep-sleeps after being
idle that long and wakes on a button press (~µA standby). machine.deepsleep()
resets the chip, so on wake main() re-runs from the top — it flushes any backlog
first, then waits for input. Default IDLE_SLEEP_S=0 keeps it always-on until deep
sleep is validated at the bench.

Config lives in `config.txt` (KEY=VALUE) on the device filesystem; copy
`config.example.txt` to `config.txt` and edit. See config.py for keys/defaults.
"""

import os
import time
import network
from machine import Pin

import config as config_mod
import buffer as buf
import button as button_logic
import battery
import leds
import power
import rtcstate
import uploader
import recorder

CONFIG_PATH = "config.txt"
RECORDINGS_DIR = "/recordings"

# GPIO assignments (mirror docs/hardware-guide.md).
# NOTE: BUTTON_PIN must be an RTC GPIO (0-21 on the S3) so deep-sleep wake works.
BUTTON_PIN = 14
LED_RED_PIN = 4
LED_GREEN_PIN = 5
LED_BLUE_PIN = 6

LONG_PRESS_S = 3.0
DEBOUNCE_S = 0.05
BATTERY_CHECK_INTERVAL_S = 300

_last_battery_check = 0


class Button:
    """Active-low momentary button with an internal pull-up (pressed == 0)."""

    def __init__(self, pin_num):
        self._pin = Pin(pin_num, Pin.IN, Pin.PULL_UP)

    def pressed(self):
        return self._pin.value() == 0


def classify_press(btn):
    """Block until the in-progress press resolves; return 'short', 'long', or None.

    The decision itself lives in the host-tested button.classify; this just samples
    the real pin and feeds it elapsed hold time.
    """
    time.sleep(DEBOUNCE_S)
    if not btn.pressed():
        return None
    t0 = time.time()
    while True:
        kind = button_logic.classify(
            time.time() - t0, released=not btn.pressed(), long_press_s=LONG_PRESS_S
        )
        if kind == "long":
            while btn.pressed():            # drain the hold so it fires once
                time.sleep(0.02)
            return "long"
        if kind == "short":
            return "short"
        time.sleep(0.02)


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
    """Upload one WAV; delete on success. Returns the job_id."""
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


def record_and_upload(btn, led, cfg):
    led.set("recording")
    cancelled = {"flag": False}

    def keep_going():
        # Polled between audio blocks. A press ends recording; a long hold cancels.
        if btn.pressed():
            if classify_press(btn) == "long":
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
        # Thought is safely on flash; the idle loop / next wake will retry it.
        led.set("error"); time.sleep(1)
        led.set("buffered"); time.sleep(0.4); led.set("off")


def _battery_adc(cfg):
    """Build an ADC for the battery pin, or None if the monitor is disabled."""
    pin = cfg["BATTERY_ADC_PIN"]
    if not pin:
        return None
    try:
        from machine import ADC, Pin as _Pin
        adc = ADC(_Pin(int(pin)))
        try:
            adc.atten(ADC.ATTN_11DB)   # widen the input range toward ~3.3 V
        except Exception:
            pass
        return adc
    except Exception:
        return None


def maybe_check_battery(adc, cfg, led):
    """Throttled low-battery check; flashes the amber cue when low."""
    global _last_battery_check
    if adc is None:
        return
    now = time.time()
    if now - _last_battery_check < BATTERY_CHECK_INTERVAL_S:
        return
    _last_battery_check = now
    v = battery.read_voltage(adc, config_mod.as_float(cfg, "BATTERY_DIVIDER_RATIO"))
    if battery.is_low(v, config_mod.as_float(cfg, "BATTERY_LOW_THRESHOLD")):
        led.set("low_battery"); time.sleep(0.3); led.set("off")


def go_to_sleep(cfg, led, has_backlog):
    """Configure button wake and deep-sleep (Phase 2). Resets on wake."""
    import machine
    import esp32
    led.set("off")
    # Wake when the (active-low) button goes LOW. BUTTON_PIN must be an RTC GPIO.
    esp32.wake_on_ext0(pin=Pin(BUTTON_PIN), level=esp32.WAKEUP_ALL_LOW)
    ms = power.sleep_duration_ms(
        has_backlog,
        timer_wake_enabled=cfg["TIMER_WAKE"] in ("1", "true", "yes"),
        retry_interval_s=config_mod.as_int(cfg, "RETRY_INTERVAL_S"),
    )
    if ms:
        machine.deepsleep(ms)
    else:
        machine.deepsleep()              # until a button press


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
    adc = _battery_adc(cfg)

    flush_pending(cfg)                  # on every boot/wake, clear backlog first
    maybe_check_battery(adc, cfg, led)

    idle_timeout = config_mod.as_int(cfg, "IDLE_SLEEP_S")
    last_activity = time.time()

    while True:
        if button.pressed():
            if classify_press(button) == "short":
                record_and_upload(button, led, cfg)
            # a long press while idle is ignored (matches the Pi)
            last_activity = time.time()
        else:
            if buf.pending_wavs(RECORDINGS_DIR):
                flush_pending(cfg)
            maybe_check_battery(adc, cfg, led)
            if power.should_enter_sleep(time.time() - last_activity, idle_timeout):
                go_to_sleep(cfg, led, bool(buf.pending_wavs(RECORDINGS_DIR)))
        time.sleep(0.05)


if __name__ == "__main__":
    main()
