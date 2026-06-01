# Anti-Drone Dome Simulation — Claude Code Megaprompt
# Weeks 2 & 3 Full Build
# Run with: claude --dangerously-skip-permissions < MEGAPROMPT.md

---

## CONTEXT

You are building a complete anti-drone dome simulation system from scratch. The project is located at:
`C:\Users\aclie\Documents\Side Projects\anti-drone-dome`

The venv is already created and activated. The following packages are already installed:
- numpy
- matplotlib
- pymavlink

You need to install pybullet as the first step.

The system simulates:
1. An intruder drone flying a scripted attack path toward a protected zone
2. A ground radar node detecting the intruder with realistic noise
3. A MAVLink data link broadcasting the track
4. An interceptor drone that autonomously launches and pursues the intruder
5. Kill zone logic that flags a successful intercept
6. A real-time visualization dashboard

---

## STRICT RULES

- Every file must be fully working Python code, no placeholders, no TODOs
- Every module must be independently runnable for testing
- Use only: pybullet, numpy, matplotlib, pymavlink — no other dependencies
- All code must run on Windows 11 and macOS (no OS-specific APIs)
- Use relative imports and relative file paths throughout
- Every file gets a docstring explaining what it does
- After writing each file, write a test to confirm it works
- If a step fails, diagnose and fix before moving on — do not skip
- Log everything to console so progress is visible overnight

---

## PROJECT STRUCTURE TO CREATE

```
anti-drone-dome/
├── assets/
│   └── drone.urdf              # quadrotor URDF model
├── sim/
│   ├── __init__.py
│   ├── physics.py              # PyBullet world setup
│   ├── drone.py                # Drone class with PD hover controller
│   └── waypoints.py            # Waypoint navigation
├── sensors/
│   ├── __init__.py
│   └── radar.py                # Simulated radar with Gaussian noise
├── comms/
│   ├── __init__.py
│   └── datalink.py             # MAVLink UDP broadcast/receive
├── guidance/
│   ├── __init__.py
│   └── intercept.py            # Pure pursuit guidance law
├── dome/
│   ├── __init__.py
│   └── killzone.py             # Dome boundary + intercept detection
├── viz/
│   ├── __init__.py
│   └── dashboard.py            # Real-time matplotlib dashboard
├── tests/
│   ├── test_drone.py
│   ├── test_radar.py
│   ├── test_datalink.py
│   └── test_intercept.py
├── main.py                     # Full simulation runner
└── requirements.txt
```

---

## STEP 1 — INSTALL PYBULLET

Run:
```
pip install pybullet
```

Verify it installed by running:
```python
import pybullet
print("PyBullet version:", pybullet.__version__)
```

If it fails on Windows, try:
```
pip install pybullet --only-binary=:all:
```

---

## STEP 2 — CREATE requirements.txt

```
pybullet
numpy
matplotlib
pymavlink
```

---

## STEP 3 — CREATE assets/drone.urdf

Create a quadrotor URDF with:
- Central body: box, mass 1.5kg, size 0.3x0.3x0.1m
- 4 rotor arms extending diagonally
- 4 rotor discs at arm tips (visual only, thin cylinders)
- Realistic inertia tensor for a 1.5kg quadrotor
- Material colors: dark gray body, red/blue rotors (front/back distinction)
- Link names: base_link, rotor_0, rotor_1, rotor_2, rotor_3

---

## STEP 4 — CREATE sim/physics.py

This module sets up the PyBullet world. It must:
- Initialize PyBullet in GUI mode with `pybullet.connect(pybullet.GUI)`
- Set gravity to (0, 0, -9.81)
- Load a ground plane using `pybullet.loadURDF("plane.urdf")`
- Set camera to a good overhead/isometric view for the dome scene
- Camera position: distance=20, yaw=45, pitch=-30, target=(0,0,0)
- Set background color to dark (RGB 0.1, 0.1, 0.15) for military aesthetic
- Draw a reference grid on the ground plane using debug lines (gray, 1m spacing, 20x20m)
- Expose a `step()` function that advances simulation by one timestep (1/240s)
- Expose a `reset()` function
- Expose a `draw_dome(center, radius, color)` function that draws a hemisphere using PyBullet debug lines
- The dome should be drawn as latitude/longitude wireframe lines, color (0,1,0) default green, turns (1,0,0) red on breach

