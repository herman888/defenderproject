# Anti-Drone Dome Simulation — Refinement Megaprompt V2
# Performance, Realism, Visual Quality, Sim Controls
# Run with: claude --dangerously-skip-permissions < MEGAPROMPT_V2.md

---

## CONTEXT

The base simulation is already built and working at:
`C:\Users\aclie\Documents\Side Projects\anti-drone-dome`

It has: intruder drone, interceptor drone, radar node, MAVLink datalink, kill zone logic, PyBullet 3D view.

This megaprompt REFINES and REPLACES parts of it. Do not rebuild from scratch — surgically improve what exists. Read every existing file before modifying it.

---

## PROBLEMS TO FIX (in priority order)

1. Laggy, slow physics — sim feels like it's running in slow motion
2. Drone models look like flat cheap discs
3. Checkerboard ground looks like a toy
4. Drones don't fly like real VTOL/fixed-wing hybrid drones (Ukraine-style loitering munitions fly perpendicular to their body axis — nose pitched forward, thrust vectored)
5. No sim controls — can't slow down, speed up, restart, or pause
6. Sim quits after one run — should loop back to menu
7. No realistic flight dynamics — drones just slide around

---

## STRICT RULES

- Read each existing file fully before editing it
- Do not break working functionality — radar, MAVLink, kill zone must still work
- Test after every major change
- All changes must work on Windows 11 and macOS
- Use only: pybullet, numpy, matplotlib, pymavlink, OpenGL (via PyOpenGL if needed)
- If a fix requires a new dependency, install it first and verify it works
- Log all changes to console as you make them

---

## FIX 1 — PERFORMANCE: Decouple physics from rendering

The lag comes from PyBullet GUI blocking the physics loop. Fix this:

In `main.py` and `sim/physics.py`:
- Run physics at fixed 240Hz using `time.perf_counter()` for precise timing
- Decouple render updates — only call PyBullet camera/debug updates every 24 physics steps (10Hz render, 240Hz physics)
- Use `pybullet.setRealTimeSimulation(0)` — manual stepping is always faster than realtime mode
- Add a simulation speed multiplier: `SIM_SPEED = 1.0` global variable
- Each physics step: `time_step = (1/240) * SIM_SPEED`
- Cap max sim speed at 8x to prevent physics explosion
- Add frame timing: measure actual vs target frame time, log if falling behind
- Pre-load all URDFs at startup, never load during the main loop
- Disable PyBullet shadows: `pybullet.configureDebugVisualizer(pybullet.COV_ENABLE_SHADOWS, 0)`
- Disable PyBullet GUI panels: `pybullet.configureDebugVisualizer(pybullet.COV_ENABLE_GUI, 0)`
- Disable RGB buffer: `pybullet.configureDebugVisualizer(pybullet.COV_ENABLE_RGB_BUFFER_PREVIEW, 0)`
- These three lines alone will dramatically improve performance

---

## FIX 2 — DRONE MODELS: Replace flat discs with proper VTOL geometry

Delete the existing drone URDF and replace with two separate URDFs:

### assets/intruder.urdf — Loitering munition style (Ukraine Lancet/Shahed inspired)
Build this geometry in URDF:
- Main fuselage: cylinder, length=0.6m, radius=0.06m, mass=1.2kg, dark gray
- Delta wings: two thin boxes (0.4m x 0.15m x 0.01m) swept back at 45°, one each side, mass=0.1kg each
- Nose cone: small sphere radius=0.06m at front of fuselage
- Tail fins: two small boxes (0.1m x 0.08m x 0.008m) at rear, crossed in X pattern
- Two rotors: cylinders radius=0.12m, height=0.01m, mounted on top via short arms (0.15m), counter-rotating
- Color: dark matte gray (0.2, 0.2, 0.2) fuselage, slightly lighter wings
- The fuselage axis is HORIZONTAL — this drone flies like a plane, not a quadcopter
- Center of mass offset slightly forward for stability

