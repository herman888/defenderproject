# Anti-drone dome simulation

## Fix: `ModuleNotFoundError: No module named 'pybullet'`

That means the **`python3` you ran is not the one inside your venv** (system Python has no PyBullet).

**Do not** paste lines that start with `#` into the terminal — zsh may try to run `#` as a command (`command not found: #`).

### Recommended (reuse `gym-pybullet-drones` venv)

```bash
cd /Users/hermanisayenka/IdeaProjects/IsayenkaEECS1021/defenderproject/gym-pybullet-drones
source .venv/bin/activate
pip install pymavlink
cd ../anti-drone-dome
python3 main.py
```

Or one step from `anti-drone-dome`:

```bash
cd /Users/hermanisayenka/IdeaProjects/IsayenkaEECS1021/defenderproject/anti-drone-dome
bash run_mac.sh
```

`run_mac.sh` activates `../gym-pybullet-drones/.venv` if it exists, otherwise `./.venv`.

### Or: venv only in this folder

```bash
cd /Users/hermanisayenka/IdeaProjects/IsayenkaEECS1021/defenderproject/anti-drone-dome
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python3 main.py
```

`run_sim.py` is the same as `main.py` — it still needs the same activated venv.

---

## Where the “mission select” text is

| Where | What you see |
|-------|----------------|
| **Terminal** | ASCII **MISSION SELECT** / speed / debrief (`print` from `main.py`). |
| **PyBullet** | 3-D scene, **User Parameters** zoom sliders (+/− strokes), keyboard `H` help. |
| **Matplotlib** | Dashboard title **ANTI-DRONE DEFENSE SYSTEM \| ACTIVE** (`viz/dashboard.py`). |

If the matplotlib window looks different from someone else’s machine, it’s usually **fonts / DPI / Tk on macOS vs Windows**.

---

## Flight controller — how it works

This sim is built for **clarity and spectacle**: two different “brains” share one PyBullet world. The README describes intent; the code lives in `sim/drone.py`.

### Blue interceptor (high-speed C-UAS airframe)

The interceptor is a **world-frame translational controller** represented by a
purpose-built high-speed C-UAS airframe:

1. **Position–velocity PD**  
   Desired force is `F = Kp · (r_target − r) − Kd · v` in X, Y, Z.  
   Using **measured velocity** in the D-term (instead of differencing position error each 1/240 s) damps overshoot and removes the “electric jitter” you get from noisy discrete derivatives when the waypoint jumps.

2. **Mass-trimmed hover**  
   After the URDF loads, the controller reads **base link mass** from `pybullet.getDynamicsInfo` and sets a vertical trim near **`m·g`**. That way the blue bird does not porpoise on a guessed gravity constant while the mesh still has a real inertia tensor in the engine.

3. **Tilt as thrust vector, not torque fight**  
   The force vector is normalised to a **desired body-up** direction (thrust along +Z). That direction is **slew-limited** (exponential smoothing) before clamping to **40° max lean**, so hard turns become a **smooth bank-to-turn** instead of a snap-roll.

4. **Kinematic attitude**  
   Orientation is applied with `resetBasePositionAndOrientation` so the art **banks into the manoeuvre** while PyBullet still integrates translation from **external forces**. That sidesteps classic “fake quad” torque wars when you are not simulating four independent rotors — but the **thrust direction matches the bank**, so the flight still reads as intentional and aggressive.

5. **Linear aerodynamic drag** on velocity for a bit of **weight in the air** once it is moving fast.

**Intercept phase (APN):** once guidance is active, `main.py` applies the pursuit thrust directly and calls `set_orientation_from_thrust` so the mesh **points into the burn** without double-counting gravity in the PD path.

### Red intruder (loitering munition)

Intruders use the **same PD structure** (`Kp·e − Kd·v`) plus **`m·g`** on the vertical channel, then layer **type-specific aerodynamics** from `scenarios.py`:

- **Quadratic drag** aligned with velocity (`½ ρ Cd A |v| v`) for high-speed realism.
- **Optional wing lift** for Shahed-class profiles (`½ ρ Cl A_w v_forward²`) so cruise feels like **pressure on the wing**, not a magic helicopter.

