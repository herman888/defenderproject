# Software overview

The software stack has six integrated capability areas:

| Piece | Location | Purpose |
|-------|----------|---------|
| **Simulation** | `main.py`, `sim/`, `viz/` | PyBullet intercept demo + dashboard |
| **Sensing** | `sensors/` | Radar, rendered EO, and track fusion |
| **Guidance** | `guidance/`, `ml/` | APN baseline and bounded residual PPO |
| **Validation** | `validation/`, `scripts/run_*validation.py` | Repeatable gates and evidence |
| **Detection** | `scripts/camera_*.py`, `scripts/finetune.py` | InnoMaker camera + YOLO drone detector |
| **Firmware tooling** | `scripts/betaflight_*.sh` | DFU flash / recovery for physical FCs |

---

## Simulation

Multiple intruder types and routes run in a shared PyBullet world with a
PyQtGraph command center and OpenGL tactical preview.

- Setup: [Simulation](simulation.md)
- Run: `bash run_mac.sh` from `anti-drone-dome/`

---

## Detection pipeline

Capture footage → extract frames → auto-label → Roboflow correct → merge → fine-tune YOLO.

Full walkthrough: [Detection Pipeline](detection-pipeline.md)

Quick live detect:

```bash
bash run_camera_detect.sh
```

---

## Repo layout (software-facing)

```
anti-drone-dome/
├── main.py / run_mac.sh     # sim entry
├── sim/                     # drone physics, waypoints
├── viz/                     # dashboard, trails, renderer
├── sensors/                 # radar helpers
├── guidance/                # intercept / APN
├── dome/                    # killzone
├── scripts/                 # camera, YOLO, Betaflight
├── models/                  # YOLO weights (gitignored)
└── documentation/           # complete MkDocs website source
```

---

## Python environment

Prefer the shared gym-pybullet-drones venv:

```bash
cd gym-pybullet-drones
source .venv/bin/activate
cd ../anti-drone-dome
python3 main.py
```

Or: `bash run_mac.sh` (activates that venv if present).
