"""
ShowerThoughts Device Firmware
Raspberry Pi Zero 2W + SPH0645 I2S Microphone

Button behavior:
  - Short press: Start/stop recording
  - Long press (3s): Cancel current recording (no upload)

LED status:
  - Solid red:    Recording
  - Blinking green: Uploading
  - Solid green:  Upload success
  - Solid blue:   Processing (server working on it)
  - Slow blue pulse (idle): Buffered thought(s) waiting to retry
  - Fast red blink: Error
  - Amber double-blink (idle): Battery low (optional I2C monitor)

Resilience:
  A recorded thought is written to disk before upload. If the upload fails
  (WiFi down, backend unreachable), the WAV stays buffered in RECORDINGS_DIR
  and a background thread retries it every RETRY_INTERVAL_S seconds; any
  backlog is also flushed on boot. The buffer keeps the newest MAX_BUFFERED
  thoughts so a long outage can't fill the SD card.
"""

import os
import time
import wave
import audioop
import threading
import logging
import requests
import pyaudio
import RPi.GPIO as GPIO
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger(__name__)

BUTTON_PIN = 17
LED_RED    = 22
LED_GREEN  = 23
LED_BLUE   = 24

# The googlevoicehat-soundcard overlay used for the SPH0645 runs at a fixed
# 48 kHz, so capture at the native rate and downsample to 16 kHz for upload.
CAPTURE_RATE   = 48000
SAMPLE_RATE    = 16000   # target rate written to the WAV / sent to Whisper
CHANNELS       = 1
SAMPLE_WIDTH   = 2
CHUNK_SIZE     = 1024
MAX_DURATION_S = 300

RETRY_INTERVAL_S = 60    # how often the background thread retries buffered thoughts
MAX_BUFFERED     = 50    # keep at most this many buffered WAVs (newest win)

# ── Battery monitor (optional) ──────────────────────────────────────
# Opt-in low-battery LED via an I2C ADC (ADS1115) reading the LiPo through a
# resistor divider. Disabled unless BATTERY_MONITOR is truthy, so units without
# the ADC are unaffected. smbus2 is imported lazily inside the read, so the
# firmware (and its tests) import fine without the library or the hardware.
BATTERY_MONITOR          = os.getenv("BATTERY_MONITOR", "").lower() in ("1", "true", "yes")
BATTERY_LOW_THRESHOLD    = float(os.getenv("BATTERY_LOW_THRESHOLD", "3.5"))   # volts
BATTERY_CHECK_INTERVAL_S = int(os.getenv("BATTERY_CHECK_INTERVAL_S", "300"))
BATTERY_I2C_BUS          = int(os.getenv("BATTERY_I2C_BUS", "1"))
BATTERY_I2C_ADDR         = int(os.getenv("BATTERY_I2C_ADDR", "0x48"), 0)      # ADS1115 default
BATTERY_ADC_CHANNEL      = int(os.getenv("BATTERY_ADC_CHANNEL", "0"))         # AIN0..AIN3
BATTERY_DIVIDER_RATIO    = float(os.getenv("BATTERY_DIVIDER_RATIO", "2.0"))   # Vbattery / Vadc

# ADS1115: full-scale range for the gain we set (±4.096 V) over its 15-bit
# positive code range. Battery volts = raw * (FSR / 32768) * divider ratio.
_ADS1115_FSR_VOLTS      = 4.096
_ADS1115_MAX_CODE       = 32768
_ADS1115_REG_CONVERSION = 0x00
_ADS1115_REG_CONFIG     = 0x01
_ADS1115_MUX_SINGLE     = {0: 0x4, 1: 0x5, 2: 0x6, 3: 0x7}  # single-ended AINx

BACKEND_URL    = os.getenv("BACKEND_URL", "http://your-server:8000")
DEVICE_TOKEN   = os.getenv("DEVICE_TOKEN", "")
RECORDINGS_DIR = Path("/tmp/shower_thoughts")
RECORDINGS_DIR.mkdir(exist_ok=True)

# Serializes all uploads (a live one and the background retry pass) so they
# never run at the same time.
_upload_lock = threading.Lock()

class State:
    IDLE      = "idle"
    RECORDING = "recording"
    UPLOADING = "uploading"
    ERROR     = "error"

_state      = State.IDLE
_recording  = False
_cancel     = False
_led_thread = None
_battery_low = False