### assets/interceptor.urdf — Military quadrotor style
Build this geometry:
- Central body: octagonal prism shape (approximate with box 0.25x0.25x0.08m), mass=1.5kg
- 4 arms: thin boxes extending diagonally (0.3m long, 0.025m wide, 0.015m tall)
- 4 rotors: flat cylinders radius=0.13m at arm tips, height=0.008m
- Landing gear: 4 thin struts hanging below body
- Color: dark blue (0.1, 0.15, 0.4) body, lighter blue arms
- Rotor colors alternate: two cyan, two white (front/back distinction)

---

## FIX 3 — FLIGHT DYNAMICS: Realistic VTOL flight model

This is the most important fix. Current drones slide — they need to fly.

### Intruder flight dynamics (loitering munition style):
In `sim/drone.py`, create a separate `LoiteringMunition` class:

- Flies with fuselage HORIZONTAL, nose pitched slightly down (5-10°) during cruise
- Uses differential rotor thrust for pitch/roll control
- Forward motion from tilting the entire body forward (like a real fixed-wing)
- During turns: banks into the turn (roll), then pitch up slightly
- Approach behavior: spiraling descent as it approaches target
- Apply aerodynamic drag force proportional to velocity squared: F_drag = -0.5 * rho * Cd * A * v^2
  - rho = 1.225 (air density), Cd = 0.3, A = 0.05 (frontal area)
- Apply lift force on wings proportional to forward velocity: F_lift = 0.5 * rho * Cl * A_wing * v_forward^2
  - Cl = 0.8, A_wing = 0.12
- Max cruise speed: 25 m/s
- Rotor animation: spin fast (visually), speed proportional to throttle

### Interceptor flight dynamics (quadrotor style):
In `sim/drone.py`, update the `Drone` class:

- Quadrotor model: 4 rotors produce upward thrust
- Attitude control via differential thrust between rotors
- Tilt to move horizontally: to move forward, tilt nose down by applying pitch torque
- Max tilt angle: 35 degrees
- Use quaternion-based attitude representation
- PD controller with proper gains:
  - Position Kp=8.0, Kd=4.0
  - Attitude Kp=50.0, Kd=10.0
- When intercepting: bank aggressively toward target, tilt up to 45 degrees
- Apply realistic drag: F_drag = -0.2 * velocity (linear drag approximation)
- Rotor animation: 4 rotors spin, front pair clockwise, rear pair counter-clockwise
- Max speed: 20 m/s

### Both drones:
- Apply gravity correctly (already done by PyBullet but verify)
- Add slight random wind disturbance every 2 seconds: random force (0.5N max) in random horizontal direction
- Constrain flight: drones cannot go below z=0.5m (ground collision)
- Add rotor sound simulation (console log RPM changes)

---

## FIX 4 — GROUND AND ENVIRONMENT: Replace checkerboard

In `sim/physics.py`:

- Remove the default PyBullet plane.urdf (it loads the checkerboard texture)
- Create a custom flat ground using `pybullet.createCollisionShape` + `pybullet.createMultiBody`:
  ```python
  ground_collision = pybullet.createCollisionShape(pybullet.GEOM_BOX, halfExtents=[50, 50, 0.1])
  ground_visual = pybullet.createVisualShape(pybullet.GEOM_BOX, halfExtents=[50, 50, 0.1], 
                    rgbaColor=[0.15, 0.18, 0.15, 1])  # dark military green-gray
  ground = pybullet.createMultiBody(0, ground_collision, ground_visual, [0,0,-0.1])
  ```
- Draw a tactical grid using debug lines instead of texture:
  - Grid lines every 5m, range -50m to +50m
  - Color: (0.25, 0.3, 0.25) — subtle dark green
  - Thicker lines every 25m: (0.4, 0.45, 0.4)
  - Cardinal direction markers at N/S/E/W edges (text labels via addUserDebugText)
- Add a radar station visual at origin:
  - Pole: thin cylinder 3m tall
  - Radar dish: flattened cylinder on top, slowly rotating (update rotation each frame)
  - Color: (0.5, 0.5, 0.5) military gray
- Draw range rings on the ground:
  - Rings at 5m, 10m (dome boundary), 15m, 20m radius
  - Dome boundary ring: brighter green (0.0, 0.8, 0.2)
  - Other rings: dim (0.2, 0.3, 0.2)
