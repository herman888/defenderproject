# Simulation quick start

PyBullet is the authoritative local physics process. The integrated command
center combines tactical rendering, track fusion, mission controls, telemetry,
charts, and event history.

---

## Run

```bash
cd anti-drone-dome
python main.py --auto-start --render-backend opengl
```

Or with the gym-pybullet-drones venv:

```bash
cd gym-pybullet-drones
source .venv/bin/activate
pip install pymavlink   # if needed
cd ../anti-drone-dome
python3 main.py
```

!!! tip
    Do not paste shell comments that start with `#` into zsh — it may try to run `#` as a command.

---

## What you see

| Window | Content |
|--------|---------|
| **Command center** | Mission selection, tactical 3-D, tracks, charts, events |
| **Terminal** | Runtime diagnostics and mission debrief |
| **Artifacts** | Mission JSONL, manifest, hashes, ACMI replay |

---

## Controllers (high level)

### Blue interceptor

World-frame translational PD with mass-trimmed hover, slew-limited bank, kinematic attitude so the mesh banks with thrust. Intercept phase uses APN-style pursuit thrust.

### Red intruder

Same PD structure plus type-specific drag / optional wing lift (Shahed-class). Nose aligns with velocity for committed forward flight.

Code: `sim/drone.py`, scenarios in `scenarios.py` (if present), guidance in `guidance/`.

---

## Zoom

In PyBullet **User Parameters** (after START):

- `3D + ZOOM` / `3D − ZOOM` — pulse zoom (drag to 1, back to 0)
- Same as `+` / `−` keys with the PyBullet window focused

---

## Fresh venv (optional)

```bash
cd anti-drone-dome
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python3 main.py
```
