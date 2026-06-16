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
| 9 | Polycase WP-23 polycarbonate enclosure, NEMA 4X / IP65 (4.5 × 3.5 × 2.1 in) | Polycase.com | $20 |
| 10 | Micro-USB panel mount extension cable | Amazon | $3 |
| 11 | PTFE acoustic vent membrane (3mm, peel-and-stick) | TE Connectivity / Mouser | $2 |
| 12 | M3 nylon standoffs + screws | Amazon | $1 |

**Total: ~$65** at maker quantities. Subtract $10–12 if you source the Pi from a local reseller.

> The WP-23 replaced the discontinued WP-50. It's gray polycarbonate (not ABS) with a silicone cover gasket, rated NEMA 4X / IP65, and a little roomier inside than the old WP-50.

### Optional / Upgrade Parts

| Part | Reason |
|------|--------|
| Magnetic suction mount (GoPro-style) | Easy removal for charging |
| Conformal coating spray | Extra water protection on PCB |
| JST 2-pin right-angle connector pair | Easier LiPo swap |
| 2000 mAh LiPo | ~2× battery life |
| PTFE pressure-equalization vent (Gore-style, peel-and-stick) | Stops the enclosure "breathing" humid air past the gasket as it heats and cools |
| ADS1115 I2C ADC breakout + 2× 100 kΩ resistors (~$5) | Low-battery LED indicator — reads LiPo voltage through a divider |

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

### Battery Monitor — ADS1115 I2C ADC (optional)

The low-battery LED (an amber idle blink) reads the LiPo voltage through an
ADS1115 ADC on the I2C bus. Because a full LiPo reaches 4.2 V — above the Pi's
3.3 V logic — feed the cell through a 2-resistor divider (two equal resistors,
e.g. 100 kΩ each, halve it to ~2.1 V) into one ADC input.

```
ADS1115 Pin   Pi GPIO (BCM)    Pi Physical Pin
───────────   ─────────────    ───────────────
VDD           3.3V             Pin 1
GND           GND              Pin 9
SCL           GPIO3 (SCL1)     Pin 5
SDA           GPIO2 (SDA1)     Pin 3
A0            ← divider midpoint (LiPo+ → 100kΩ → A0 → 100kΩ → GND)
```

Enable I2C first (`install.sh` adds `dtparam=i2c_arm=on`, or run `sudo
raspi-config` → Interface Options → I2C). Confirm the chip with `i2cdetect -y 1`
(default address `0x48`). Then set `BATTERY_MONITOR=1` in `device/.env`; the
divider ratio defaults to `2.0` for two equal resistors. The feature is off by
default and a missing/flaky sensor never affects recording.

### Power Path

```
USB-C / Micro-USB  →  TP4056 charger  →  LiPo cell
                                              ↓
                                       MT3608 boost  →  Pi 5V rail (Pin 4)
```

Connect the MT3608 input to the LiPo's positive terminal (via the TP4056 output), set the MT3608 output to 5.1V with its trim pot, and connect to the Pi's 5V GPIO pin (not the micro-USB port on the Pi, to avoid powering through two regulators). **Never power this from mains electricity inside a shower. LiPo only.**

> ⚠️ **Set the MT3608 output voltage *before* you connect the Pi.** Turn the trim pot while watching a multimeter on the output and dial in 5.0–5.1V; the MT3608 ships wound up well above 5V and can push >20V, which will instantly kill a Pi.
>
> ⚠️ **Feeding 5V into the GPIO pin bypasses the Pi's input polyfuse and protection.** That's the intended setup here (it avoids double regulation), but it means a bad boost-converter setting or a short goes straight to the board — double-check polarity and voltage before powering on.

---

## Enclosure Assembly

**Polycase WP-23** is a 4.5" × 3.5" × 2.1" gray polycarbonate box rated NEMA 4X / IP65 (dust-tight, water-jet resistant), with a silicone cover gasket. That's enough for a shower; you don't need IP67/68 unless you're mounting it inside the spray zone.

Assembly order:

