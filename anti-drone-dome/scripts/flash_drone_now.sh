#!/bin/bash
# Auto-flash drone when Mac sees it — Mac popup notifications included.
#
# Usage (from anti-drone-dome folder):
#   bash scripts/flash_drone_now.sh omnibus   # Omnibus F4 (default)
#   bash scripts/flash_drone_now.sh fury      # Fury F4 OSD
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/betaflight_common.sh"

BOARD="${1:-omnibus}"

notify() {
  osascript -e "display notification \"$2\" with title \"Betaflight Flash\" subtitle \"$1\" sound name \"Glass\"" 2>/dev/null || true
}

alert() {
  osascript -e "display alert \"$1\" message \"$2\" as informational" 2>/dev/null || true
}

if [[ "$BOARD" == "omnibus" ]]; then
  source "$SCRIPT_DIR/betaflight_fc_omnibus.env"
  BF_RELEASE="2025.12.4"
  BF_RADIO_PROTOCOLS='["CRSF"]'
  HEX="/tmp/bf_OMNIBUSF4_2025.12.4.hex"
  LABEL="OMNIBUSF4 2025.12.4"
  prep_hex() {
    download_cloud_hex
    cp -f "/tmp/bf_${BF_TARGET}_${BF_RELEASE}.hex" "$HEX" 2>/dev/null || true
  }
else
  source "$SCRIPT_DIR/betaflight_fc_fury.env"
  HEX="/tmp/bf_FURYF4OSD_2025.12.4_spektrum.hex"
  LABEL="FURYF4OSD 2025.12.4 + Spektrum"
  prep_hex() {
    BF_RADIO_PROTOCOLS='["SPEKTRUM"]'
    download_cloud_hex
    cp -f "/tmp/bf_${BF_TARGET}_${BF_RELEASE}.hex" "$HEX" 2>/dev/null || true
  }
fi

do_flash() {
  prep_hex
  notify "Flashing..." "$LABEL — DO NOT UNPLUG"
  echo "Flashing $LABEL ..."
  echo "  $HEX ($(wc -c < "$HEX") bytes)"
  $DFU -d 0483:df11 -a 0 -s 0x08000000:force:mass-erase 2>/dev/null || true
  sleep 2
  $DFU -d 0483:df11 -a 0 -s 0x08000000:leave -D "$HEX"
}

alert "Drone flash watcher started" "Watching for $LABEL. Props OFF. Battery on. Quit Chrome (Cmd+Q). Plug drone into hub now."
notify "Watching for drone" "Hold BOOT + plug USB if nothing happens in 30 sec"

echo "=============================================="
echo "  FLASH WATCHER — $LABEL"
echo "=============================================="
echo ""
prep_hex
echo "Firmware ready: $HEX"
echo ""
echo "Waiting up to 15 minutes..."
echo "Ctrl+C to stop."
echo ""

for i in $(seq 1 900); do
  if has_dfu; then
    notify "DFU found!" "Flashing in 2 seconds..."
    sleep 2
    do_flash
    notify "SUCCESS!" "Unplug USB 5 sec, replug. Open app.betaflight.com"
    alert "Flash complete!" "Unplug USB, wait 5 sec, replug WITHOUT BOOT. Then Connect in Chrome."
    echo ""
    echo "SUCCESS! Run: ls /dev/cu.usb*"
    exit 0
  fi
  PORT=$(find_fc_port)
  if [[ -n "$PORT" ]] && ! lsof "$PORT" 2>/dev/null | grep -q .; then
    notify "Serial found" "$PORT — rebooting to flash..."
    enter_dfu_via_cli "$PORT"
    sleep 2
    if has_dfu; then
      do_flash
      notify "SUCCESS!" "Unplug USB 5 sec, replug."
      alert "Flash complete!" "Unplug USB, wait 5 sec, replug. Connect in Chrome."
      exit 0
    fi
  fi
  if (( i == 30 )); then
    notify "No drone yet" "Hold BOOT, plug USB, release after 3 sec"
  fi
  if (( i % 60 == 0 )); then
    echo "[${i}s] waiting... serial=$(find_fc_port || echo none) dfu=$(has_dfu && echo yes || echo no)"
    notify "Still waiting (${i}s)" "Try BOOT + USB or another cable"
  fi
  sleep 1
done

alert "Timed out" "Mac never saw the drone. Try data cable, BOOT mode, or ST-Link."
notify "Failed" "No USB/DFU detected in 15 min"
exit 1