---

## STEP 5 — CREATE sim/drone.py

Create a `Drone` class that must:
- Accept: drone_id (str), start_position (x,y,z), physics_client
- Load the drone URDF from assets/drone.urdf
- Implement a PD hover controller:
  - Target altitude maintained via upward force
  - Kp=10.0, Kd=5.0 gain values
  - Apply force at center of mass each timestep
- Expose `set_target(x, y, z)` — sets navigation target
- Expose `update()` — called every timestep, applies PD control forces
- Expose `get_position()` — returns (x, y, z) tuple
- Expose `get_velocity()` — returns (vx, vy, vz) tuple
- Expose `get_state()` — returns dict with position, velocity, orientation, timestamp
- Implement basic 3D navigation: apply horizontal forces toward target x,y while maintaining altitude z
- Max horizontal force: 15N
- Max vertical force: 20N
- Drone should not exceed 15 m/s
- Add rotor spin animation (rotate rotor joints each timestep for visual effect)
- Intruder drone: red color tint
- Interceptor drone: blue color tint

---

## STEP 6 — CREATE sim/waypoints.py

Create a `WaypointNavigator` class that:
- Accepts a list of (x, y, z) waypoints
- Tracks current waypoint index
- Returns current target waypoint
- Advances to next waypoint when drone gets within 1.5m of current target
- Exposes `is_complete()` — True when all waypoints visited
- Exposes `get_current_target()` — returns current (x,y,z) waypoint
- Exposes `update(drone_position)` — checks proximity, advances waypoints
- Create a default intruder attack path:
  - Starts at (15, 15, 8) — outside dome
  - Approaches (8, 8, 6)
  - Moves to (4, 4, 5)
  - Penetrates to (1, 1, 4) — inside dome
  - Target (0, 0, 3) — center/asset being protected
- This path should look like a realistic attack run, not a straight line

---

## STEP 7 — CREATE sensors/radar.py

Create a `RadarNode` class that:
- Accepts: protected_center (x,y,z), max_range (float, default 20m), noise_std (float, default 0.3m)
- Exposes `scan(drone_position)` — takes true drone position, returns radar return
- Radar return is a dict: {detected: bool, range: float, bearing_deg: float, elevation_deg: float, position_estimate: (x,y,z), snr: float}
- Adds Gaussian noise (numpy) to range and bearing — simulates real radar imprecision
- Detection probability: 95% within 15m, drops off to 60% at 20m (use random draw)
- Below minimum detectable range of 2m: always detected (too close to miss)
- SNR calculated as: 30 - (range/max_range)*20 dB, plus Gaussian noise
- Lost track: if scan() called and not detected, return {detected: False}
- Maintain track history: last 50 returns stored in self.track_history
- Exposes `get_track_history()` — returns list of last N position estimates
- Exposes `get_track_velocity()` — estimates velocity from last 2 track positions + timestamps
- Log detection events to console: "RADAR: Track acquired at range X.Xm, bearing X.X°"

---

## STEP 8 — CREATE comms/datalink.py

Create a `DataLink` class using pymavlink that:
- Implements MAVLink UDP communication
- Broadcaster role: `DataLink(role='broadcast', port=14550)`
- Receiver role: `DataLink(role='receive', port=14550)`
- Exposes `send_track(track_data)` — serializes and sends track via MAVLink GLOBAL_POSITION_INT message
  - Map our simulation coords to lat/lon/alt (use simple linear mapping: 1m = 0.00001 degrees)
  - Base lat: 43.0000, Base lon: -79.0000 (Toronto area for realism)
