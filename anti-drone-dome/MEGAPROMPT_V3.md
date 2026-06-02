# Anti-Drone Dome Simulation — Megaprompt V3
# Visual Polish + Tacview ACMI Export + Quality Pass
# DO NOT SCRAP ANYTHING — surgical improvements only
# Paste directly into Claude Code

---

## CRITICAL RULES — READ FIRST

- Read EVERY existing file fully before touching anything
- Do NOT change: APN guidance math, Kalman tracker, radar detection model, MAVLink datalink, IPC queue structure, mission flow, scenario definitions
- Do NOT change physics constants: dome radius 200m, timestep 1/240s, interceptor max speed 100m/s
- Do NOT change the multiprocessing architecture
- Only add or improve — never remove working functionality
- Test after every major change, fix errors before moving on
- If something breaks, revert that specific change only

---

## WHAT TO IMPROVE (in priority order)

1. Tacview ACMI export — pipe sim data into Tacview for professional 3D visualization
2. PyBullet visual quality — ground, lighting, drone models, environment
3. Dashboard aesthetic — military grade, not default matplotlib
4. Drone flight visuals — proper orientation, rotor spin, trails
5. Sound/haptic feedback via console — audio cues for events
6. Performance — smooth 240Hz physics, no lag

---

## IMPROVEMENT 1 — TACVIEW ACMI EXPORT

Create `viz/acmi_writer.py`:

```python
"""
Writes Tacview-compatible ACMI 2.1 files in real time.
Tacview (free version from tacview.net) can load this file live
while the sim is running for professional 3D mission visualization.
"""
```

The ACMIWriter class must:

- Create `missions/` folder if not exists
- Open `missions/session_YYYYMMDD_HHMMSS.acmi` at init
- Write header:
```
FileType=text/acmi/tabular
FileVersion=2.1
0,ReferenceTime=2024-01-01T00:00:00Z
0,ReferenceLatitude=43.0000
0,ReferenceLongitude=-79.0000
0,Title=Anti-Drone Dome Defense
0,Author=DefenderProject
0,Category=Anti-Drone Defense
0,Briefing=Anti-drone dome defense simulation. Dome radius: 200m.
```

- Object IDs: intruder=1, interceptor=2, radar=3, dome_center=4
- Write initial object declarations after header:
```
1,T=0|0|220,Name=Intruder,Type=Air+FixedWing,Color=Red,Coalition=Enemies
2,T=0|-250|5,Name=Interceptor,Type=Air+Rotorcraft,Color=Blue,Coalition=Allies  
3,T=0|-200|10,Name=RadarStation,Type=Ground+Static,Color=Green,Coalition=Allies
4,T=0|0|0,Name=DomeCenter,Type=Ground+Static,Color=Green,Coalition=Allies
```

- `update(elapsed_seconds, intruder_state, interceptor_state, radar_state)`:
  - Convert sim XYZ to lat/lon: lat = ref_lat + (y/111111), lon = ref_lon + (x/111111), alt = z
  - Get roll/pitch/yaw from drone state (degrees)
  - Write timestamped update every call:
  ```
  #ELAPSED_SECONDS
  1,T=LON|LAT|ALT|ROLL|PITCH|YAW
  2,T=LON|LAT|ALT|ROLL|PITCH|YAW
  ```
  - Only write interceptor line if interceptor is airborne (z > 1.0)
  - Flush every 48 updates for real-time Tacview viewing

- `write_event(elapsed, event_type, message)`:
  - RADAR_LOCK: `0,Event=Message|SourceId:3|Message:Radar Lock - Track Acquired`
  - DOME_BREACH: `0,Event=Message|SourceId:1|Message:DOME BREACH - Intruder Inside Perimeter`
  - INTERCEPT: `0,Event=Timeout|SourceId:2|AmmoType:INTERCEPT|TargetId:1|Outcome:Kill`
  - MISS: `0,Event=Message|SourceId:1|Message:MISSION FAILED - Intruder Reached Target`

- `close()`: flush and close file, print path to console

