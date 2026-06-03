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

### Blue interceptor (VTOL quad)

The interceptor is a **world-frame translational controller** dressed up like a quadrotor:

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

---

## 3-D view zoom (PyBullet)

PyBullet’s API does not give literal **+ / − buttons** in the native UI — only **sliders** in the **User Parameters** panel (right side when the GUI is enabled).

After you click **▶ START**, look in that panel for:

- **`3D + ZOOM (slide→1, back→0)`** — one zoom-in step per stroke  
- **`3D − ZOOM (slide→1, back→0)`** — one zoom-out step per stroke  

Same behaviour as the **`+` / `−` keys** (with the PyBullet window focused) and the **radar dashboard** zoom strip. Drag to **1**, then back toward **0**, to arm the next pulse (same pattern as red-team **FIRE** in `gym-pybullet-drones`).
