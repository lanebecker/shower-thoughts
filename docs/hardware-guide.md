# Hardware Guide

## Bill of Materials

| # | Part | Source | ~Cost |
|---|------|--------|---------|
| 1 | Raspberry Pi Zero 2W (with headers) | Adafruit / PiShop | $15 |
| 2 | Adafruit SPH0645 I2S MEMS microphone breakout | Adafruit #3421 | $7 |
| 3 | IP67 16mm stainless momentary push button | Amazon / AliExpress | $5 |
| 4 | TP4056 LiPo charger module (micro-USB) | Amazon | $2 |
| 5 | MT3608 boost converter module (3.7V → 5V) | Amazon | $2 |
| 6 | 1000 mAh 3.7V LiPo cell (with JST connector) | Adafruit / eBay | $8 |
| 7 | RGB LED (common cathode, 5mm) | Any | $0.50 |
| 8 | 3× 330Ω resistors | Any | $0.10 |
| 9 | Polycase WP-23 NEMA 4 polycarbonate enclosure | Polycase.com | $12 |
| 10 | Micro-USB panel mount extension cable | Amazon | $3 |
| 11 | PTFE acoustic vent membrane (3mm, peel-and-stick) | TE Connectivity / Mouser | $2 |
| 12 | M3 nylon standoffs + screws | Amazon | $1 |

**Total: ~$57** at maker quantities. Subtract $10–12 if you source the Pi from a local reseller.

### Optional / Upgrade Parts

| Part | Reason |
|------|--------|
| Magnetic suction mount (GoPro-style) | Easy removal for charging |
| Conformal coating spray | Extra water protection on PCB |
| JST 2-pin right-angle connector pair | Easier LiPo swap |
| 2000 mAh LiPo | ~2× battery life |

---

## Why I2S?

The SPH0645 uses the I2S (Inter-IC Sound) digital protocol instead of the analog output you'd find on a typical electret microphone. In a shower environment this matters: analog mics need an ADC and are susceptible to noise picked up over long PCB traces, while I2S transmits a clean digital signal that's immune to the kind of humidity-induced conductivity changes that would degrade an analog path. The SPH0645 also has a -26 dBFS sensitivity floor that handles the echo-y acoustics of a tiled bathroom well.

---

## Wiring

### I2S Microphone (SPH0645 → Pi GPIO)

```
SPH0645 Pin    Pi GPIO (BCM)    Pi Physical Pin
───────────    ─────────────    ───────────────
3V             3.3V             Pin 1
GND            GND              Pin 6
BCLK           GPIO18           Pin 12
LRCLK (WS)     GPIO19           Pin 35
DATA (DOUT)    GPIO20           Pin 38
SEL            GND              Pin 9  (selects LEFT channel)
```

### Button (GPIO17)

```
One terminal  → GPIO17 (Pin 11)
Other terminal → GND   (Pin 9)
```

The firmware uses a pull-up resistor in software (`GPIO.setup(17, GPIO.IN, pull_up_down=GPIO.PUD_UP)`), so no external resistor is needed.

### RGB LED (GPIO22/23/24)

```
Red   anode → 330Ω → GPIO22 (Pin 15)
Green anode → 330Ω → GPIO23 (Pin 16)
Blue  anode → 330Ω → GPIO24 (Pin 18)
Common cathode      → GND
```

### Power Path

```
USB-C / Micro-USB  →  TP4056 charger  →  LiPo cell
                                              ↓
                                       MT3608 boost  →  Pi 5V rail (Pin 4)
```

Connect the MT3608 input to the LiPo's positive terminal (via the TP4056 output), set the MT3608 output to 5.1V with its trim pot, and connect to the Pi's 5V GPIO pin (not the micro-USB port on the Pi, to avoid powering through two regulators). **Never power this from mains electricity inside a shower. LiPo only.**

---

## Enclosure Assembly

**Polycase WP-23** is a 4.1" × 3.2" × 1.9" polycarbonate box rated NEMA 4 (equivalent to IP65/66 — dust-tight and water jet resistant). That's enough for a shower; you don't need IP67/68 unless you're mounting it inside the spray zone.

Assembly order:

1. Drill button hole (16mm) on the front face using a step bit
2. Drill a 3mm sound inlet hole for the microphone, positioned over the SPH0645 breakout
3. Peel-and-stick the PTFE acoustic vent membrane over the sound hole from the inside — this lets sound through while blocking water droplets
4. Install the IP67 button with its silicone o-ring and hex nut
5. Cut a slot for the micro-USB panel-mount charging extension
6. Seal the USB slot edges with clear silicone RTV (let cure 24h before exposing to water)
7. Mount the Pi on M3 nylon standoffs to the enclosure floor
8. Tuck the LiPo alongside the Pi; secure with double-sided foam tape
9. Close the lid — the WP-23's foam gasket handles the waterproofing

### Mounting Options

| Method | Pros | Cons |
|--------|------|------|
| 3M Command strips | No drilling, removable | Can release in steam over months |
| Suction cup mount | Repositionable, very easy | Weaker on textured tile |
| Magnetic mount (neodymium) | Detach for charging, clean look | Requires drilling or epoxy plate |
| Tile adhesive with bracket | Most permanent | Hard to remove |

Recommended: adhesive neodymium plate on the tile + matching plate on the enclosure. Easy to pull off for charging, snaps back in place.

---

## ESP32 Alternative

If battery life or cost is a priority, an **ESP32-S3** is a capable alternative:

| | RPi Zero 2W | ESP32-S3 |
|-|-------------|----------|
| Cost | ~$15 | ~$5 |
| OS | Linux (full Python) | Bare metal / MicroPython |
| I2S mic | ✅ easy | ✅ native support |
| Firmware language | Python | C / MicroPython |
| Sleep current | ~80 mA (idle) | ~10 µA (deep sleep) |
| Battery life (1000 mAh) | ~12 hours | Weeks |
| Setup complexity | Moderate | Higher |

With an ESP32 you'd need to rewrite the firmware in MicroPython or C, implement HTTP multipart upload manually, and handle the sleep/wake cycle. The trade-off is dramatically better battery life — useful if you don't want to charge every night.

An ESP32-S3-DevKitC-1 (N16R8 variant) with the INMP441 I2S mic breakout is the recommended ESP32 combination.

---

## v0.1 Prototype Checklist

- [ ] Pi Zero 2W boots, SSH works over WiFi
- [ ] `arecord -D hw:0 -f S16_LE -r 16000 -d 5 test.wav` records audio without errors
- [ ] `aplay test.wav` plays back recognizable audio (not silence or static)
- [ ] Button press detected: `python3 -c "import RPi.GPIO as GPIO; GPIO.setmode(GPIO.BCM); GPIO.setup(17, GPIO.IN, pull_up_down=GPIO.PUD_UP); import time; time.sleep(5); print(GPIO.input(17))"`
- [ ] RGB LED cycles through red / green / blue on boot animation
- [ ] Backend reachable: `curl http://<backend-ip>:8000/health` returns `{"status":"ok"}`
- [ ] End-to-end: press button, speak, press again, note appears in configured notes app
- [ ] Enclosure closed, held under running tap for 30 seconds — no water ingress
