#!/bin/bash
# Flash OMNIBUSF4 via ST-Link when USB serial/DFU are dead.
# Restores 2025.12.4 (last known working version).
#
# Wiring: ST-Link GND/SWDIO/SWCLK -> FC pads. Power FC with battery.
# Install: brew install stlink
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/betaflight_fc_omnibus.env"
source "$SCRIPT_DIR/betaflight_common.sh"

HEX="/tmp/bf_OMNIBUSF4_2025.12.4.hex"

if ! command -v st-flash >/dev/null 2>&1; then
  echo "Install ST-Link tools:  brew install stlink"
  exit 1
fi

BF_RELEASE="2025.12.4"
BF_RADIO_PROTOCOLS='["CRSF"]'
download_cloud_hex
[[ -f "$HEX" ]] || cp "/tmp/bf_${BF_TARGET}_${BF_RELEASE}.hex" "$HEX"

echo "=== ST-Link restore: ${BF_BOARD_NAME} / ${BF_RELEASE} ==="
echo "Wire GND, SWDIO, SWCLK. Battery on, props off."
read -r -p "Press Enter when ready..."

st-info --probe 2>&1 | head -15
if ! st-info --probe 2>&1 | grep -qi "found"; then
  echo "No ST-Link / STM32 detected. Check wiring."
  exit 1
fi

echo "Erasing chip..."
st-flash erase
echo "Flashing $HEX ..."
st-flash --reset write "$HEX" 0x08000000

echo ""
echo "Done. Disconnect ST-Link, replug USB, run: ls /dev/cu.usb*"
