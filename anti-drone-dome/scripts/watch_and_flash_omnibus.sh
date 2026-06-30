#!/bin/bash
# Watch for Omnibus F4 on USB and auto-flash when it appears.
# Cannot force connection — only works when Mac actually sees serial or DFU.
#
# Usage:  bash scripts/watch_and_flash_omnibus.sh
#         bash scripts/watch_and_flash_omnibus.sh 357   # flash 3.5.7 instead
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/betaflight_fc_omnibus.env"
source "$SCRIPT_DIR/betaflight_common.sh"

MODE="${1:-2025}"

if [[ "$MODE" == "357" || "$MODE" == "3.5.7" ]]; then
  HEX="/tmp/bf_omnibus_357.hex"
  URL="https://github.com/betaflight/betaflight/releases/download/3.5.7/betaflight_3.5.7_OMNIBUSF4.hex"
  LABEL="3.5.7 OMNIBUSF4 (includes Spektrum)"
  download_hex() {
    [[ -f "$HEX" ]] && [[ $(wc -c < "$HEX") -gt 500000 ]] && return
    echo "Downloading $LABEL..."
    curl -sL "$URL" -o "$HEX"
  }
else
  BF_RELEASE="2025.12.4"
  BF_RADIO_PROTOCOLS='["CRSF"]'
  HEX="/tmp/bf_OMNIBUSF4_2025.12.4.hex"
  LABEL="2025.12.4 OMNIBUSF4 (last working USB)"
  download_hex() { download_cloud_hex; cp -f "/tmp/bf_${BF_TARGET}_${BF_RELEASE}.hex" "$HEX" 2>/dev/null || true; }
fi

show_usb() {
  echo "--- What's on USB right now ---"
  system_profiler SPUSBDataType 2>/dev/null | grep -B1 -A5 -iE "betaflight|stm|bootloader|0483|serial|cp210|ch340" \
    || echo "  (no flight controller in USB list)"
  echo "  Serial ports: $(ls /dev/cu.usb* 2>/dev/null | tr '\n' ' ' || echo none)"
  $DFU -l 2>&1 | grep -i "found dfu" || echo "  DFU: none"
  echo ""
}

do_flash() {
  download_hex
  echo "Flashing $LABEL ..."
  echo "  File: $HEX ($(wc -c < "$HEX") bytes)"
  $DFU -d 0483:df11 -a 0 -s 0x08000000:force:mass-erase 2>/dev/null || true
  sleep 2
  $DFU -d 0483:df11 -a 0 -s 0x08000000:leave -D "$HEX"
}

echo "=============================================="
echo "  Watch for Omnibus F4 -> auto flash"
echo "  Target firmware: $LABEL"
echo "=============================================="
echo ""
echo "Plug in ONLY the drone USB (props off, battery on)."
echo "Quit Chrome (Cmd+Q). Press Ctrl+C to stop."
echo ""
show_usb

for i in $(seq 1 600); do
  if has_dfu; then
    echo ">>> DFU DETECTED — flashing in 2 sec..."
    sleep 2
    do_flash
    echo ""
    echo "DONE. Unplug USB, wait 5s, replug. Run: ls /dev/cu.usb*"
    exit 0
  fi
  PORT=$(find_fc_port)
  if [[ -n "$PORT" ]] && ! lsof "$PORT" 2>/dev/null | grep -q .; then
    echo ">>> SERIAL DETECTED: $PORT — entering DFU..."
    enter_dfu_via_cli "$PORT"
    sleep 2
    if has_dfu; then
      do_flash
      echo ""
      echo "DONE. Unplug USB, wait 5s, replug. Run: ls /dev/cu.usb*"
      exit 0
    fi
  fi
  if (( i % 30 == 0 )); then
    echo "[${i}s] still waiting... (try BOOT: hold BOOT, plug USB, release)"
    show_usb
  fi
  sleep 1
done

echo "Timed out after 10 min. Mac never saw the drone."
show_usb
exit 1
