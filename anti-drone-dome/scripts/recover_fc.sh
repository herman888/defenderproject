#!/bin/bash
# Flash OMNIBUSF4 — works from DFU mode OR normal USB (sends bl) OR manual BOOT.
set -euo pipefail

DFU="${DFU:-$(command -v dfu-util || echo /opt/homebrew/bin/dfu-util)}"
HEX="/tmp/bf_omni_357.hex"
URL="https://github.com/betaflight/betaflight/releases/download/3.5.7/betaflight_3.5.7_OMNIBUSF4.hex"
PY="${PY:-$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")/../.." && pwd)/gym-pybullet-drones/.venv/bin/python3}"

has_dfu() { $DFU -l 2>&1 | grep -q 'Found DFU'; }

wait_dfu() {
  local secs="${1:-30}"
  for i in $(seq 1 "$secs"); do
    if has_dfu; then
      echo "DFU ready."
      return 0
    fi
    if (( i % 5 == 0 )); then
      echo "  waiting for DFU... (${i}s)"
    fi
    sleep 1
  done
  return 1
}

enter_dfu_via_cli() {
  local port="$1"
  echo "Sending bl (bootloader) on $port..."
  "$PY" -c "
import serial, time
s = serial.Serial('$port', 115200, timeout=1)
time.sleep(0.3)
s.reset_input_buffer()
s.write(b'#\n'); time.sleep(0.8); s.read(s.in_waiting or 1)
s.write(b'bl\n'); time.sleep(0.3)
s.close()
"
}

echo "=== FC recovery flash ==="
echo ""

# --- diagnostics ---
echo "Checking USB..."
$DFU -l 2>&1 | grep -E 'Found DFU|No DFU' || true
PORT=$(ls /dev/cu.usbmodem* 2>/dev/null | head -1 || true)
if [[ -n "$PORT" ]]; then
  echo "Serial port: $PORT"
else
  echo "Serial port: (none)"
fi
echo ""

# --- get into DFU ---
if has_dfu; then
  echo "Already in DFU mode."
elif [[ -n "$PORT" ]]; then
  if lsof "$PORT" 2>/dev/null | grep -q .; then
    echo "Port busy — quit Chrome (Cmd+Q), then run this script again."
    lsof "$PORT" 2>/dev/null || true
    exit 1
  fi
  enter_dfu_via_cli "$PORT"
  if ! wait_dfu 25; then
    echo ""
    echo "CLI reboot did not enter DFU. Try manual bootloader:"
    echo "  1. Unplug USB"
    echo "  2. Hold BOOT on the FC"
    echo "  3. Plug USB while holding BOOT"
    echo "  4. Release BOOT after 2 seconds"
    echo ""
    read -r -p "Press Enter when done..."
    if ! wait_dfu 20; then
      echo "FAILED: Still no DFU. Try another USB port/cable (skip hub if possible)."
      $DFU -l 2>&1 || true
      exit 1
    fi
  fi
else
  echo "No DFU and no serial port."
  echo ""
  echo "Put the FC into bootloader mode:"
  echo "  1. Unplug USB from the FC"
  echo "  2. Hold the BOOT button on the flight controller"
  echo "  3. Plug USB into the hub/Mac while still holding BOOT"
  echo "  4. Release BOOT after 2 seconds"
  echo ""
  read -r -p "Press Enter when BOOT procedure is done..."
  if ! wait_dfu 30; then
    echo ""
    echo "FAILED: Mac still does not see DFU."
    echo "  - Try a different USB cable"
    echo "  - Plug hub directly into Mac if you can"
    echo "  - Hold BOOT longer (3–4 sec) before releasing"
    $DFU -l 2>&1 || true
    exit 1
  fi
fi

# --- flash ---
if [[ ! -f "$HEX" ]] || [[ $(wc -c < "$HEX") -lt 100000 ]]; then
  echo "Downloading firmware..."
  curl -sL "$URL" -o "$HEX"
fi

echo ""
echo "Flashing — DO NOT UNPLUG..."
$DFU -d 0483:df11 -a 0 -s 0x08000000:leave -D "$HEX"

echo ""
echo "SUCCESS! Now:"
echo "  1. Unplug USB"
echo "  2. Wait 5 sec"
echo "  3. Plug USB back in WITHOUT holding BOOT"
echo "  4. Run: ls /dev/cu.usb*"
echo "  5. Connect in app.betaflight.com -> Receiver -> SPEKTRUM2048"