Integrate into `main.py`:
- Instantiate ACMIWriter at mission start (not at sim start — only when mission begins)
- Call `writer.update()` every 24 physics steps (10Hz — enough for smooth Tacview)
- Call `writer.write_event()` on all dome status transitions
- Call `writer.close()` at mission end
- Print at mission start:
```
╔══════════════════════════════════════════════════════╗
║  TACVIEW EXPORT ACTIVE                               ║
║  File: missions/session_TIMESTAMP.acmi               ║
║  Open Tacview → File → Open → select this file       ║
║  For live view: load file while simulation is running ║
╚══════════════════════════════════════════════════════╝
```

---

## IMPROVEMENT 2 — PYBULLET VISUAL QUALITY

In `sim/physics.py`, make these changes:

### Performance first (do these before anything visual):
```python
pybullet.configureDebugVisualizer(pybullet.COV_ENABLE_SHADOWS, 0)
pybullet.configureDebugVisualizer(pybullet.COV_ENABLE_GUI, 0)
pybullet.configureDebugVisualizer(pybullet.COV_ENABLE_RGB_BUFFER_PREVIEW, 0)
pybullet.configureDebugVisualizer(pybullet.COV_ENABLE_TINY_RENDERER, 0)
pybullet.setRealTimeSimulation(0)  # manual stepping always faster
```

### Replace checkerboard ground:
Remove `loadURDF("plane.urdf")`. Replace with:
```python
# Dark military terrain — no checkerboard
col = pybullet.createCollisionShape(pybullet.GEOM_BOX, halfExtents=[1500,1500,0.5])
vis = pybullet.createVisualShape(pybullet.GEOM_BOX, halfExtents=[1500,1500,0.5],
        rgbaColor=[0.12, 0.15, 0.12, 1.0])  # dark military green-gray
pybullet.createMultiBody(0, col, vis, [0, 0, -0.5])
```

### Tactical grid (debug lines, not texture):
Draw grid lines every 50m from -800 to +800:
- Minor grid (50m): color (0.18, 0.22, 0.18)
- Major grid (200m): color (0.28, 0.35, 0.28)
- Dome boundary ring at radius=200m: 64-point circle, color (0.0, 0.7, 0.15), lineWidth=2
- Inner ring at 100m: color (0.0, 0.4, 0.1)
- Cardinal markers: addUserDebugText "N" at (0, 250, 2), "S" at (0,-250,2), "E" at (250,0,2), "W" at (-250,0,2), color (0.5,0.6,0.5), size 1.2

### Dome hemisphere wireframe:
Draw dome as 12 longitude + 8 latitude lines at radius=200m, height 0-200m:
- Store all line IDs in `self._dome_line_ids`
- `update_dome_color(status)`: remove old lines, redraw in new color
  - CLEAR: (0.0, 0.6, 0.1) dim green
  - TRACKING: (0.8, 0.7, 0.0) amber
  - BREACH: (1.0, 0.1, 0.05) red
  - INTERCEPTED: (0.0, 0.8, 1.0) cyan flash

### Radar station visual at (0, -200, 0):
```python
# Mast
mast_col = pybullet.createCollisionShape(pybullet.GEOM_CYLINDER, radius=0.3, height=10)
mast_vis = pybullet.createVisualShape(pybullet.GEOM_CYLINDER, radius=0.3, length=10,
             rgbaColor=[0.4,0.4,0.45,1])
pybullet.createMultiBody(0, mast_col, mast_vis, [0,-200,5])

# Dish (flat cylinder on top)
dish_col = pybullet.createCollisionShape(pybullet.GEOM_CYLINDER, radius=2.0, height=0.3)
dish_vis = pybullet.createVisualShape(pybullet.GEOM_CYLINDER, radius=2.0, length=0.3,
             rgbaColor=[0.5,0.55,0.5,1])
pybullet.createMultiBody(0, dish_col, dish_vis, [0,-200,10.2])
```

