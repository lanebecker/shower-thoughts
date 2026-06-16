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
  - Fast red blink: Error
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

BACKEND_URL    = os.getenv("BACKEND_URL", "http://your-server:8000")
DEVICE_TOKEN   = os.getenv("DEVICE_TOKEN", "")
RECORDINGS_DIR = Path("/tmp/shower_thoughts")
RECORDINGS_DIR.mkdir(exist_ok=True)

class State:
    IDLE      = "idle"
    RECORDING = "recording"
    UPLOADING = "uploading"
    ERROR     = "error"

_state      = State.IDLE
_recording  = False
_cancel     = False
_led_thread = None


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
    duration = time.time() - start_time
    size_kb = filepath.stat().st_size / 1024
    log.info(f"Saved {duration:.1f}s recording ({size_kb:.1f} KB) → {filepath}")
    return True

def _upload_recording(filepath: Path):
    _led_blink(g=True, interval=0.2)
    log.info(f"Uploading {filepath.name}...")
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
        log.info(f"Upload accepted, job_id={data.get('job_id')}")
        _led_solid(g=True)
        time.sleep(2)
        filepath.unlink()
    except requests.RequestException as e:
        log.error(f"Upload failed: {e}")
        _led_blink(r=True, interval=0.1)
        time.sleep(5)
    finally:
        _led_off()

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
