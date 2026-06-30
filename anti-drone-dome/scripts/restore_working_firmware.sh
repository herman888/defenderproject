#!/bin/bash
# Restore Omnibus F4 to Betaflight 2025.12.4 — the last version USB worked.
#
# Run with FC plugged in (battery + USB, props off). Quit Chrome first (Cmd+Q).
#
#   bash restore_working_firmware.sh
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/betaflight_fc_omnibus.env"
source "$SCRIPT_DIR/betaflight_common.sh"

HEX="/tmp/bf_OMNIBUSF4_2025.12.4.hex"
FLASHED=0

do_flash() {
  echo "Flashing 2025.12.4 — DO NOT UNPLUG..."
  $DFU -d 0483:df11 -a 0 -s 0x08000000:leave -D "$HEX"
  FLASHED=1
}

echo "=============================================="
echo "  RESTORE working firmware (2025.12.4)"
echo "  Board: ${BF_BOARD_NAME} (${BF_TARGET})"
echo "=============================================="
echo ""
echo "This replaces the broken 3.5.7 downgrade + old config."
echo "After flash you should get SERIAL back (normal mode)."
echo ""
echo "Before continuing:"
echo "  • Props OFF"
echo "  • Battery plugged in"
echo "  • USB plugged in"
echo "  • Chrome QUIT (Cmd+Q)"
echo ""
read -r -p "Press Enter when ready..."

BF_RELEASE="2025.12.4"
BF_RADIO_PROTOCOLS='["CRSF"]'
download_cloud_hex
if [[ "$HEX" != "/tmp/bf_${BF_TARGET}_${BF_RELEASE}.hex" ]]; then
  cp -f "/tmp/bf_${BF_TARGET}_${BF_RELEASE}.hex" "$HEX"
fi

echo ""
echo "Firmware ready: $HEX ($(wc -c < "$HEX") bytes)"
echo ""
echo "Looking for serial or DFU (up to 5 min)..."
echo "Tip: wiggle USB plug, or hold BOOT -> plug USB -> release"
echo ""

for i in $(seq 1 300); do
  if has_dfu; then
    echo "DFU detected — flashing..."
    do_flash
    break
  fi
  PORT=$(find_fc_port)
  if [[ -n "$PORT" ]] && ! lsof "$PORT" 2>/dev/null | grep -q .; then
    echo "Serial port: $PORT — rebooting to flash..."
    enter_dfu_via_cli "$PORT"
    sleep 2
    if has_dfu; then
      do_flash
      break
    fi
  elif [[ -n "$PORT" ]] && (( i % 20 == 0 )); then
    echo "  Port busy — quit Chrome (Cmd+Q): $PORT"
  fi
  (( i % 30 == 0 )) && echo "  waiting... (${i}s)"
  sleep 1
done

if [[ $FLASHED -eq 0 ]]; then
  echo ""
  echo "FAILED: Mac never saw the FC (no serial, no DFU)."
  echo "Firmware saved at: $HEX"
  echo "Try another data cable, battery+USB, or USB port repair."
  exit 1
fi

echo ""
echo "=============================================="
echo "  DONE — 2025.12.4 restored"
echo "=============================================="
echo ""
echo "1. Unplug USB, wait 5 sec"
echo "2. Plug USB (NO BOOT button)"
echo "3. Run:  ls /dev/cu.usb*"
echo "4. app.betaflight.com -> Connect"
echo ""