def _led_off():
    GPIO.output(LED_RED,   GPIO.LOW)
    GPIO.output(LED_GREEN, GPIO.LOW)
    GPIO.output(LED_BLUE,  GPIO.LOW)

def _led_solid(r=False, g=False, b=False):
    global _led_thread
    _stop_led_thread()
    GPIO.output(LED_RED,   GPIO.HIGH if r else GPIO.LOW)
    GPIO.output(LED_GREEN, GPIO.HIGH if g else GPIO.LOW)
    GPIO.output(LED_BLUE,  GPIO.HIGH if b else GPIO.LOW)

def _led_blink(r=False, g=False, b=False, interval=0.3):
    global _led_thread
    _stop_led_thread()
    stop_event = threading.Event()
    def _blink_loop():
        while not stop_event.is_set():
            GPIO.output(LED_RED,   GPIO.HIGH if r else GPIO.LOW)
            GPIO.output(LED_GREEN, GPIO.HIGH if g else GPIO.LOW)
            GPIO.output(LED_BLUE,  GPIO.HIGH if b else GPIO.LOW)
            time.sleep(interval)
            _led_off()
            time.sleep(interval)
    t = threading.Thread(target=_blink_loop, daemon=True)
    t._stop_event = stop_event
    t.start()
    _led_thread = t

def _stop_led_thread():
    global _led_thread
    if _led_thread and _led_thread.is_alive():
        _led_thread._stop_event.set()
        _led_thread.join(timeout=1)
    _led_thread = None


# ── Buffered-upload helpers ─────────────────────────────────────────

def _pending_wavs():
    """Buffered recordings, oldest first (filename timestamps sort chronologically)."""
    return sorted(RECORDINGS_DIR.glob("thought_*.wav"))

def _enforce_buffer_cap():
    """Keep only the newest MAX_BUFFERED buffered WAVs so the SD card can't fill."""
    files = _pending_wavs()
    for old in files[:-MAX_BUFFERED] if len(files) > MAX_BUFFERED else []:
        try:
            old.unlink()
            log.warning(f"Buffer cap reached; dropped oldest buffered thought: {old.name}")
        except OSError:
            pass

def _post_wav(filepath: Path) -> bool:
    """POST one WAV to the backend. On success delete it and return True."""
    headers = {}
    if DEVICE_TOKEN:
        headers["X-Device-Token"] = DEVICE_TOKEN
    try:
        with open(filepath, "rb") as f:
            resp = requests.post(
                f"{BACKEND_URL}/upload",
                files={"audio": (filepath.name, f, "audio/wav")},
                headers=headers, timeout=60,
            )
        resp.raise_for_status()
        data = resp.json()
        log.info(f"Upload accepted ({filepath.name}), job_id={data.get('job_id')}")
        filepath.unlink(missing_ok=True)
        return True
    except requests.RequestException as e:
        log.warning(f"Upload failed for {filepath.name}: {e}")
        return False

def _pending_cue():
    """Brief slow blue pulse to signal buffered thoughts are waiting to retry."""
    if _state != State.IDLE:
        return
    _led_solid(b=True)
    time.sleep(0.4)
    _led_off()

def _flush_pending() -> int:
    """Try to upload buffered thoughts, oldest first. Returns count uploaded."""
    if not _pending_wavs():
        return 0
    sent = 0
    with _upload_lock:
        _enforce_buffer_cap()
        for fp in _pending_wavs():
            if _state == State.RECORDING:
                break  # don't compete with an active recording
            if _post_wav(fp):
                sent += 1
            else:
                break  # backend still unreachable — leave the rest for next pass
    if sent:
        log.info(f"Flushed {sent} buffered thought(s).")
    return sent

def _retry_loop():
    """Background thread: periodically retry buffered thoughts while idle."""
    time.sleep(5)  # let the boot animation finish first
    while True:
        try:
            if _state == State.IDLE and _pending_wavs():
                _pending_cue()
                _flush_pending()
        except Exception as e:
            log.warning(f"Retry pass error: {e}")
        time.sleep(RETRY_INTERVAL_S)


# ── Battery monitor helpers ─────────────────────────────────────────

def _battery_voltage_from_raw(raw: int) -> float:
    """Convert a signed ADS1115 code to battery volts (divider included)."""
    return raw * (_ADS1115_FSR_VOLTS / _ADS1115_MAX_CODE) * BATTERY_DIVIDER_RATIO