- Exposes `receive_track()` — returns latest track dict or None
- Non-blocking: use UDP with timeout=0.01s
- Handle connection errors gracefully — if no receiver, broadcast silently fails without crashing
- Log MAVLink messages: "DATALINK: Broadcasting track — pos (X, Y, Z) vel (VX, VY, VZ)"
- Include sequence numbers in messages for packet loss detection

---

## STEP 9 — CREATE guidance/intercept.py

Create a `PurePursuitGuidance` class that:
- Implements pure pursuit intercept guidance law
- Accepts: interceptor_position, interceptor_velocity, target_position, target_velocity
- Exposes `compute_guidance(interceptor_state, target_track)` — returns (fx, fy, fz) force vector
- Pure pursuit algorithm:
  - Compute line of sight vector from interceptor to target
  - Predict target position in T seconds (T = range / closing_speed, capped at 3s)
  - Steer toward predicted intercept point
  - Proportional navigation gain: N=3
- Max guidance force: 25N
- Includes lead angle computation — interceptor leads the target, doesn't just chase
- Exposes `time_to_intercept(interceptor_state, target_track)` — estimates seconds to intercept
- Exposes `intercept_possible(interceptor_state, target_track)` — returns bool based on kinematics
- Log guidance commands: "GUIDANCE: Steering to intercept at predicted pos (X,Y,Z), TTI=X.Xs"

---

## STEP 10 — CREATE dome/killzone.py

Create a `DomeKillZone` class that:
- Accepts: center (x,y,z), radius (float, default 10m)
- Exposes `is_inside(position)` — returns bool
- Exposes `distance_to_boundary(position)` — returns float (negative = inside)
- Exposes `check_breach(intruder_position)` — returns breach event dict or None
  - Breach event: {breached: True, position: (x,y,z), time: float, distance_to_center: float}
- Exposes `check_intercept(interceptor_position, intruder_position, intercept_radius=3.0)` — returns bool
- Tracks breach history: timestamps + positions of all boundary crossings
- Exposes `get_status()` — returns 'CLEAR', 'TRACKING', 'BREACH', or 'INTERCEPTED'
- Status transitions:
  - CLEAR → TRACKING: intruder detected by radar within dome range
  - TRACKING → BREACH: intruder crosses dome boundary
  - BREACH → INTERCEPTED: interceptor gets within intercept_radius of intruder
  - Any → CLEAR: intruder exits dome range and no active breach
- Log all status transitions: "DOME STATUS: CLEAR → TRACKING"

---

## STEP 11 — CREATE viz/dashboard.py

Create a `Dashboard` class using matplotlib that:
- Opens a figure with 2 subplots side by side
- LEFT: 2D top-down radar view
  - Dark background (0.05, 0.05, 0.1)
  - Dome boundary circle in green (red when breached)
  - Radar sweep animation (rotating line, updates every 10 sim steps)
  - Intruder blip: red dot, track history as fading red trail (last 20 positions)
  - Interceptor blip: blue dot, blue trail
  - Intercept vector: yellow dashed line from interceptor to predicted intercept point
  - Range rings at 5m, 10m, 15m, 20m in dim gray
  - Cardinal labels: N/S/E/W
- RIGHT: Mission status panel
  - Dome status (large text, color coded: green=CLEAR, yellow=TRACKING, orange=BREACH, red=INTERCEPTED)
  - Intruder: range to center, bearing, speed, altitude
  - Interceptor: distance to intruder, TTI (time to intercept), speed
  - Radar: SNR, last detection time, track confidence %
  - Event log: last 5 events with timestamps (scrolling)
- Exposes `update(sim_state)` — takes full simulation state dict, redraws
- Updates at 10Hz (every 24 sim steps at 240Hz physics)
- Non-blocking: use plt.pause(0.001)
- Title: "ANTI-DRONE DOME — ACTIVE DEFENSE SYSTEM" in military font style

---

## STEP 12 — CREATE tests/test_drone.py

