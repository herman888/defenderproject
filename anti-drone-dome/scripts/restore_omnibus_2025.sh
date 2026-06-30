#!/bin/bash
# Restore Omnibus F4 to Betaflight 2025.12.4 — last known working USB version.
#
# Usage (from anti-drone-dome folder):
#   bash scripts/restore_omnibus_2025.sh
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/betaflight_fc_omnibus.env"
source "$SCRIPT_DIR/betaflight_common.sh"

HEX="/tmp/bf_OMNIBUSF4_2025.12.4.hex"
FLASHED=0

flash_omnibus() {
  echo ""
  echo "Step 1: Mass erase (clears bad 3.5.7 downgrade + old config)..."
  $DFU -d 0483:df11 -a 0 -s 0x08000000:force:mass-erase 2>/dev/null || true
  sleep 2
  echo ""
  echo "Step 2: Flashing OMNIBUSF4 2025.12.4 — DO NOT UNPLUG..."
  $DFU -d 0483:df11 -a 0 -s 0x08000000:leave -D "$HEX"
  FLASHED=1
}

echo "=============================================="
echo "  RESTORE Omnibus F4 -> Betaflight 2025.12.4"
echo "=============================================="
echo ""
echo "This is the version that worked before the 3.5.7 downgrade."
echo ""
echo "Before starting:"
echo "  • Props OFF"
echo "  • Battery plugged in (LED + beeps)"
echo "  • USB plugged in"
echo "  • Chrome QUIT (Cmd+Q)"
echo ""
echo "If Mac does not see the FC yet:"
echo "  1. Unplug USB"
echo "  2. Hold BOOT button on FC"
echo "  3. Plug USB while holding BOOT"
echo "  4. Release BOOT after 3 seconds"
echo ""

BF_RELEASE="2025.12.4"
BF_RADIO_PROTOCOLS='["CRSF"]'
download_cloud_hex
cp -f "/tmp/bf_${BF_TARGET}_${BF_RELEASE}.hex" "$HEX" 2>/dev/null || true
echo "Firmware: $HEX ($(wc -c < "$HEX") bytes) — must say OMNIBUSF4 ~809919"
echo ""
echo "Waiting up to 5 minutes for serial or DFU..."
echo ""

for i in $(seq 1 300); do
  if has_dfu; then
    echo "DFU detected!"
    flash_omnibus
    break
  fi
  PORT=$(find_fc_port)
  if [[ -n "$PORT" ]] && ! lsof "$PORT" 2>/dev/null | grep -q .; then
    echo "Serial found: $PORT — sending bl to enter DFU..."
    enter_dfu_via_cli "$PORT"
    sleep 2
    if has_dfu; then
      flash_omnibus
      break
    fi
  elif [[ -n "$PORT" ]] && (( i % 20 == 0 )); then
    echo "  Port busy — quit Chrome (Cmd+Q): $PORT"
  fi
  (( i % 30 == 0 )) && echo "  waiting... (${i}s) — try BOOT procedure or wiggle USB"
  sleep 1
done

if [[ $FLASHED -eq 0 ]]; then
  echo ""
  echo "FAILED: Mac never saw the Omnibus (no serial, no DFU)."
  echo ""
  echo "Firmware is ready at: $HEX"
  echo "When DFU appears, flash manually:"
  echo "  $DFU -d 0483:df11 -a 0 -s 0x08000000:leave -D $HEX"
  echo ""
  echo "If battery beeps but Mac never sees anything -> USB data cable/port repair."
  exit 1
fi

echo ""
echo "=============================================="
echo "  SUCCESS — 2025.12.4 restored on Omnibus F4"
echo "=============================================="
echo ""
echo "1. Unplug USB, wait 5 sec"
echo "2. Plug USB WITHOUT holding BOOT"
echo "3. Run:  ls /dev/cu.usb*"
echo "4. app.betaflight.com -> Connect"
echo ""
