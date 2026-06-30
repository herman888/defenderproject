#!/bin/bash
# Fury F4 OSD — flash Spektrum firmware (if DFU) + connect instructions for DX4e.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/betaflight_fc_fury.env"
source "$SCRIPT_DIR/betaflight_common.sh"

HEX="/tmp/bf_FURYF4OSD_2025.12.4_spektrum.hex"

echo "=========================================="
echo "  Fury F4 OSD — Radio (Spektrum) setup"
echo "=========================================="
echo ""

# --- DFU? flash first so serial comes back ---
if has_dfu; then
  echo "FC is in BOOTLOADER mode (not normal serial yet)."
  if [[ ! -f "$HEX" ]] || [[ $(wc -c < "$HEX") -lt 500000 ]]; then
    BF_RADIO_PROTOCOLS='["SPEKTRUM"]'
    download_cloud_hex
    cp -f "/tmp/bf_${BF_TARGET}_${BF_RELEASE}.hex" "$HEX" 2>/dev/null || true
  fi
  echo "Flashing 2025.12.4 + Spektrum..."
  $DFU -d 0483:df11 -a 0 -s 0x08000000:leave -D "$HEX"
  echo ""
  echo "Flashed. Unplug USB, wait 5 sec, replug WITHOUT holding BOOT."
  echo "Waiting 15 sec for serial port..."
  sleep 15
fi

PORT=$(find_fc_port)
if [[ -z "$PORT" ]]; then
  echo ""
  echo "No serial port yet."
  echo "  • Unplug USB, wait 5 sec, replug (do NOT hold BOOT)"
  echo "  • macOS: click Allow if asked about STM / Betaflight"
  echo "  • Re-run:  bash scripts/setup_fury_radio.sh"
  exit 1
fi

echo "FC connected: $PORT"
echo ""

if lsof "$PORT" 2>/dev/null | grep -q .; then
  echo "Port busy — quit Chrome (Cmd+Q) first."
  lsof "$PORT" 2>/dev/null || true
  exit 1
fi

echo "--- Current FC settings ---"
fc_cli "$PORT" "version" "get serialrx_provider" "serial" || true

cat <<'GUIDE'

==========================================
  Connect in Chrome (step by step)
==========================================

1. Open:  https://app.betaflight.com

2. Turn OFF "Auto-Connect" (top right)

3. Click green "Connect"
   • If list is empty → "I can't find my USB device"
   • Pick: Betaflight STM Electronics (or similar)
   • Click Allow on Mac popup

4. Left sidebar → RECEIVER tab
   • Serial Receiver Provider → SPEKTRUM2048
   • Click "Save and Reboot" at bottom

5. Left sidebar → PORTS tab
   • Find the UART your Spektrum satellite is wired to
   • Enable "Serial RX" on that row (checkmark)
   • Click "Save and Reboot"

   Fury F4 OSD common wiring:
   • Spektrum sat signal → UART pad (often UART3 or SBUS/RX pad)
   • Sat power → 3.3V, GND

6. Bind DX4e to receiver:
   • Insert bind plug on receiver OR use bind mode in radio menu
   • Power FC (USB is OK without battery)
   • Hold bind on DX4e until receiver LED solid

7. Back to RECEIVER tab — move sticks on DX4e
   • Bars should move when you move sticks

Battery not required for USB config or bind.
Battery IS required later for motor test.

GUIDE
