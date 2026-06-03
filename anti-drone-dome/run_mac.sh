#!/usr/bin/env bash
# Run anti-drone-dome with a venv that has PyBullet (avoids ModuleNotFoundError).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

GYM_VENV="$ROOT/../gym-pybullet-drones/.venv/bin/activate"
LOCAL="$ROOT/.venv/bin/activate"

if [[ -f "$GYM_VENV" ]]; then
  # shellcheck source=/dev/null
  source "$GYM_VENV"
  echo "[INFO] Using ../gym-pybullet-drones/.venv"
elif [[ -f "$LOCAL" ]]; then
  # shellcheck source=/dev/null
  source "$LOCAL"
  echo "[INFO] Using anti-drone-dome/.venv"
else
  echo "[ERROR] No virtualenv found."
  echo ""
  echo "Option A — reuse the gym-pybullet-drones venv (recommended if you already use it):"
  echo "  cd $ROOT/../gym-pybullet-drones && python3 -m venv .venv && source .venv/bin/activate"
  echo "  pip install -e . && pip install pymavlink"
  echo "  cd $ROOT && bash run_mac.sh"
  echo ""
  echo "Option B — venv only in this folder:"
  echo "  cd $ROOT && python3 -m venv .venv && source .venv/bin/activate"
  echo "  pip install -r requirements.txt"
  echo "  python3 main.py"
  exit 1
fi

exec python3 main.py "$@"
