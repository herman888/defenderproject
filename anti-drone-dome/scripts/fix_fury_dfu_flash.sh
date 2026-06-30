#!/bin/bash
# Fix failed DFU flash on Fury F4 OSD — mass erase + correct 2025.12.4 Spektrum hex.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/betaflight_fc_fury.env"
source "$SCRIPT_DIR/betaflight_common.sh"

HEX="/tmp/bf_FURYF4OSD_2025.12.4_spektrum.hex"

echo "=========================================="
echo "  Fury F4 OSD — DFU recovery flash"
echo "=========================================="
echo ""
echo "Quit Chrome first (Cmd+Q)."
echo ""
echo "If DFU is not active yet:"
echo "  1. Unplug USB from the FC"
echo "  2. Hold the BOOT button on the FC"
echo "  3. Plug USB while still holding BOOT"
echo "  4. Release BOOT after 3 seconds"
echo ""
echo "Waiting up to 3 minutes for DFU..."
echo ""

FOUND=0
for i in $(seq 1 180); do
  if has_dfu; then
    echo "DFU detected!"
    FOUND=1
    break
  fi
  (( i % 15 == 0 )) && echo "  still waiting... (${i}s) — do BOOT procedure now"
  sleep 1
done

if [[ $FOUND -eq 0 ]]; then
  echo ""
  echo "No DFU device found."
  echo "Try: different USB port/cable, or plug directly into Mac (no hub)."
  $DFU -l 2>&1 || true
  exit 1
fi

$DFU -l 2>&1 | grep -i "found dfu" || true
echo ""

echo "Downloading correct FURYF4OSD firmware (NOT Omnibus)..."
BF_RADIO_PROTOCOLS='["SPEKTRUM"]'
download_cloud_hex
cp -f "/tmp/bf_${BF_TARGET}_${BF_RELEASE}.hex" "$HEX" 2>/dev/null || true
[[ -f "$HEX" ]] || HEX="/tmp/bf_${BF_TARGET}_${BF_RELEASE}.hex"
echo "Firmware: $HEX ($(wc -c < "$HEX") bytes)"
echo ""

echo "Step 1: Mass erase..."
$DFU -d 0483:df11 -a 0 -s 0x08000000:force:mass-erase
sleep 2

echo ""
echo "Step 2: Flash — DO NOT UNPLUG..."
$DFU -d 0483:df11 -a 0 -s 0x08000000:leave -D "$HEX"

echo ""
echo "SUCCESS!"
echo "1. Unplug USB, wait 5 sec"
echo "2. Plug USB WITHOUT holding BOOT"
echo "3. Run:  ls /dev/cu.usb*"
echo "4. app.betaflight.com -> Connect -> Receiver -> SPEKTRUM2048"
