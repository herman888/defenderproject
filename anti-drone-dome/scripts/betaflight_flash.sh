#!/bin/bash
# Flash configured FC via DFU (Fury F4 OSD by default).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/betaflight_common.sh"

echo "=== Flash ${BF_BOARD_NAME} (${BF_RELEASE}) ==="
echo ""

if has_dfu; then
  echo "DFU mode active."
elif PORT=$(find_fc_port); [[ -n "$PORT" ]]; then
  wait_port_free "$PORT" || exit 1
  enter_dfu_via_cli "$PORT"
  wait_dfu 30 || {
    echo "Hold BOOT, plug USB, release, then re-run."
    exit 1
  }
else
  echo "No FC. Hold BOOT, plug USB, release."
  read -r -p "Press Enter when ready..."
  wait_dfu 30 || exit 1
fi

flash_dfu_hex
echo ""
echo "Done. Unplug USB, wait 5s, replug. Run: bash setup_fury_f4.sh"