### Protected asset markers inside dome:
Small military structure boxes at: (30,20,0), (-25,30,0), (10,-35,0), (-30,-20,0)
```python
for pos in [(30,20), (-25,30), (10,-35), (-30,-20)]:
    col = pybullet.createCollisionShape(pybullet.GEOM_BOX, halfExtents=[4,6,3])
    vis = pybullet.createVisualShape(pybullet.GEOM_BOX, halfExtents=[4,6,3],
            rgbaColor=[0.55,0.50,0.38,1])  # sand/tan military
    pybullet.createMultiBody(0, col, vis, [pos[0], pos[1], 3])
```

---

## IMPROVEMENT 3 — DRONE VISUAL QUALITY

In `sim/drone.py`:

### Interceptor drone color:
After loading URDF, apply blue tint to all links:
```python
for link_idx in range(-1, pybullet.getNumJoints(self.body_id)):
    pybullet.changeVisualShapeData(self.body_id, link_idx, 
        rgbaColor=[0.1, 0.3, 0.85, 1.0])
```

### Intruder (LoiteringMunition) color:
Apply red tint same way: rgbaColor=[0.85, 0.1, 0.1, 1.0]

### Rotor spin animation:
Every physics step, rotate rotor joints:
```python
self._rotor_angle += 0.3  # radians per step at 240Hz = ~72 rad/s ≈ 690 RPM
for joint_idx in self._rotor_joints:
    pybullet.resetJointState(self.body_id, joint_idx, self._rotor_angle)
```
For LoiteringMunition: spin in alternating directions (joint 0,2 positive, 1,3 negative)

### Proper orientation for LoiteringMunition:
The loitering munition (Shahed-style) should fly nose-first, not upright like a quad.
On spawn, rotate 90° around Y axis so fuselage is horizontal:
```python
# Initial orientation: fuselage horizontal, nose pointing toward target
orn = pybullet.getQuaternionFromEuler([0, math.pi/2, 0])
pybullet.resetBasePositionAndOrientation(self.body_id, start_pos, orn)
```
During flight, update orientation each step to match velocity vector:
```python
vel = self.get_velocity()
if np.linalg.norm(vel[:2]) > 1.0:
    yaw = math.atan2(vel[0], vel[1])
    pitch = math.atan2(-vel[2], math.sqrt(vel[0]**2 + vel[1]**2))
    orn = pybullet.getQuaternionFromEuler([0, pitch, yaw])
    pos = self.get_position()
    pybullet.resetBasePositionAndOrientation(self.body_id, pos, orn)
```

---

## IMPROVEMENT 4 — FLIGHT TRAILS

Add to `sim/physics.py` or a new `viz/trails.py`:

```python
class TrailRenderer:
    def __init__(self, color, max_segments=40):
        self.color = color
        self.max_segments = max_segments
        self._positions = []
        self._line_ids = []
    
    def update(self, pos):
        self._positions.append(pos)
        if len(self._positions) > self.max_segments + 1:
            # Remove oldest line
            if self._line_ids:
                pybullet.removeUserDebugItem(self._line_ids.pop(0))
            self._positions.pop(0)
        
        if len(self._positions) >= 2:
            # Fade color based on age
            n = len(self._line_ids)
            alpha = (n / self.max_segments)
            faded = [c * alpha for c in self.color]
            line_id = pybullet.addUserDebugLine(
                self._positions[-2], self._positions[-1],
                lineColorRGB=faded, lineWidth=2
            )
            self._line_ids.append(line_id)
    
    def clear(self):
        for lid in self._line_ids:
            pybullet.removeUserDebugItem(lid)
        self._line_ids.clear()
        self._positions.clear()
```

Instantiate in main.py:
- `intruder_trail = TrailRenderer([1.0, 0.2, 0.1], max_segments=40)`  # red
- `interceptor_trail = TrailRenderer([0.2, 0.5, 1.0], max_segments=30)`  # blue
- Update trails every 12 physics steps

---

## IMPROVEMENT 5 — DASHBOARD MILITARY AESTHETIC

In `viz/dashboard.py`, apply this color scheme throughout without changing any IPC logic or button functionality:

```python
# Color palette — apply to all figure/axes backgrounds and text
BG_DARK = '#060a0e'        # near-black blue
BG_MID = '#0d1520'         # panel background  
GRID_COLOR = '#1a2a1a'     # subtle green grid
PRIMARY = '#00ff88'        # military green
AMBER = '#ffaa00'          # warning
RED = '#ff2200'            # danger
BLUE = '#00aaff'           # interceptor
WHITE = '#e0e8e0'          # text
DIM = '#3a4a3a'            # dim text
```