- Add 3-4 simple "asset" markers inside the dome to show what's being protected:
  - Small boxes representing buildings/infrastructure at (2,1,0), (-1,2,0), (1,-2,0)
  - Color: (0.6, 0.5, 0.3) — tan/sand color like military structures
- Draw the dome as a hemisphere wireframe:
  - 12 longitude lines + 6 latitude lines
  - Normal state: dim green (0.0, 0.5, 0.1, 0.3)
  - Tracking state: yellow (0.8, 0.7, 0.0)
  - Breach state: red (1.0, 0.1, 0.1) + increase line width
  - Use removeAllUserDebugItems + redraw each status change (not every frame)

---

## FIX 5 — SIM CONTROLS: Full keyboard control panel

In `main.py`, add a keyboard control system using PyBullet's built-in key detection:

```python
keys = pybullet.getKeyboardEvents()
```

Implement these controls:

| Key | Action |
|-----|--------|
| SPACE | Pause / Resume simulation |
| R | Restart simulation (reset all positions, re-run) |
| 1 | Set sim speed 0.25x (slow motion) |
| 2 | Set sim speed 0.5x |
| 3 | Set sim speed 1.0x (normal) |
| 4 | Set sim speed 2.0x |
| 5 | Set sim speed 4.0x |
| 6 | Set sim speed 8.0x (fast forward) |
| C | Cycle camera: Overview / Chase intruder / Chase interceptor / Top-down radar view |
| I | Toggle intruder trail on/off |
| D | Toggle dashboard window on/off |
| Q | Quit cleanly |
| H | Print help text to console listing all controls |

Camera modes:
- Overview: distance=25, yaw=45, pitch=-30, target=(0,0,0)
- Chase intruder: distance=5, follows intruder position, pitch=-15
- Chase interceptor: distance=5, follows interceptor position, pitch=-15  
- Top-down: distance=30, yaw=0, pitch=-89, target=(0,0,0)

Show current sim speed and pause state in PyBullet HUD:
```python
pybullet.addUserDebugText(f"SPEED: {SIM_SPEED}x {'[PAUSED]' if paused else ''}", 
                          [-8, -8, 8], textColorRGB=[1,1,0], textSize=1.5)
```

---

## FIX 6 — MISSION LOOP: Don't quit, return to menu

Replace the current single-run main loop with a mission loop:

```
MAIN MENU (console)
├── [1] Run simulation (normal speed)
├── [2] Run simulation (fast - 4x)  
├── [3] Run with custom scenario
└── [4] Quit
```

After each mission completes (intercept success, failure, or timeout):
- Display full mission debrief in console:
  ```
  ╔══════════════════════════════════════╗
  ║         MISSION DEBRIEF              ║
  ╠══════════════════════════════════════╣
  ║ Result:        INTERCEPT SUCCESS     ║
  ║ Duration:      47.3 seconds          ║
  ║ First detect:  T+2.1s at 18.4m      ║
  ║ Dome breach:   T+18.7s              ║
  ║ Intercept:     T+31.2s at (4.2,3.1) ║
  ║ Max penetration: 6.8m into dome     ║
  ║ Interceptor approach: 1.2m          ║
  ╚══════════════════════════════════════╝
  Press [R] to run again | [M] for menu | [Q] to quit
  ```
- Wait for keypress
- On R: reset and rerun same scenario
- On M: return to main menu
- On Q: exit cleanly

Add 3 built-in scenarios in `scenarios.py`:
```python
SCENARIOS = {
    "standard": {
        "intruder_start": (15, 15, 8),
        "intruder_speed": 12,  # m/s
        "intruder_path": "direct_approach",
        "interceptor_start": (0, 0, 0),
        "interceptor_response_delay": 2.0,  # seconds after detection
        "wind": False,
        "description": "Single intruder, direct approach, standard conditions"
    },
    "fast_low": {
        "intruder_start": (20, 0, 3),
        "intruder_speed": 22,
        "intruder_path": "low_fast_approach",
        "interceptor_start": (-2, 0, 0),
        "interceptor_response_delay": 1.0,
        "wind": True,
        "description": "Fast low-altitude intruder, harder to detect"
    },
    "spiral": {
        "intruder_start": (18, 0, 10),
        "intruder_speed": 10,
        "intruder_path": "spiral_descent",
        "interceptor_start": (0, 0, 0),
        "interceptor_response_delay": 3.0,
        "wind": False,
        "description": "Spiraling descent attack pattern"
    }
}
```