def _read_battery_voltage():
    """Read LiPo voltage via the ADS1115. Returns volts, or None on any failure.

    Any I2C/library problem returns None rather than raising, so a flaky or
    absent sensor can never take down the recording firmware.
    """
    try:
        from smbus2 import SMBus  # lazy: only needed on a Pi wired to the ADC
    except ImportError:
        log.debug("smbus2 not installed; battery monitor inactive")
        return None
    mux = _ADS1115_MUX_SINGLE.get(BATTERY_ADC_CHANNEL, 0x4)
    # OS=1 (start), MUX=channel, PGA=001 (±4.096 V), MODE=1 (single-shot)
    config_hi = 0x80 | (mux << 4) | (0x1 << 1) | 0x1
    # DR=100 (128 SPS), comparator disabled (COMP_QUE=11)
    config_lo = 0x83
    try:
        with SMBus(BATTERY_I2C_BUS) as bus:
            bus.write_i2c_block_data(
                BATTERY_I2C_ADDR, _ADS1115_REG_CONFIG, [config_hi, config_lo]
            )
            time.sleep(0.01)  # ~8 ms conversion at 128 SPS, plus margin
            data = bus.read_i2c_block_data(
                BATTERY_I2C_ADDR, _ADS1115_REG_CONVERSION, 2
            )
    except Exception as e:  # noqa: BLE001 — never let a sensor fault crash recording
        log.warning(f"Battery ADC read failed: {e}")
        return None
    raw = (data[0] << 8) | data[1]
    if raw >= 0x8000:  # two's-complement negative (not expected for a battery)
        raw -= 0x10000
    return _battery_voltage_from_raw(raw)


def _battery_is_low(voltage) -> bool:
    return voltage is not None and voltage <= BATTERY_LOW_THRESHOLD


def _battery_low_cue():
    """Amber double-blink (red+green) while idle to signal a low battery."""
    if _state != State.IDLE:
        return
    for _ in range(2):
        _led_solid(r=True, g=True)  # red+green = amber
        time.sleep(0.15)
        _led_off()
        time.sleep(0.15)


def _check_battery_once():
    """Sample the battery once; update _battery_low and cue if low.

    Returns the measured voltage, or None if the read failed.
    """
    global _battery_low
    voltage = _read_battery_voltage()
    if voltage is None:
        return None
    if _battery_is_low(voltage):
        if not _battery_low:
            log.warning(f"Battery low: {voltage:.2f} V (<= {BATTERY_LOW_THRESHOLD} V)")
        _battery_low = True
        _battery_low_cue()
    else:
        if _battery_low:
            log.info(f"Battery recovered: {voltage:.2f} V")
        _battery_low = False
    return voltage


def _battery_loop():
    """Background thread: periodically check the battery and cue when low."""
    time.sleep(8)  # let the boot animation and first retry pass settle
    while True:
        try:
            if _state == State.IDLE:
                _check_battery_once()
        except Exception as e:
            log.warning(f"Battery check error: {e}")
        time.sleep(BATTERY_CHECK_INTERVAL_S)


def _record_to_file(filepath: Path) -> bool:
    global _recording, _cancel
    pa = pyaudio.PyAudio()
    device_index = None
    for i in range(pa.get_device_count()):
        info = pa.get_device_info_by_index(i)
        if info["maxInputChannels"] > 0:
            device_index = i
            log.info(f"Using audio device {i}: {info['name']}")
            break
    if device_index is None:
        log.error("No audio input device found!")
        pa.terminate()
        return False
    stream = pa.open(
        format=pyaudio.paInt16, channels=CHANNELS, rate=CAPTURE_RATE,
        input=True, input_device_index=device_index, frames_per_buffer=CHUNK_SIZE,
    )
    frames = []
    start_time = time.time()
    log.info(f"Recording to {filepath}")
    while _recording:
        if time.time() - start_time > MAX_DURATION_S:
            log.warning("Max recording duration reached, stopping")
            _recording = False
            break
        data = stream.read(CHUNK_SIZE, exception_on_overflow=False)
        frames.append(data)
    stream.stop_stream()
    stream.close()
    pa.terminate()
    if _cancel:
        log.info("Recording cancelled")
        return False
    # Downsample from the card's native capture rate to the target rate.
    # (audioop is in the stdlib through Python 3.12; if you move to 3.13+,
    # swap this for a resampler such as soxr or scipy.signal.resample_poly.)
    raw = b"".join(frames)
    if CAPTURE_RATE != SAMPLE_RATE:
        raw, _ = audioop.ratecv(raw, SAMPLE_WIDTH, CHANNELS, CAPTURE_RATE, SAMPLE_RATE, None)
    with wave.open(str(filepath), "wb") as wf:
        wf.setnchannels(CHANNELS)
        wf.setsampwidth(SAMPLE_WIDTH)
        wf.setframerate(SAMPLE_RATE)
        wf.writeframes(raw)
    _enforce_buffer_cap()
    duration = time.time() - start_time
    size_kb = filepath.stat().st_size / 1024
    log.info(f"Saved {duration:.1f}s recording ({size_kb:.1f} KB) → {filepath}")
    return True

