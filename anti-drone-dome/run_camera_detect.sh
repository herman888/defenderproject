#!/usr/bin/env bash
# InnoMaker USB IR camera + threat detection — paste this one line anywhere:
#   bash <repo>/defenderproject/anti-drone-dome/run_camera_detect.sh
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
  echo "[ERROR] No venv. Run: cd $ROOT/../gym-pybullet-drones && python3 -m venv .venv"
  exit 1
fi

python3 -m pip install -q opencv-python ultralytics huggingface_hub 2>/dev/null || true
export PYTHONUNBUFFERED=1
# InnoMaker USB only — wireless / FaceTime / iPhone cameras are blocked in Python.
if [[ $# -eq 0 ]]; then
  exec python3 "$ROOT/scripts/camera_detect.py"
fi
exec python3 "$ROOT/scripts/camera_detect.py" "$@"
