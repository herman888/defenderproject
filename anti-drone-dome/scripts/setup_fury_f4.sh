#!/bin/bash
# Fury F4 OSD — check USB, show FC info, optional Spektrum firmware flash.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/betaflight_fc_fury.env"
source "$SCRIPT_DIR/betaflight_common.sh"

FLASH=0
[[ "${1:-}" == "--flash" ]] && FLASH=1

echo "=========================================="
echo "  ${BF_BOARD_NAME} setup"
echo "  Target: ${BF_TARGET}  Firmware: ${BF_RELEASE}"
echo "=========================================="
echo ""

PORT=""
if has_dfu; then
  echo "DFU mode detected."
elif PORT=$(wait_fc_port 120); then
  [[ -n "$PORT" ]] && echo "USB port: $PORT"
else
  echo "No FC found. Plug USB (props off, battery recommended)."
  exit 1
fi

if [[ -n "$PORT" ]]; then
  wait_port_free "$PORT" || {
    echo "Quit Chrome (Cmd+Q) — port is busy."
    exit 1
  }
  echo ""
  echo "--- Flight controller ---"
  fc_cli "$PORT" "version" "status" "get serialrx_provider" "serial" || true
  echo ""
  echo "--- Spektrum (DX4e) in Configurator ---"
  echo "  1. app.betaflight.com -> Connect"
  echo "  2. Receiver -> Serial Receiver Provider -> SPEKTRUM2048 -> Save"
  echo "  3. Ports -> enable Serial RX on the UART wired to the Spektrum sat"
  echo "  4. Bind receiver to DX4e (bind plug / bind button on radio)"
  echo ""
  echo "Motor test:  python3 anti-drone-dome/scripts/betaflight_motor_test.py"
fi

if [[ $FLASH -eq 1 ]]; then
  echo ""
  echo "Flashing ${BF_RELEASE} with Spektrum support..."
  if ! has_dfu; then
    ensure_dfu || {
      echo "Enter DFU: hold BOOT, plug USB, release, re-run with --flash"
      exit 1
    }
  fi
  flash_dfu_hex
  echo ""
  echo "Done. Unplug USB, wait 5s, replug. Then set SPEKTRUM2048 in Configurator."
elif [[ -n "$PORT" ]]; then
  echo "To flash Spektrum firmware:  bash $0 --flash"
fi
