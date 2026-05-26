#!/bin/bash
# Run on the Raspberry Pi to set up ShowerThoughts device software

set -e

echo "🚿 ShowerThoughts Device Setup"

sudo apt update
sudo apt install -y python3-pip python3-venv portaudio19-dev

if ! grep -q "dtoverlay=i2s-mmap" /boot/config.txt; then
    echo "dtoverlay=i2s-mmap" | sudo tee -a /boot/config.txt
fi
if ! grep -q "googlevoicehat" /boot/config.txt; then
    echo "dtoverlay=googlevoicehat-soundcard" | sudo tee -a /boot/config.txt
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