def _upload_recording(filepath: Path):
    _led_blink(g=True, interval=0.2)
    log.info(f"Uploading {filepath.name}...")
    with _upload_lock:
        ok = _post_wav(filepath)
    if ok:
        _led_solid(g=True)
        time.sleep(2)
        _led_off()
        # We're online — opportunistically flush any older buffered thoughts.
        _flush_pending()
    else:
        # Thought is safely buffered on disk; the retry thread will send it later.
        log.info("Upload failed — thought buffered, will retry in the background.")
        _led_blink(r=True, interval=0.1)
        time.sleep(2)
        _led_off()
        _pending_cue()

def _handle_button(channel):
    global _state, _recording, _cancel
    time.sleep(0.05)
    if GPIO.input(BUTTON_PIN) == GPIO.HIGH:
        return
    press_start = time.time()
    while GPIO.input(BUTTON_PIN) == GPIO.LOW:
        if time.time() - press_start > 3.0:
            if _state == State.RECORDING:
                log.info("Long press: cancelling recording")
                _cancel = True
                _recording = False
                _led_blink(r=True, interval=0.05)
                time.sleep(1)
                _led_off()
                _state = State.IDLE
            return
        time.sleep(0.05)
    if _state == State.IDLE:
        _start_recording()
    elif _state == State.RECORDING:
        _stop_recording()

def _start_recording():
    global _state, _recording, _cancel
    _state = State.RECORDING
    _recording = True
    _cancel = False
    _led_solid(r=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filepath = RECORDINGS_DIR / f"thought_{timestamp}.wav"
    def _record_and_upload():
        global _state
        success = _record_to_file(filepath)
        if success:
            _state = State.UPLOADING
            _upload_recording(filepath)
        _state = State.IDLE
        _led_off()
    threading.Thread(target=_record_and_upload, daemon=True).start()

def _stop_recording():
    global _recording
    log.info("Button pressed: stopping recording")
    _recording = False

def main():
    log.info("ShowerThoughts starting up 🚿")
    GPIO.setmode(GPIO.BCM)
    GPIO.setwarnings(False)
    for pin in (LED_RED, LED_GREEN, LED_BLUE):
        GPIO.setup(pin, GPIO.OUT)
        GPIO.output(pin, GPIO.LOW)
    GPIO.setup(BUTTON_PIN, GPIO.IN, pull_up_down=GPIO.PUD_UP)
    GPIO.add_event_detect(BUTTON_PIN, GPIO.FALLING, callback=_handle_button, bouncetime=300)
    for color in [(True, False, False), (False, True, False), (False, False, True)]:
        _led_solid(*color)
        time.sleep(0.15)
    _led_off()
    backlog = _pending_wavs()
    if backlog:
        log.info(f"{len(backlog)} buffered thought(s) from a previous session — will retry.")
    threading.Thread(target=_retry_loop, daemon=True).start()
    if BATTERY_MONITOR:
        log.info(f"Battery monitor on (low <= {BATTERY_LOW_THRESHOLD} V, every "
                 f"{BATTERY_CHECK_INTERVAL_S}s).")
        threading.Thread(target=_battery_loop, daemon=True).start()
    log.info(f"Ready. Backend: {BACKEND_URL}")
    log.info("Press button to record. Long-press to cancel.")
    try:
        while True:
            time.sleep(0.1)
    except KeyboardInterrupt:
        log.info("Shutting down")
    finally:
        _led_off()
        GPIO.cleanup()

if __name__ == "__main__":
    main()
