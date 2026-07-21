# defenderproject — PyBullet quadcopter gym

This repository vendors **[learnsyslab/gym-pybullet-drones](https://github.com/learnsyslab/gym-pybullet-drones)** under `gym-pybullet-drones/` for reinforcement learning and PID demos in PyBullet.

The integrated Project LARP counter-UAS simulator, command center, validation
workbench, hardware profiles, and documentation website live under
`anti-drone-dome/`. Start with
[`anti-drone-dome/documentation/index.md`](anti-drone-dome/documentation/index.md)
or the published site at
[defenderproject.vercel.app](https://defenderproject.vercel.app).

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
    