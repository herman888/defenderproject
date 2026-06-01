# Defender drone scenario

This adds a small **high-level policy** on top of the existing **PID** stack: the PID controller still tracks XYZ setpoints; the defender layer chooses *where* each drone should fly.

## What runs

- **`gym_pybullet_drones/examples/defender_pid.py`** — full PyBullet demo.
- **Central building** — `assets/defender_command_building.urdf` (concrete + glass + roof) in the courtyard (`scenario_props.load_command_building`); collisions vs drones are filtered for stability.
- **Default layout** — **2 VIPs + 1 defender**, all spawned on the **left** so the center/right stays open (building + attack lanes).
- **Red team controls** (`attack_ui.py`) — **PyBullet Params** sliders (same window as the sim):

  - **Red ATTACK type** — `0` = Rocket, `1` = Drone swarm, `2` = Dive bomber  
  - **Red FIRE** — drag to **1** to launch, then back toward **0** to arm the next shot  

  Until you launch, blue team **patrols** only (`policy.py` with `threat_active=False`).
- **`threat_fleet.py`** — kinematic red bodies (no collision vs blue drones).
- **`intruder.py`** — legacy single intruder (still importable); the demo uses **`ThreatFleet`** instead.
- **`policy.py`** — intercept / block / escort when `threat_active=True`; otherwise defenders orbit on **patrol**.

## Quick start

From the `gym-pybullet-drones` folder (with your venv active):

```bash
python3 gym_pybullet_drones/examples/defender_pid.py --gui true --radar_hud false
```

In PyBullet, use the **Params** / sliders panel: **Red ATTACK type** (0/1/2) and **Red FIRE**
(slide to 1, then back to 0 to launch / re-arm).

Optional camera: ``--camera_orbit true``, ``--camera_follow true``, and **J/L/I/K/U/O** with the 3D view focused (see ``gui_camera.py``).

Skip the Params attack UI (auto rocket at start, e.g. scripting):

```bash
python3 gym_pybullet_drones/examples/defender_pid.py --gui true --attack_ui false
```

Recommended: keep **`--obstacles false`** (default here) so the scene stays readable.

### More drones

```bash
python3 gym_pybullet_drones/examples/defender_pid.py --num_drones 5 --num_assets 2
```

You need **`num_drones > num_assets`** so there is at least one defender.

### Run length

Same idea as `pid.py`: **`--duration_sec 0`** with GUI is effectively unlimited; headless uses a short cap.

## How “defending” works (mental model)

1. **Sensing** (this demo): perfect world knowledge — the policy reads `env.pos` and aggregate threat motion. You can later restrict this to range-limited or noisy measurements.
2. **Planning**: `DefenderPolicy.compute_targets(..., threat_active=...)` returns one **target position** per drone per step.
3. **Control**: `DSLPIDControl.computeControlFromState` turns each target into motor **RPMs**.

## Ideas to extend

- Replace straight pursuit with **pure pursuit** or **proportional navigation** on velocity.
- Add a **second wave** after the first threat is destroyed (distance / timeout).
- Add **success metrics** (minimum VIP–threat distance over time) and log them to CSV.
