#!/bin/bash
# Omnibus F4 — diagnose USB, restore firmware, optional Spektrum flash.
#
# Usage:
#   bash setup_omnibus_f4.sh              # check connection + instructions
#   bash setup_omnibus_f4.sh --flash      # flash 2025.12.4 (restore working USB)
#   bash setup_omnibus_f4.sh --spektrum   # flash 2025.12.4 with Spektrum (DX4e)
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/betaflight_fc_omnibus.env"
source "$SCRIPT_DIR/betaflight_common.sh"

FLASH=0
for arg in "$@"; do
  case "$arg" in
    --flash)    FLASH=1 ;;
    --spektrum) FLASH=1; BF_RADIO_PROTOCOLS='["SPEKTRUM"]' ;;
  esac
done

echo "=========================================="
echo "  ${BF_BOARD_NAME} recovery / setup"
echo "  Target: ${BF_TARGET}  Firmware: ${BF_RELEASE}"
echo "=========================================="
echo ""
echo "Props OFF. Battery on for motor test / full power."
echo ""

# --- diagnostics ---
echo "--- USB diagnostics ---"
$DFU -l 2>&1 | grep -E 'Found DFU' || echo "DFU: not detected"
PORT=$(find_fc_port)
[[ -n "$PORT" ]] && echo "Serial: $PORT" || echo "Serial: (none yet)"
echo ""

if [[ -z "$PORT" ]] && ! has_dfu; then
  echo "Mac does not see the FC yet. Try in order:"
  echo "  1. Data-capable USB cable + hub port (or direct to Mac)"
  echo "  2. Battery + USB together"
  echo "  3. Hold BOOT -> plug USB -> release after 3 sec"
  echo "  4. Wiggle USB plug at the FC — loose port = no data"
  echo ""
  echo "Waiting up to 3 minutes..."
  if ! PORT=$(wait_fc_port 180); then
    if ! has_dfu; then
      echo ""
      echo "Still no USB data path. If battery gives LED + motor beeps but"
      echo "Mac never sees a port, the micro-USB jack may need repair."
      echo ""
      echo "When USB appears, re-run:  bash $0"
      exit 1
    fi
  fi
  [[ -n "$PORT" ]] && echo "Found: $PORT"
fi

if [[ -n "$PORT" ]]; then
  wait_port_free "$PORT" || {
    echo "Quit Chrome (Cmd+Q) — port busy: $PORT"
    exit 1
  }
  echo ""
  echo "--- Flight controller ---"
  fc_cli "$PORT" "version" "status" "get serialrx_provider" || true
  echo ""
fi

if [[ $FLASH -eq 1 ]]; then
  echo "Preparing firmware (${BF_RADIO_PROTOCOLS})..."
  if ! has_dfu; then
    ensure_dfu || {
      echo ""
      echo "Need DFU mode. Hold BOOT, plug USB, release, then:"
      echo "  bash $0 --flash"
      exit 1
    }
  fi
  flash_dfu_hex
  echo ""
  echo "SUCCESS. Unplug USB, wait 5s, replug WITHOUT holding BOOT."
  echo "Red status LED should blink. Then connect app.betaflight.com"
  if [[ "$BF_RADIO_PROTOCOLS" == *SPEKTRUM* ]]; then
    echo "Receiver -> SPEKTRUM2048 -> Save"
  fi
  exit 0
fi

echo "--- Next steps ---"
echo "  Connect:  app.betaflight.com  (quit Chrome first if port busy)"
echo "  Motors:   python3 anti-drone-dome/scripts/betaflight_motor_test.py"
echo ""
echo "  Restore firmware (2025.12.4, last known working USB):"
echo "    bash $0 --flash"
echo ""
echo "  Flash with Spektrum for DX4e radio:"
echo "    bash $0 --spektrum"
echo ""
if [[ -n "$PORT" ]]; then
  echo "FC is connected on: $PORT"
fi
