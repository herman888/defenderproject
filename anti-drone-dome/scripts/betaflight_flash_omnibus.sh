#!/bin/bash
# Flash OMNIBUSF4 via DFU on Mac. USB plugged in, battery optional.
set -euo pipefail

PORT="/dev/cu.usbmodem0x80000001"
HEX="/tmp/bf_flash.hex"
PY="${PY:-$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")/../.." && pwd)/gym-pybullet-drones/.venv/bin/python3}"
DFU="${DFU:-$(command -v dfu-util || echo /opt/homebrew/bin/dfu-util)}"

if [[ ! -f "$HEX" ]]; then
  echo "Downloading firmware (OMNIBUSF4 2025.12.4)..."
  ID=$(curl -sL -X POST "https://build.betaflight.com/api/builds" \
    -H "Content-Type: application/json" \
    -d '{"release":"2025.12.4","target":"OMNIBUSF4","motorProtocols":["DSHOT"],"radioProtocols":["CRSF"],"options":["CORE_ONLY"]}' \
    | python3 -c "import sys,json; print(json.load(sys.stdin)['key'])")
  for _ in $(seq 1 30); do
    st=$(curl -sL "https://build.betaflight.com/api/builds/$ID/status" | python3 -c "import sys,json; print(json.load(sys.stdin).get('status',''))")
    [[ "$st" == "success" || "$st" == "cached" ]] && break
    sleep 2
  done
  curl -sL "https://build.betaflight.com/api/builds/$ID/hex" -o "$HEX"
fi

echo "Rebooting FC into DFU mode..."
"$PY" - <<'PY'
import serial, time
port = "/dev/cu.usbmodem0x80000001"
ser = serial.Serial(port, 115200, timeout=1)
time.sleep(0.3)
ser.reset_input_buffer()
ser.write(b"#\n")
time.sleep(0.8)
ser.read(ser.in_waiting or 1)
ser.write(b"bl\n")
time.sleep(0.3)
ser.close()
print("Sent bl (bootloader)")
PY

echo "Waiting for STM32 DFU..."
for _ in $(seq 1 15); do
  if "$DFU" -l 2>/dev/null | grep -q "0483:df11"; then
    echo "DFU device found."
    break
  fi
  sleep 1
done

echo "Flashing (do not unplug USB)..."
"$DFU" -d 0483:df11 -a 0 -s 0x08000000:leave -D "$HEX"

echo ""
echo "Flash complete. Unplug USB, wait 3 sec, plug back in."
echo "Open app.betaflight.com in Chrome -> Connect -> Motors tab."