The nose is aligned with **velocity** (or toward the next waypoint when nearly stationary), so you get **committed forward flight** and believable turns instead of a sliding crate.

### Why it feels “cool”

Short answer: **smooth attitude**, **mass-aware hover**, **damped translation**, and **bank that matches thrust** — so the interceptor **carves** toward the threat while the intruder **drives** through the dome airspace on physics-flavoured rails. It is not a full-blown PX4-in-the-loop model, but it is coherent: every tilt you see is tied to the force vector the integrator is using that frame.

## Real maps, weather scenarios, and ML guidance

Mission geometry, the geodetic site, weather, radar quality, and map settings live
in `scenario_data/southern_ontario.json`. The configured latitude/longitude is a
placeholder; set it to an approved test location before downloading a map.

```powershell
python scripts\download_osm_map.py
python main.py --no-vispy
```

The first command caches OpenStreetMap roads and buildings locally. The PyBullet
renderer then projects them into local ENU coordinates and adds building
collision geometry. Simulation remains offline after the cache is downloaded.
Map data is copyright OpenStreetMap contributors and is available under the
Open Database License: https://www.openstreetmap.org/copyright.

### Integrated command center

The embedded tactical 3-D pane is an explicitly labeled **PyBullet Tiny
Renderer CPU preview**. It uses real cached OSM geometry and structural terrain
relief, but it is not a photorealistic or real-time production renderer. The
header reports both Qt UI refresh rate, tactical-video update rate, and the
simulation real-time factor (RTF). The versioned UDP tactical stream is the
boundary for an Unreal Engine + Cesium presentation layer; PyBullet remains the
authoritative physics/ML process.

`python main.py` now opens one operational command-center window by default.

### GPU acceleration and production runtime

The simulator now defaults to PyBullet's OpenGL camera path and reports the
actual requested render and ML compute backends in the command center. Use
`--render-backend tiny` only for CPU-renderer compatibility, or
`--render-backend opengl` to require the accelerated path explicitly.

PPO and YOLO accept `--ml-device auto|cpu|cuda`; training accepts the same
choice through `scripts\train_interceptor.py --device`. A CUDA-capable NVIDIA
GPU is not sufficient by itself: the virtual environment must contain a
CUDA-enabled PyTorch wheel. Verify it before relying on GPU execution:

```powershell
.\.venv\Scripts\python.exe -c "import torch; print(torch.cuda.is_available(), torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'CPU')"
python main.py --render-backend opengl --ml-device cuda --ml-model models\interceptor_ppo.zip
```

PyBullet remains the deterministic physics authority; its rigid-body solver is
CPU-based. OpenGL accelerates tactical rendering, while CUDA accelerates
learning and neural inference. Production-quality geospatial presentation is
still expected to consume `aegis.tactical.v1` in Unreal Engine/Cesium rather
than treating the embedded PyBullet preview as a photorealistic renderer.

Mission JSONL intentionally excludes raw video frames. Video should be stored
as a separately encoded artifact; telemetry retains only normalized state,
sensor detections, timing, backend identity, and event data.

### No-hardware regression campaign

The versioned synthetic campaign exercises named operational stress cases such
as low-altitude approaches, remote interceptor launch geometry, crosswind,
sensor latency/dropout/noise, agile targets, and a compound edge case:

```powershell
.\.venv\Scripts\python.exe scripts\run_regression_campaign.py `
  --repeats 100 `
  --seed 1000 `
  --output validation_reports\regression_campaign
