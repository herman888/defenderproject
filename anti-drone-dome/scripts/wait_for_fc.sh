#!/bin/bash
# Wait for FC USB, verify CLI, print Chrome connect steps.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/betaflight_fc.env"

echo "=========================================="
echo "  Waiting for ${BF_BOARD_NAME} USB"
echo "=========================================="
echo "Plug USB now (props off, battery on)..."
echo ""

PORT=""
for i in $(seq 1 180); do
  PORT=$(ls /dev/cu.usbmodem* 2>/dev/null | head -1 || true)
  if [[ -n "$PORT" ]]; then
    echo "FOUND: $PORT"
    break
  fi
  if (( i % 10 == 0 )); then
    echo "  ... ${i}s (still waiting)"
  fi
  sleep 1
done

if [[ -z "$PORT" ]]; then
  echo ""
  echo "No device. Try another cable/port or hold BOOT while plugging USB."
  exit 1
fi

echo ""
echo "Testing flight controller..."
"$PY" - "$PORT" <<'PY'
import serial, time, sys
port = sys.argv[1]
s = serial.Serial(port, 115200, timeout=2)
time.sleep(0.4)
s.write(b"#\n")
time.sleep(0.8)
out = s.read(500).decode("utf-8", errors="replace")
s.close()
print(out[:400] if out else "no CLI response")
PY

echo ""
echo "=========================================="
echo "  FC READY — connect in Chrome"
echo "=========================================="
echo ""
echo "1. Open app.betaflight.com"
echo "2. Turn OFF Auto-Connect"
echo "3. Connect -> pick Betaflight device"
echo "4. Receiver -> SPEKTRUM2048 -> Save  (DX4e radio)"
echo "5. Motors tab -> props off -> test sliders"
echo ""
echo "Port: $PORT"
echo "Omnibus setup: bash anti-drone-dome/scripts/setup_omnibus_f4.sh"
