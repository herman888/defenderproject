#!/bin/bash
# Shared helpers for Betaflight FC scripts on Mac.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/betaflight_fc.env"

has_dfu() { $DFU -l 2>&1 | grep -q 'Found DFU'; }

find_fc_port() {
  ls /dev/cu.usbmodem* 2>/dev/null | head -1 || true
}

wait_fc_port() {
  local secs="${1:-180}"
  local port=""
  for i in $(seq 1 "$secs"); do
    port=$(find_fc_port)
    if [[ -n "$port" ]]; then
      echo "$port"
      return 0
    fi
    if has_dfu; then
      echo ""
      return 0
    fi
    (( i % 10 == 0 )) && echo "  waiting for USB... (${i}s)" >&2
    sleep 1
  done
  return 1
}

wait_port_free() {
  local port="$1"
  local secs="${2:-60}"
  for i in $(seq 1 "$secs"); do
    if ! lsof "$port" 2>/dev/null | grep -q .; then
      return 0
    fi
    if (( i == 1 )); then
      echo "Port busy — quit Chrome (Cmd+Q):" >&2
      lsof "$port" 2>/dev/null >&2 || true
    fi
    sleep 1
  done
  return 1
}

enter_dfu_via_cli() {
  local port="$1"
  echo "Rebooting to bootloader (bl) on $port..."
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

wait_dfu() {
  local secs="${1:-30}"
  for i in $(seq 1 "$secs"); do
    if has_dfu; then
      echo "DFU ready."
      return 0
    fi
    sleep 1
  done
  return 1
}

download_cloud_hex() {
  if [[ -f "$HEX" ]] && [[ $(wc -c < "$HEX") -gt 500000 ]]; then
    echo "Firmware cached: $HEX ($(wc -c < "$HEX") bytes)"
    return
  fi
  echo "Building ${BF_RELEASE} ${BF_TARGET} online..."
  local json
  json=$(printf '{"release":"%s","target":"%s","motorProtocols":%s,"radioProtocols":%s,"options":%s}' \
    "$BF_RELEASE" "$BF_TARGET" "$BF_MOTOR_PROTOCOLS" "$BF_RADIO_PROTOCOLS" "$BF_BUILD_OPTIONS")
  local id
  id=$(curl -sL -X POST "https://build.betaflight.com/api/builds" \
    -H "Content-Type: application/json" -d "$json" \
    | python3 -c "import sys,json; print(json.load(sys.stdin)['key'])")
  for _ in $(seq 1 45); do
    local st
    st=$(curl -sL "https://build.betaflight.com/api/builds/$id/status" \
      | python3 -c "import sys,json; print(json.load(sys.stdin).get('status',''))")
    [[ "$st" == "success" || "$st" == "cached" ]] && break
    sleep 2
  done
  curl -sL "https://build.betaflight.com/api/builds/$id/hex" -o "$HEX"
  if [[ $(wc -c < "$HEX") -lt 500000 ]]; then
    echo "FAILED: firmware download too small" >&2
    exit 1
  fi
  echo "Downloaded: $(wc -c < "$HEX") bytes -> $HEX"
}

flash_dfu_hex() {
  download_cloud_hex
  echo "Flashing ${BF_BOARD_NAME} — DO NOT UNPLUG..."
  $DFU -d 0483:df11 -a 0 -s 0x08000000:leave -D "$HEX"
}

ensure_dfu() {
  if has_dfu; then
    return 0
  fi
  local port
  port=$(find_fc_port)
  if [[ -z "$port" ]]; then
    echo "No FC port. Plug USB (battery on, props off)."
    return 1
  fi
  wait_port_free "$port" || {
    echo "Close Betaflight / quit Chrome (Cmd+Q) and retry."
    return 1
  }
  enter_dfu_via_cli "$port"
  wait_dfu 30
}

fc_cli() {
  local port="$1"
  shift
  "$PY" - "$port" "$@" <<'PY'
import serial, time, sys
port, *cmds = sys.argv[1:]
s = serial.Serial(port, 115200, timeout=1)
time.sleep(0.3)
s.reset_input_buffer()
s.write(b"#\n")
time.sleep(0.8)
chunk = s.read(s.in_waiting or 4096).decode("utf-8", errors="replace")
if chunk:
    print(chunk, end="")
for line in cmds:
    s.write((line + "\n").encode())
    time.sleep(0.35)
    chunk = s.read(s.in_waiting or 4096).decode("utf-8", errors="replace")
    if chunk:
        print(chunk, end="")
s.write(b"exit\n")
time.sleep(0.2)
s.close()
PY
}