```

This produces JSON episode evidence, a compact CSV summary, and an HTML
release-readiness report. Every case uses deterministic scenario geometry and
records its seed, allowing a weak or failed episode to be reproduced. The
failure analysis reports observed stress-factor correlations only; it does not
claim that a threshold factor proves root cause. Intercept gates use the lower
bound of a 95% Wilson interval rather than the optimistic point estimate, so
small perfect-looking samples do not create unsupported reliability claims.

Edit or extend
`scenario_data\regression_campaign_v1.json` to add lab-relevant cases while
keeping existing cases stable for regression history.
PyBullet runs headlessly and streams a tactical 3-D view into the same interface
as the local map, vertical profile, fused radar/EO track, event timeline, weather,
site identity, guidance mode, and mission controls. This avoids the old collection
of overlapping dashboard, PyBullet, HUD, and picture-in-picture windows.

Use `--legacy-windows` only when debugging the old standalone 3-D renderers.
Use `--auto-start` for unattended demonstrations and integration smoke tests.

The integrated view includes selectable **overview**, **Shahed track**,
**interceptor FPV**, and **top-down** cameras. Track boxes, speed/altitude labels,
velocity vectors, predicted intercept points, the vertical engagement profile,
and the live ACMI recording timeline all use the same fused state.

External presentation engines can subscribe to the versioned JSON state stream:

```powershell
python main.py --telemetry-udp 127.0.0.1:49000
```

Packets use schema `aegis.tactical.v1` and contain ENU positions/velocities,
sensor lock state, guidance mode, site identity, and the predicted intercept.
This is the renderer boundary for an Unreal/Cesium front end; PyBullet and the
ML stack remain authoritative for the local dynamics and autonomy loop.

The demonstrated use case is **critical-infrastructure airspace protection**:
detect a low-observable inbound aircraft, correlate radar and electro-optical
observations into one track, maintain a common operating picture, generate an
intercept solution, supervise autonomous response, and export the mission for
Tacview review.

This architecture follows public patterns from modern autonomy platforms:
map-centric sensor fusion and command workflow; configurable actors, sensors,
weather, and headless validation as used by CARLA; geospatial 3D Tiles as offered
by Cesium; and external robotics integration through ROS 2 and MAVLink. PyBullet
remains the fast local dynamics/test engine. A future photorealistic deployment
should keep these interfaces and replace only the renderer/physics adapter with
Unreal, Isaac Sim, or another validated digital-twin backend.

The interception task is also exposed as a Gymnasium environment with randomized
intruder type, route, wind, and radar noise:

```powershell
python scripts\train_interceptor.py --steps 500000 --output models\interceptor_ppo
python main.py --no-vispy --ml-model models\interceptor_ppo.zip
```

Without `--ml-model`, the existing APN guidance remains the default. `--sitl` can
still be used for ArduPilot control; use either SITL or an ML policy for a mission,
not both. Models trained with `--absolute-actions` must also be launched with
`--ml-absolute-actions`.

### Rendered camera perception

The simulator can render an electro-optical camera through PyBullet and recover
tracks from its RGB, depth, and segmentation buffers. This lets camera visibility
and occlusion affect guidance instead of always using perfect world state:

```powershell
python main.py --no-vispy --camera-perception
```

The segmentation mode is a deterministic reference sensor for development. To
put the existing YOLO detector directly in the simulation loop, supply trained
weights. YOLO detections select image pixels while the depth camera estimates
range:

```powershell
python main.py --no-vispy --camera-model models\finetuned\<run>\weights\best.pt
```

### Robust parallel training

The Gymnasium task randomizes route, aircraft type, wind, radar noise/dropout,
vehicle mass, actuator response, and battery thrust. PPO training uses parallel
worker processes and periodically saves checkpoints and evaluates the policy.
By default it uses **residual RL**: APN supplies the safe base command and PPO
learns bounded corrections for disturbances. A weak model therefore cannot
replace the proven pursuit controller with arbitrary flight:

```powershell
python scripts\train_interceptor.py `
  --steps 1000000 --envs 4 --checkpoint-every 100000 `
  --output models\interceptor_ppo_curriculum_v2
```

Training now defaults to a progressive procedural curriculum. It starts with
simple direct approaches and gradually introduces randomized threat bearing and
range, interceptor launch position, crossing/spiral/pop-up/dogleg geometry,
target evasion, wind, mass, actuator lag, sensor noise, dropout, and latency.
The v2 observation is translation-invariant: it learns relative position,
relative velocity, line of sight, closing speed, confidence, wind, battery, and
sensor age rather than memorizing one launch pad or map coordinate.

The live mission selector exposes six route profiles and three intruder types
across six weather/EW environments. The trainer samples continuously within and
between those regimes, so training is not limited to the 54 named UI
combinations.

Generate a reproducible APN expert dataset for imitation, regression tests, or
offline analysis:

```powershell
python scripts\generate_training_dataset.py `
  --episodes 1000 --output datasets\interceptor_expert_v2
```