Apply:
```python
fig.patch.set_facecolor(BG_DARK)
for ax in all_axes:
    ax.set_facecolor(BG_MID)
    ax.tick_params(colors=PRIMARY)
    ax.spines[:].set_color(DIM)
```

### Radar display improvements:
- Background: BG_DARK
- Range rings: DIM color, dashed, label distances ("50m", "100m", "150m", "200m")
- Dome boundary ring: PRIMARY color, solid, linewidth=2
- Intruder blip: red diamond marker (marker='D', s=80, color=RED)
- Interceptor blip: blue triangle (marker='^', s=80, color=BLUE)
- Track history: gradient trail — recent=bright, old=dim, use scatter with alpha array
- Radar sweep line: rotating line from center, updates every dashboard refresh
  - Implement with `ax.plot([0, sweep_x], [0, sweep_y], color=PRIMARY, alpha=0.4, linewidth=1)`
  - Advance sweep angle each update: `sweep_angle += 15` degrees
- Add phosphor afterglow: plot sweep trail as fading wedge using fill_between
- Status text: large, bold, monospace, color matches status (PRIMARY/AMBER/RED/CYAN)
- Title: "ANTI-DRONE DEFENSE SYSTEM" in PRIMARY, monospace font

### Status panel:
- Font: monospace throughout (`fontfamily='monospace'`)
- Threat bar: horizontal bar showing intruder proximity (0=safe, 1=at center)
  ```python
  threat = 1.0 - (dist_to_center / dome_radius)
  ax.barh(0, threat, color=RED if threat > 0.7 else AMBER if threat > 0.4 else PRIMARY)
  ```
- TTI display: large countdown in amber
- Event log: color-coded by type using axtext with bbox

### Button styling:
Apply to all existing buttons without changing their callbacks:
```python
for btn in all_buttons:
    btn.ax.set_facecolor(BG_MID)
    btn.color = BG_MID
    btn.hovercolor = '#1a2a3a'
    btn.label.set_color(PRIMARY)
    btn.label.set_fontfamily('monospace')
```

---

## IMPROVEMENT 6 — HUD POLISH

In `main.py`, update the PyBullet HUD text:

Replace the single status line with a 3-line HUD:
```python
# Line 1: Mission status
pybullet.addUserDebugText(
    f"◈ {dome_status} ◈",
    [0, 0, 215],
    textColorRGB=status_color,
    textSize=1.8,
    replaceItemUniqueId=hud_ids.get('status')
)

# Line 2: Intruder telemetry  
pybullet.addUserDebugText(
    f"INTRUDER  rng:{range_m:.0f}m  spd:{speed:.0f}m/s  alt:{alt:.0f}m",
    [0, 0, 208],
    textColorRGB=[1.0, 0.3, 0.2],
    textSize=1.2,
    replaceItemUniqueId=hud_ids.get('intruder')
)

# Line 3: Interceptor telemetry
pybullet.addUserDebugText(
    f"INTERCEPTOR  sep:{sep:.0f}m  TTI:{tti:.1f}s  spd:{int_speed:.0f}m/s",
    [0, 0, 201],
    textColorRGB=[0.2, 0.6, 1.0],
    textSize=1.2,
    replaceItemUniqueId=hud_ids.get('interceptor')
)

# Line 4: Sim controls reminder (static, set once)
pybullet.addUserDebugText(
    "SPACE=pause  1-6=speed  C=camera  R=restart  Q=quit",
    [0, 0, 194],
    textColorRGB=[0.3, 0.4, 0.3],
    textSize=0.9
)
```

Status colors:
- CLEAR: [0.0, 1.0, 0.4]
- TRACKING: [1.0, 0.8, 0.0]
- BREACH: [1.0, 0.2, 0.0]
- INTERCEPTED: [0.0, 0.9, 1.0]

---

## IMPROVEMENT 7 — MISSION DEBRIEF QUALITY