Test that:
1. Drone loads without crashing
2. Hover controller maintains altitude within 0.5m after 5 seconds
3. Waypoint navigation reaches target within 2m
4. get_state() returns all required fields
Print PASS/FAIL for each test.

---

## STEP 13 — CREATE tests/test_radar.py

Test that:
1. Radar detects drone at 5m range (should always detect)
2. Radar output has correct field names
3. Noise is being applied (10 detections at same position should not all be identical)
4. Track history accumulates correctly
Print PASS/FAIL for each test.

---

## STEP 14 — CREATE tests/test_datalink.py

Test that:
1. DataLink broadcaster initializes without error
2. DataLink receiver initializes without error
3. Send + receive round trip works (send a track, receive it back)
4. Malformed data handled gracefully
Print PASS/FAIL for each test.

---

## STEP 15 — CREATE tests/test_intercept.py

Test that:
1. Pure pursuit returns a force vector pointing toward target
2. Force magnitude does not exceed max (25N)
3. TTI estimate is positive and reasonable
4. Lead angle is non-zero when target is moving
Print PASS/FAIL for each test.

---

## STEP 16 — CREATE main.py

This is the full simulation runner. It must:

```python
"""
Anti-Drone Dome Simulation
Full system: intruder drone, ground radar, MAVLink data link,
interceptor drone with pure pursuit guidance, kill zone logic,
real-time dashboard visualization.

Run: python main.py
"""
```

The main loop must:
1. Initialize PyBullet physics world
2. Spawn intruder drone at start position (15, 15, 8)
3. Spawn interceptor drone at (0, 0, 0) — on the ground, on standby
4. Initialize radar node centered at (0, 0, 0), range 20m
5. Initialize dome kill zone centered at (0, 0, 0), radius 10m
6. Initialize MAVLink datalink (broadcaster)
7. Initialize dashboard
8. Initialize intruder waypoint path (attack run toward center)
9. Interceptor stays grounded until radar acquires track (TRACKING status)
10. On TRACKING: interceptor launches, receives MAVLink track cues, begins pursuit
11. Main loop at 240Hz physics, dashboard updates at 10Hz:
    - Step physics
    - Update intruder waypoints + navigation
    - Run radar scan
    - If detected: broadcast MAVLink track
    - Update dome status
    - Update interceptor guidance (if launched)
    - Every 24 steps: update dashboard
    - Log to console every 48 steps (2x/second):
      "T+XX.Xs | INTRUDER: (X,Y,Z) | RADAR: Xm | DOME: STATUS | INTERCEPTOR: Xm to target"
12. Simulation ends when:
    - INTERCEPTED (success) — print mission summary
    - Intruder reaches center (0,0,0) (failure) — print failure report
    - 120 seconds elapsed (timeout)
13. On completion print full mission report:
    - Time to first detection
    - Time to dome breach
    - Time to intercept (or failure reason)
    - Intruder max penetration depth
    - Interceptor closest approach distance

---

## STEP 17 — FINAL VERIFICATION

Run the full test suite:
```
python tests/test_drone.py
python tests/test_radar.py
python tests/test_datalink.py
python tests/test_intercept.py
```

All tests must pass before running main.py.

Then run:
```
python main.py
```

The simulation should open a PyBullet 3D window and a matplotlib dashboard window simultaneously. Both should update in real time. The interceptor should successfully intercept the intruder within 60 seconds under normal conditions.

---

## IF ANYTHING FAILS

- PyBullet GUI crashes: fall back to `pybullet.connect(pybullet.DIRECT)` for headless mode, keep dashboard
- URDF load fails: use `pybullet.loadURDF("sphere.urdf")` as fallback drone shape
- MAVLink port conflict: try port 14551, then 14552
- matplotlib not rendering: add `matplotlib.use('TkAgg')` at top of dashboard.py
- Import errors: check all `__init__.py` files expose the right classes

---

## DELIVERABLE

When complete, the following command should work from the project root:
```
python main.py
```

And produce a fully running anti-drone dome simulation with real-time 3D physics and 2D radar dashboard.
