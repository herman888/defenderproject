# Defender drone scenario

This adds a small **high-level policy** on top of the existing **PID** stack: the PID controller still tracks XYZ setpoints; the defender layer chooses *where* each drone should fly.

## What runs

- **`gym_pybullet_drones/examples/defender_pid.py`** — full PyBullet demo.
- **`gym_pybullet_drones/defender/`** — reusable pieces:
  - **`intruder.py`** — kinematic red sphere that moves toward the VIP centroid, then loiters. It does **not** collide with drones (collision pairs disabled).
  - **`policy.py`** — assigns roles using **line-of-sight geometry**:
    - **VIP** (first `num_assets` indices): hold their spawn positions.
    - **Interceptor** — defender closest to a **cut point** on *threatened VIP → intruder*
      (blended with intruder position + velocity lead), so the quad flies into the **inbound corridor**.
    - **Block** — second defender sits at **`block_chord_t`** along that chord (between VIP and threat).
    - **Escort ring** — remaining drones orbit the threatened VIP’s hold point.
    - **Threatened VIP** = smallest **horizontal (XY)** distance to the intruder (stable vs altitude noise).

## Quick start

From the `gym-pybullet-drones` folder (with your venv active):

```bash
python gym_pybullet_drones/examples/defender_pid.py --gui true --radar_hud false
```

Optional camera: ``--camera_orbit true``, ``--camera_follow true`` (centroid of drones + intruder), and **J/L/I/K/U/O** with the 3D view focused (see ``gui_camera.py``).

Recommended: keep **`--obstacles false`** (default here) so the scene stays readable.

### More drones

```bash
python gym_pybullet_drones/examples/defender_pid.py --num_drones 5 --num_assets 2
```

You need **`num_drones > num_assets`** so there is at least one defender.

### Run length

Same idea as `pid.py`: **`--duration_sec 0`** with GUI is effectively unlimited; headless uses a short cap.

## How “defending” works (mental model)

1. **Sensing** (this demo): perfect world knowledge — the policy reads `env.pos` and the intruder state. You can later restrict this to range-limited or noisy measurements.
2. **Planning**: `DefenderPolicy.compute_targets(...)` returns one **target position** per drone per step.
3. **Control**: `DSLPIDControl.computeControlFromState` turns each target into motor **RPMs**.

## Ideas to extend

- Replace straight pursuit with **pure pursuit** or **proportional navigation** on velocity.
- Add a **second intruder** and greedy defender–threat assignment.
- Add **success metrics** (minimum VIP–intruder distance over time) and log them to CSV.
