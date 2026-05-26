# ShowerThoughts Hardware Guide

## Recommended Platform: Raspberry Pi Zero 2W

The RPi Zero 2W hits the sweet spot for a DIY maker build:
- **WiFi built-in** (2.4GHz 802.11 b/g/n) — uploads directly, no phone tether
- **Full Linux** — Python ecosystem, ALSA audio, easy debugging over SSH
- **Tiny footprint** — 65mm × 30mm, fits in any enclosure
- **$15** — won't cry if one gets steam-damaged during iteration

Alternative: **ESP32-S3** if you want sub-$5 BOM and don't mind writing C firmware.
This guide focuses on the RPi path; ESP32 notes at the bottom.

---

## Full Bill of Materials

### Core Compute
| Part | Model | Price (approx) | Notes |
|------|-------|----------------|-------|
| Microcontroller | Raspberry Pi Zero 2W | $15 | Get the with-headers version |
| MicroSD Card | SanDisk 32GB A1 | $8 | Go name-brand; cheap cards fail in humid environments |

### Audio
| Part | Model | Price | Notes |
|------|-------|-------|-------|
| MEMS Microphone | Adafruit I2S MEMS Microphone (SPH0645LM4H) | $7 | I2S digital interface — far better SNR than analog mics, no ADC noise |
| **Alternative** | INMP441 (bare module) | $2 | Same I2S protocol, cheaper, needs a bit more wiring |

**Why I2S?** Analog mics need an ADC and pick up ground plane noise. I2S is a digital protocol that gives you clean 24-bit audio even in a noisy switching-supply environment. In a wet enclosure, this matters.

### Input / Output
| Part | Model | Price | Notes |
|------|-------|-------|-------|
| Waterproof Button | Momentary IP67 push button (16mm, SS316) | $3–8 | Search "16mm stainless waterproof momentary" on Amazon/AliExpress |
| Status LED | 5mm LED + IP67 cable gland or panel LED | $1 | Tri-color (RGB) is nice for status: red=recording, green=uploading, etc. |
| Buzzer (optional) | Passive piezo buzzer | $1 | Tactile feedback when recording starts/stops |

### Power
| Part | Model | Price | Notes |
|------|-------|-------|-------|
| LiPo Battery | 3.7V 2000–3000mAh LiPo | $8–12 | Fit size to enclosure; 2000mAh ≈ 4–5 hrs active |
| Charge/Boost Module | TP4056 + MT3608 boost (combo module) | $2 | Charges via USB-C, boosts to 5V for Pi |
| **Alternative** | Pimoroni LiPo SHIM for Pi Zero | $10 | Cleaner, plugs directly onto GPIO, includes protection |

> ⚠️ **Shower note on power:** Never run mains power into the shower. LiPo-only is the right call. Charge the device on the bathroom counter, not in the stall.

### Enclosure (the most critical part)
| Option | Details | Price |
|--------|---------|-------|
| **Recommended: Polycase WP-50** | IP65 polycarbonate, clear lid, 4.6"×3.1"×1.6" | ~$12 |
| Hammond 1555F2GY | IP65, slightly smaller, flanges for wall mount | ~$15 |
| **DIY: PVC conduit cap** | Hacky but works for v0.1 prototyping | $3 |
| Custom 3D print | PETG + silicone gasket + O-ring | $5 materials |

**Sealing tips:**
- Use **silicone sealant** (not hot glue) around cable glands and button cutouts
- Route audio through a **acoustic vent membrane** (IP67 PTFE membrane) so sound reaches the mic without water ingress. Gore-Tex acoustic membranes are the gold standard — search "Gore acoustic vent SMT" or buy an Adafruit waterproof microphone vent
- Alternatively, use the **SPH0645 behind a thin silicone membrane** — steam will get through fine, water droplets won't

### Mounting
| Part | Notes |
|------|-------|
| Suction cups (shower-rated) | iDesign or OXO shower mounts — clip your enclosure to one |
| 3M Command strips | Fine for tiles; need replacing every few months in humid environments |
| Magnetic mount | Two-part epoxy magnet on enclosure + metal plate on tile. Easiest to remove for charging |

---

## Wiring Diagram (Text)

```
RPi Zero 2W GPIO → SPH0645 I2S Mic
  3.3V  (Pin 1)  → VDD + SEL (SEL to 3.3V = Left channel)
  GND   (Pin 6)  → GND
  GPIO18 (Pin 12) → BCLK
  GPIO19 (Pin 35) → LRCLK
  GPIO20 (Pin 38) → DOUT (data from mic)

RPi Zero 2W GPIO → Button
  GPIO17 (Pin 11) → One terminal
  GND   (Pin 14)  → Other terminal
  (Enable internal pull-up in software)

RPi Zero 2W GPIO → RGB LED (common cathode)
  GPIO22 → Red (via 330Ω resistor)
  GPIO23 → Green (via 330Ω resistor)
  GPIO24 → Blue (via 330Ω resistor)
  GND    → Common cathode

TP4056+MT3608 → Pi Zero 2W
  5V out → 5V (Pin 2)
  GND    → GND (Pin 6)
  LiPo   ← Battery leads
  USB-C  ← For charging (outside enclosure via cable gland)
```

---

## Software Dependencies (on the Pi)
```bash
sudo apt install -y python3-pip portaudio19-dev
pip3 install pyaudio RPi.GPIO requests python-dotenv
# Enable I2S overlay
echo "dtoverlay=i2s-mmap" | sudo tee -a /boot/config.txt
echo "dtoverlay=googlevoicehat-soundcard" | sudo tee -a /boot/config.txt
# Or use the Adafruit I2S setup script
```

---

## ESP32 Alternative Path

If you want a leaner, cheaper device:
- **Chip:** ESP32-S3-WROOM (has I2S, WiFi, USB)
- **Mic:** INMP441 (same wiring, same I2S)
- **Framework:** ESP-IDF or Arduino + ArduinoFFT
- **Audio upload:** Record to SPIFFS/SD, POST wav file via HTTPClient
- **Tradeoff:** Firmware in C/C++, no Python ecosystem, harder to iterate but much lower BOM cost (~$5 total)
- The backend API is identical — only the device firmware changes

---

## v0.1 Prototype Checklist

- [ ] RPi Zero 2W + SD card, SSH enabled, WiFi configured
- [ ] SPH0645 wired to I2S pins, `arecord -D hw:0 test.wav` produces audio
- [ ] Button on GPIO17, test with a simple GPIO.input() loop
- [ ] LiPo + boost module powering the Pi (measure voltage first!)
- [ ] Everything fits in enclosure with cable glands sealed
- [ ] Backend API running on a home server or cloud instance
- [ ] Test recording → upload → transcription → note end-to-end
- [ ] Hang it in the shower and have a thought 🚿
