#!/bin/bash
# Full chip erase + reflash — fixes boot hang after firmware downgrade (2025.x config on 3.5.7).
# Requires ST-Link (SWD) OR DFU mode. Cannot run over broken USB serial.
#
# Usage:
#   bash erase_restore_fc.sh          # default: clean 3.5.7 OMNIBUSF4
#   bash erase_restore_fc.sh dfu      # use dfu-util (if Found DFU appears)
#   bash erase_restore_fc.sh stlink   # use ST-Link (recommended)
#
set -euo pipefail

METHOD="${1:-stlink}"
HEX="/tmp/bf_omni_357.hex"
URL="https://github.com/betaflight/betaflight/releases/download/3.5.7/betaflight_3.5.7_OMNIBUSF4.hex"
DFU="/opt/homebrew/bin/dfu-util"

download_hex() {
  if [[ ! -f "$HEX" ]] || [[ $(wc -c < "$HEX") -lt 100000 ]]; then
    echo "Downloading betaflight_3.5.7_OMNIBUSF4.hex..."
    curl -sL "$URL" -o "$HEX"
  fi
  echo "Firmware: $HEX ($(wc -c < "$HEX") bytes)"
}

flash_dfu() {
  if ! $DFU -l 2>&1 | grep -q 'Found DFU'; then
    echo "No DFU device. Hold BOOT, plug USB, release, then run:"
    echo "  bash erase_restore_fc.sh dfu"
    $DFU -l 2>&1 || true
    exit 1
  fi
  download_hex
  echo ""
  echo "Erasing + flashing via DFU (DO NOT UNPLUG)..."
  # Reflash from 0x08000000 overwrites app + config partitions
  $DFU -d 0483:df11 -a 0 -s 0x08000000:leave -D "$HEX"
}

flash_stlink() {
  if ! command -v st-flash >/dev/null 2>&1; then
    echo "Install ST-Link tools:  brew install stlink"
    exit 1
  fi
  echo "Probing ST-Link..."
  if ! st-info --probe 2>&1 | grep -qi "found"; then
    echo ""
    echo "No ST-Link / STM32 detected."
    echo "Wire GND, SWDIO, SWCLK from ST-Link to FC pads. Power FC with battery."
    st-info --probe 2>&1 || true
    exit 1
  fi
  download_hex
  echo ""
  echo "FULL CHIP ERASE (wipes firmware + old 2025.x config)..."
  st-flash erase
  echo ""
  echo "Flashing clean 3.5.7 — DO NOT UNPLUG..."
  st-flash --reset write "$HEX" 0x08000000
}

echo "=========================================="
echo "  FC erase + clean restore"
echo "=========================================="
echo ""
echo "Why: Downgrading 2025.12.4 -> 3.5.7 can leave incompatible"
echo "config in flash. That may stop boot (no blinking red LED, no USB)."
echo "Full erase + reflash gives a factory-clean 3.5.7 install."
echo ""
echo "Note: Erase alone leaves the board blank — we always reflash after."
echo ""

case "$METHOD" in
  dfu)    flash_dfu ;;
  stlink) flash_stlink ;;
  *)
    echo "Usage: bash erase_restore_fc.sh [stlink|dfu]"
    exit 1
    ;;
esac

echo ""
echo "=========================================="
echo "  DONE — clean firmware installed"
echo "=========================================="
echo ""
echo "1. Disconnect ST-Link (if used)"
echo "2. Unplug USB, wait 5 sec, replug WITHOUT holding BOOT"
echo "3. Battery on — red status LED should BLINK"
echo "4. ls /dev/cu.usb*"
echo "5. app.betaflight.com -> Receiver -> SPEKTRUM2048 -> Save"
echo ""
echo "To go back to 2025.12.4 (USB worked, no Spektrum):"
echo "  That build is only via Chrome cloud flasher once USB serial works again."
echo "  Configurator -> Firmware Flasher -> OMNIBUSF4 -> Load Online -> Flash"
