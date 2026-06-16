#!/bin/bash
# Run on the Raspberry Pi to set up ShowerThoughts device software

set -e

echo "🚿 ShowerThoughts Device Setup"

sudo apt update
sudo apt install -y python3-pip python3-venv portaudio19-dev

# Raspberry Pi OS Bookworm (2023+) moved the boot config to /boot/firmware/config.txt.
# Prefer the new path; fall back to /boot/config.txt on older images.
if [ -f /boot/firmware/config.txt ]; then
    CONFIG=/boot/firmware/config.txt
else
    CONFIG=/boot/config.txt
fi
echo "Using boot config: $CONFIG"

if ! grep -q "dtparam=i2s=on" "$CONFIG"; then
    echo "dtparam=i2s=on" | sudo tee -a "$CONFIG"
fi
if ! grep -q "dtoverlay=i2s-mmap" "$CONFIG"; then
    echo "dtoverlay=i2s-mmap" | sudo tee -a "$CONFIG"
fi
if ! grep -q "googlevoicehat" "$CONFIG"; then
    echo "dtoverlay=googlevoicehat-soundcard" | sudo tee -a "$CONFIG"
fi

python3 -m venv venv
source venv/bin/activate
pip install pyaudio RPi.GPIO requests python-dotenv

if [ ! -f .env ]; then
    cp .env.example .env
    echo "⚠️  Edit .env with your backend URL and device token"
fi

sudo cp shower-thoughts.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable shower-thoughts
echo "✅ Done. Reboot to activate I2S overlay, then: sudo systemctl start shower-thoughts"
