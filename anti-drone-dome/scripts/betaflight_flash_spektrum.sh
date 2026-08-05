#!/bin/bash
# Flash OMNIBUSF4 (STM32F405) with Betaflight 4.5.1 — includes Spektrum support.
set -euo pipefail

HEX="/tmp/bf_spektrum_405.hex"
URL="https://github.com/betaflight/betaflight/releases/download/4.5.1/betaflight_4.5.1_STM32F405.hex"
PY="${PY:-$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")/../.." && pwd)/gym-pybullet-drones/.venv/bin/python3}"
DFU="${DFU:-$(command -v dfu-util || echo /opt/homebrew/bin/dfu-util)}"

find_port() {
  ls /dev/cu.usbmodem* 2>/dev/null | head -1 || true
}

enter_dfu() {
  local port="$1"
  "$PY" - <<PY
import serial, time
ser = serial.Serial("$port", 115200, timeout=1)
time.sleep(0.3)
ser.reset_input_buffer()
ser.write(b"#\n")
time.sleep(0.8)
ser.read(ser.in_waiting or 1)
ser.write(b"bl\n")
time.sleep(0.5)
ser.close()
print("Sent bl (bootloader reboot)")
PY
}

wait_dfu() {
  echo "Waiting for STM32 DFU (up to 25 seconds)..."
  for i in $(seq 1 25); do
    if "$DFU" -l 2>/dev/null | grep -q "0483:df11"; then
      echo "DFU found after ${i}s."
      return 0
    fi
    sleep 1
  done
  return 1
}

echo "=== Spektrum firmware flash (4.5.1 STM32F405) ==="
echo ""
echo "Before continuing:"
echo "  1. Close Betaflight in Chrome (Disconnect)"
echo "  2. Plug USB from drone into Mac"
echo "  3. Do NOT hold BOOT yet"
echo ""
read -r -p "Press Enter when USB is plugged in..."

PORT=$(find_port)
if [[ -z "$PORT" ]]; then
  echo ""
  echo "ERROR: No USB port found. Plug the drone in and try again."
  exit 1
fi
echo "Found port: $PORT"

if [[ ! -f "$HEX" ]] || [[ $(wc -c < "$HEX") -lt 100000 ]]; then
  echo "Downloading firmware..."
  curl -sL "$URL" -o "$HEX"
fi
echo "Firmware: $(wc -c < "$HEX") bytes"

enter_dfu "$PORT"

if ! wait_dfu; then
  echo ""
  echo "DFU not detected. Try manual bootloader mode:"
  echo "  1. Unplug USB"
  echo "  2. Hold BOOT button on the FC"
  echo "  3. Plug USB in while holding BOOT"
  echo "  4. Release BOOT after 2 seconds"
  echo ""
  read -r -p "Press Enter after doing that..."
  if ! wait_dfu; then
    echo "ERROR: Still no DFU device. Try a different USB cable/port."
    "$DFU" -l 2>&1 || true
    exit 1
  fi
fi

echo ""
echo "Flashing — do NOT unplug USB..."
"$DFU" -d 0483:df11 -a 0 -s 0x08000000:leave -D "$HEX"

echo ""
echo "SUCCESS. Unplug USB, wait 3 sec, plug back in."
echo "Open app.betaflight.com -> Connect -> Receiver -> SPEKTRUM2048"