---

## FIX 7 — DASHBOARD: Make it look military grade

Rebuild `viz/dashboard.py` with this aesthetic:

- Dark background: #080c10 (very dark blue-black)
- Primary color: #00ff88 (military green)
- Warning color: #ffaa00 (amber)
- Danger color: #ff2200 (red)
- Text font: monospace everywhere
- Add a header bar: "ANTI-DRONE DEFENSE SYSTEM | ACTIVE" with blinking indicator
- Radar display improvements:
  - Add rotating sweep line that leaves a fading trail (phosphor effect)
  - Implement sweep using a wedge that fades over 2 seconds
  - Blips flash briefly when sweep passes over them
  - Add distance labels on range rings: "5m", "10m", "15m", "20m"
  - Draw N/S/E/W compass labels
  - Track history: gradient from bright to dim (recent = bright)
  - Interceptor: blue triangle shape instead of dot, pointing toward target
  - Intruder: red diamond shape
  - Predicted intercept point: yellow X marker
- Status panel improvements:
  - Large status text with background color fill matching status
  - Threat level bar (0-100%) based on intruder proximity to center
  - Timeline bar showing mission elapsed time
  - Mini-map thumbnail showing 3D view orientation
  - Event log with color coding:
    - DETECTION: green
    - BREACH: orange  
    - INTERCEPT: cyan
    - FAILURE: red

---

## FIX 8 — VISUAL TRAILS AND EFFECTS

Add to `sim/physics.py`:

- Intruder trail: draw debug line between last position and current position every 5 frames
  - Color fades from bright red (recent) to dark red (old)
  - Keep last 30 trail segments, remove oldest when adding new
  - Store line IDs and use `removeUserDebugItem` to clear old ones
- Interceptor trail: same but blue
- Intercept vector line: yellow line from interceptor to predicted intercept point, updates every frame
- On intercept event: draw a bright white flash sphere at intercept point
  ```python
  pybullet.addUserDebugText("INTERCEPT", position, textColorRGB=[1,1,1], textSize=3, lifeTime=3)
  ```
- On dome breach: flash dome color red 3 times (toggle color rapidly)

---

## FINAL VERIFICATION

After all fixes, run:
```bash
python tests/test_drone.py
python tests/test_radar.py  
python tests/test_datalink.py
python tests/test_intercept.py
```

All must pass.

Then run:
```bash
python main.py
```

Verify:
- [ ] Ground is dark military green, no checkerboard
- [ ] Drones have proper 3D geometry (not flat discs)
- [ ] Intruder flies with nose forward like a loitering munition
- [ ] Interceptor tilts to fly horizontally
- [ ] Sim runs smooth (no lag) at 1x speed
- [ ] Speed controls work (1-6 keys)
- [ ] Pause works (SPACE)
- [ ] Restart works (R key)
- [ ] Camera modes cycle (C key)
- [ ] After mission ends, debrief shows and waits for input
- [ ] R reruns, M goes to menu, Q quits
- [ ] Dashboard looks dark and military, not default matplotlib blue
- [ ] Drone trails visible in 3D view
- [ ] Dome wireframe changes color on breach

---

## IF PYBULLET VISUAL QUALITY IS STILL NOT ENOUGH

If after all the above PyBullet still looks too basic, add a secondary OpenGL renderer:

Install: `pip install PyOpenGL PyOpenGL_accelerate`

Create `viz/opengl_renderer.py` that:
- Opens a separate OpenGL window alongside PyBullet
- Reads drone positions from the sim state dict every frame
- Renders drones as proper 3D meshes using OpenGL primitives
- Implements basic Phong shading (ambient + diffuse + specular)
- Dark military environment with subtle fog effect
- This runs as a separate thread, reading shared state

Only implement this if the base PyBullet fixes are insufficient.
