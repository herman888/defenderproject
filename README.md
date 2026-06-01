# defenderproject — PyBullet quadcopter gym

This repository vendors **[learnsyslab/gym-pybullet-drones](https://github.com/learnsyslab/gym-pybullet-drones)** under `gym-pybullet-drones/` for reinforcement learning and PID demos in PyBullet.

## Quick start

```bash
cd gym-pybullet-drones
python3.12 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip setuptools wheel poetry-core
pip install -e .
cd gym_pybullet_drones/examples
python3 pid.py
```

See `gym-pybullet-drones/README.md` for full documentation, Betaflight SITL notes, and citations.
    