1. Drill button hole (16mm) on the front face using a step bit
2. Drill a 3mm sound inlet hole for the microphone, positioned over the SPH0645 breakout
3. Peel-and-stick the PTFE acoustic vent membrane over the sound hole from the inside — this lets sound through while blocking water droplets
4. (Recommended) Add a PTFE pressure-equalization vent on a side wall — as the enclosure heats up in the shower and cools afterward, the internal air pressure swings and pulls humid air past the gasket; a vent lets pressure equalize without letting water in
5. Install the IP67 button with its silicone o-ring and hex nut
6. Cut a slot for the micro-USB panel-mount charging extension
7. Seal the USB slot edges with clear silicone RTV (let cure 24h before exposing to water)
8. Mount the Pi on M3 nylon standoffs to the enclosure floor (the WP-23 has 4 mounting bosses in the base)
9. Tuck the LiPo alongside the Pi; secure with double-sided foam tape
10. Close the lid — the WP-23's silicone gasket handles the waterproofing

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
| Battery life (1000 mAh) | ~6–8 hours | Weeks |
| Setup complexity | Moderate | Higher |

With an ESP32 you'd need to rewrite the firmware in MicroPython or C, implement HTTP multipart upload manually, and handle the sleep/wake cycle. The trade-off is dramatically better battery life — the Pi Zero 2W idles around 80 mA, so a 1000 mAh cell only lasts ~6–8 hours of standby (a roughly daily charge). It also wakes instantly on a button press, whereas the Pi takes ~30–40 s to boot — so with the Pi you have to leave it powered on (and charging) between uses rather than sleeping it.

An ESP32-S3-DevKitC-1 (N16R8 variant) with the INMP441 I2S mic breakout is the recommended ESP32 combination.

### ESP32-S3 wiring (v0.3.0)

The firmware in [`../device-esp32/`](../device-esp32/) targets the
ESP32-S3-DevKitC-1 N16R8 with an INMP441 I2S mic. Default GPIO assignments below
are kept in sync with the constants at the top of `recorder.py` (I2S pins) and
`main.py` (button, LED) — change them in one place and mirror here.

```
INMP441 (I2S mic)    ESP32-S3 GPIO
─────────────────    ─────────────
VDD                  3V3
GND                  GND
SD  (data out)       GPIO11
SCK (bit clock)      GPIO12
WS  (word select)    GPIO13
L/R                  GND          (selects the left channel)

Button               GPIO14  →  GND      (active-low; firmware enables a pull-up)
                     ⚠ must be an RTC GPIO (0–21) so deep sleep can wake on a press

RGB LED (common cathode)
Red   anode  → 330Ω → GPIO4
Green anode  → 330Ω → GPIO5
Blue  anode  → 330Ω → GPIO6
Common cathode      → GND

Battery sense (optional, Phase 2)
LiPo+ → 100kΩ → GPIO1 (ADC1) → 100kΩ → GND     (divider ratio 2.0)
  set BATTERY_ADC_PIN=1 in config.txt; the ESP32 ADC reads it directly (no ADS1115)
```

Notes:
- **ADC1 pins** on the S3 are GPIO1–GPIO10; the battery divider must feed one of
  those. The divider halves the 4.2 V max LiPo to ~2.1 V, within the ADC range.
- **Power** is a bench decision: the safe default is to keep the same TP4056 +
  MT3608-to-5 V path the Pi uses and feed the board's 5 V pin (the onboard
  regulator then makes a clean 3.3 V). Powering a bare module's 3V3 rail directly
  from the LiPo is possible but marginal as the cell sags — settle this when you
  have the board in hand. **LiPo only; never mains in a shower.**

---

## v0.1 Prototype Checklist

- [ ] Pi Zero 2W boots, SSH works over WiFi
- [ ] `arecord -D plughw:0 -c1 -f S16_LE -r 16000 -d 5 test.wav` records audio without errors (the card is 48 kHz native; `plughw` resamples)
- [ ] `aplay test.wav` plays back recognizable audio (not silence or static)
- [ ] Button press detected: `python3 -c "import RPi.GPIO as GPIO; GPIO.setmode(GPIO.BCM); GPIO.setup(17, GPIO.IN, pull_up_down=GPIO.PUD_UP); import time; time.sleep(5); print(GPIO.input(17))"`
- [ ] RGB LED cycles through red / green / blue on boot animation
- [ ] Backend reachable: `curl http://<backend-ip>:8000/health` returns `{"status":"ok"}`
- [ ] End-to-end: press button, speak, press again, note appears in configured notes app
- [ ] Enclosure closed, held under running tap for 30 seconds — no water ingress
- [ ] (Optional) `i2cdetect -y 1` shows the ADS1115 at `0x48`; with `BATTERY_MONITOR=1`, a low cell shows the amber idle blink
