#!/usr/bin/env bash
# Live USB camera preview (uses gym-pybullet-drones venv or local .venv).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
GYM_VENV="$ROOT/../gym-pybullet-drones/.venv/bin/activate"
LOCAL="$ROOT/.venv/bin/activate"

if [[ -f "$GYM_VENV" ]]; then
  # shellcheck source=/dev/null
  source "$GYM_VENV"
elif [[ -f "$LOCAL" ]]; then
  # shellcheck source=/dev/null
  source "$LOCAL"
else
  echo "[ERROR] No venv found. Run once:"
  echo "  cd $ROOT/../gym-pybullet-drones && python3 -m venv .venv && source .venv/bin/activate"
  echo "  pip install opencv-python"
  exit 1
fi

python3 -m pip install -q opencv-python 2>/dev/null || true
exec python3 "$ROOT/scripts/camera_preview.py" "$@"