In `main.py`, improve the debrief output:

```python
def print_debrief(result, stats):
    w = 52
    print("\n" + "═"*w)
    print(f"{'MISSION DEBRIEF':^{w}}")
    print("═"*w)
    result_str = "✓ INTERCEPT SUCCESS" if result == 'intercepted' else "✗ MISSION FAILED"
    result_color = "\033[92m" if result == 'intercepted' else "\033[91m"
    print(f"{result_color}{result_str:^{w}}\033[0m")
    print("─"*w)
    print(f"  Duration          {stats['duration']:.1f}s")
    print(f"  Intruder type     {stats['intruder_type']}")
    print(f"  Attack pattern    {stats['pattern']}")
    print(f"  First detection   T+{stats['first_detect']:.1f}s at {stats['detect_range']:.0f}m")
    if stats.get('breach_time'):
        print(f"  Dome breach       T+{stats['breach_time']:.1f}s")
    print(f"  Max penetration   {stats['max_penetration']:.0f}m into dome")
    if result == 'intercepted':
        print(f"  Intercept time    T+{stats['intercept_time']:.1f}s")
        print(f"  Closest approach  {stats['closest_approach']:.1f}m")
    print(f"  ACMI file saved   missions/{stats['acmi_file']}")
    print("═"*w)
    print("  [R] Run again  [M] Main menu  [Q] Quit")
    print("═"*w + "\n")
```

---

## IMPROVEMENT 8 — SCENARIOS: ADD SWARM

Add to `scenarios.py` a swarm scenario (2 simultaneous intruders, different angles):

```python
"swarm_2": {
    "description": "Dual FPV attack — simultaneous approach from NE and NW",
    "intruder_type": "fpv_attack",
    "pattern": "direct",
    "second_intruder": {
        "type": "fpv_attack", 
        "start": (-550, 550, 120),
        "pattern": "direct"
    }
}
```

Note: only add the data structure in scenarios.py — do NOT implement multi-drone logic in main.py yet if it would risk breaking existing functionality. Flag it with a TODO comment.

---

## FINAL VERIFICATION

Run all existing tests:
```
python tests/test_drone.py
python tests/test_radar.py
python tests/test_datalink.py
python tests/test_intercept.py
```

All must pass. Then run:
```
python main.py
```

Verify checklist:
- [ ] Ground is dark military green, zero checkerboard
- [ ] Tactical grid visible, major/minor lines distinct
- [ ] Dome wireframe visible, changes color on status transitions
- [ ] Intruder flies nose-first (horizontal fuselage for Shahed), banking into turns
- [ ] Interceptor tilts to fly — not floating upright
- [ ] Rotors visually spinning on both drones
- [ ] Red trail behind intruder, blue trail behind interceptor
- [ ] HUD shows 3 lines of telemetry, color coded
- [ ] Sim runs smooth at 1x speed, no lag
- [ ] Speed 1-6 keys work
- [ ] Pause/resume works
- [ ] Camera cycling works (C key)
- [ ] Restart works (R key)
- [ ] After mission: debrief prints cleanly with ACMI file path
- [ ] missions/ folder exists with .acmi file
- [ ] ACMI file opens in Tacview without error
- [ ] Dashboard has dark military background, not default matplotlib blue/white
- [ ] Radar sweep line rotates on dashboard
- [ ] All existing buttons still work (START, PAUSE, RESET, ABORT, intruder type, pattern, pad)
- [ ] IPC between main and dashboard still works

---

## IF PYBULLET VISUAL CEILING IS HIT

If after all improvements PyBullet still looks insufficient, add this to viz/:

Install: `pip install vispy`

Create `viz/vispy_renderer.py` — a VisPy-based 3D renderer that reads drone positions from a shared dict and renders a proper scene with:
- Phong shading (ambient + diffuse + specular lighting)
- Dark military terrain with subtle fog
- Proper drone meshes loaded from .dae files
- Runs as a separate thread alongside PyBullet (which can then run headless via DIRECT)

VisPy uses OpenGL directly, is cross-platform (Mac + Windows), and produces dramatically better visuals than PyBullet's debug renderer. Only implement if explicitly needed.