The compressed dataset contains v2 observations, expert actions, episode IDs,
and scenario IDs. Its manifest records seeds, geometry, latency, outcomes,
coordinate frame, units, and validation status. Trained policies also receive a
manifest recording observation/action versions and validation requirements.

Evaluate on held-out maximum-difficulty procedural engagements:

```powershell
python scripts\benchmark_controllers.py --procedural --episodes 100 `
  --model models\interceptor_ppo_curriculum_v2.zip `
  --output reports\apn_vs_curriculum_v2
```

The included curriculum policy completed 106,496 transitions. On 100 held-out
procedural engagements, APN and residual PPO both intercepted 100/100. PPO
preserved the safety baseline but did not yet outperform it, so it should be
treated as a robustness-trained correction model rather than evidence of
superior guidance.

### What transfers to real testing

The relative-state policy, disturbance curriculum, deterministic datasets, and
held-out evaluation are useful foundations for real testing. Simulation alone
is not deployment evidence. Before any flight use, calibrate dynamics against
approved flight logs, replay representative radar/EO recordings, validate the
same policy in software-in-the-loop and hardware-in-the-loop, measure timing and
coordinate-frame errors, and complete independent safety/range review. Keep APN
and command limits as the safety envelope until those gates pass.

Use `--absolute-actions` to research a fully learned controller. Absolute mode
uses APN imitation pretraining first; set `--apn-pretrain-samples 0` to disable it.

Track training with:

```powershell
tensorboard --logdir runs\rl
```

### APN versus ML benchmark

Do not judge a learned model by training reward alone. Run every intruder type
against every route with repeatable randomized seeds:

```powershell
python scripts\benchmark_controllers.py --episodes 25 `
  --model models\interceptor_ppo.zip `
  --output reports\controller_benchmark
```

The command writes machine-readable JSON with every episode and a CSV summary
containing intercept rate, closest approach, duration, energy use, and reward.
Omit `--model` for the APN baseline or add `--include-random` as a sanity check.

The included `models/interceptor_ppo_residual.zip` starter was trained for
106,496 transitions. In `reports/apn_vs_residual_ppo.csv`, both APN and residual
PPO intercepted 225/225 randomized attacks; mean mission time was 9.089 s for APN
and 9.083 s for PPO. Treat this as a verified starter, not proof of a statistically
meaningful advantage—longer training and hardware replay are still required.

---

## 3-D view zoom (PyBullet)

PyBullet’s API does not give literal **+ / − buttons** in the native UI — only **sliders** in the **User Parameters** panel (right side when the GUI is enabled).

After you click **▶ START**, look in that panel for:

- **`3D + ZOOM (slide→1, back→0)`** — one zoom-in step per stroke  
- **`3D − ZOOM (slide→1, back→0)`** — one zoom-out step per stroke  

Same behaviour as the **`+` / `−` keys** (with the PyBullet window focused) and the **radar dashboard** zoom strip. Drag to **1**, then back toward **0**, to arm the next pulse (same pattern as red-team **FIRE** in `gym-pybullet-drones`).

---

## InnoMaker USB camera + threat detection

Live **InnoMaker U20CAM** (USB cable only — not FaceTime / iPhone) with YOLO object + drone detection. Threat boxes at **≥65%** confidence.

```bash
cd anti-drone-dome
bash run_camera_detect.sh
```

Preview only (no YOLO):

```bash
bash run_camera.sh
```

List cameras: `bash run_camera_detect.sh --list`

First run downloads YOLO weights into `models/` (gitignored). Press **Q** or **Esc** to quit.

---

## Physical drones — Betaflight firmware

Two quads in the lab use different FCs: **Omnibus F4** (CRSF, original drone) and **Fury F4 OSD** (Spektrum / DX4e). Flash, recover, and compare targets in **`docs/FIRMWARE.md`**.

Quick start:

```bash
cd anti-drone-dome/scripts
bash setup_omnibus_f4.sh        # Omnibus — diagnose / --flash
bash setup_fury_f4.sh           # Fury — diagnose / --flash
```
