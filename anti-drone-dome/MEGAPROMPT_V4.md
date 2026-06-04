# Anti-Drone Dome Simulation — Megaprompt V4
# VisPy 3D Renderer — Replace PyBullet debug window
# DO NOT touch physics, guidance, radar, IPC, or dashboard
# PyBullet stays as physics engine — DIRECT mode only when VisPy is active

---

## CRITICAL RULES

- Read EVERY existing file fully before touching anything
- Do NOT change: PyBullet physics, APN guidance, Kalman tracker, radar model, MAVLink datalink
- Do NOT change: multiprocessing architecture, IPC queue structure, dashboard.py
- Do NOT change: dome radius 200m, timestep 1/240s, any physics constants
- PyBullet runs in DIRECT mode (no window) when VisPy renderer is active
- VisPy renderer reads positions from a shared dict updated by the physics loop
- All existing keyboard controls must still work (remap to VisPy window)
- Test after every major step — fix errors before moving on
- If something breaks, revert that specific change only

---

## ARCHITECTURE

```
main.py (physics loop)
  └── PyBullet DIRECT (physics only, no window)
  └── shared_state dict  ←── updated every frame
  └── VisPy window thread  ←── reads shared_state, renders 3D scene
  └── Dashboard subprocess (unchanged)
  └── ACMIWriter (unchanged)
```

The VisPy window runs in the main thread (OpenGL requirement).
PyBullet physics runs in a background thread.
shared_state uses threading.Lock for safe reads/writes.

---

## STEP 1 — INSTALL & SCAFFOLD

Install:
```
pip install vispy PyOpenGL PyOpenGL_accelerate
```

Create `viz/vispy_renderer.py` — the entire VisPy renderer lives here.

---

## STEP 2 — VISPY RENDERER CLASS

```python
"""
VisPy-based 3D renderer for anti-drone simulation.
Replaces PyBullet's debug renderer. PyBullet runs DIRECT (headless).
"""
```

### Canvas setup

```python
from vispy import app, scene
from vispy.scene import visuals

class SimRenderer:
    def __init__(self, shared_state: dict, state_lock, dome_radius=200.0):
        self.canvas = scene.SceneCanvas(
            title="ANTI-DRONE DEFENSE — 3D VIEW",
            size=(1280, 720),
            bgcolor="#060a0e",   # near-black military blue
            keys="interactive",
            show=True,
        )
        self.view = self.canvas.central_widget.add_view()
        self.view.camera = scene.TurntableCamera(
            elevation=30, azimuth=45,
            distance=dome_radius * 5,
            fov=60,
        )
```

### Ground plane

Draw a large flat quad (1600×1600m) with dark military green color:
```python
# Ground — dark military terrain
ground = visuals.Plane(
    width=1600, height=1600,
    width_segments=32, height_segments=32,
    color=(0.10, 0.13, 0.10, 1.0),
    parent=self.view.scene,
)
ground.transform = scene.transforms.STTransform(translate=(0, 0, 0))
```

Add a subtle grid overlay using `visuals.GridLines`:
```python
grid = visuals.GridLines(color=(0.20, 0.28, 0.20, 0.6), parent=self.view.scene)
```

### Dome hemisphere wireframe

Draw the dome as a wireframe hemisphere using `visuals.Line` with 64-point lat/lon circles:
- 8 latitude rings from ground level to apex
- 12 longitude lines from ground to apex
- Color: `(0.0, 0.8, 0.2, 0.7)` — bright military green
- Store all line visuals in `self._dome_lines`
- Method `update_dome_color(status)`: swap color based on status
  - CLEAR:       `(0.0, 0.7, 0.15, 0.7)`
  - TRACKING:    `(0.9, 0.75, 0.0, 0.8)`
  - BREACH:      `(1.0, 0.15, 0.05, 0.9)`
  - INTERCEPTED: `(0.0, 0.85, 1.0, 1.0)`

### Range rings on ground

Draw 4 flat circles on the ground plane at z=0.1:
- 50m:  color `(0.15, 0.25, 0.15, 0.5)`
- 100m: color `(0.15, 0.30, 0.15, 0.6)`
- 200m: color `(0.0,  0.65, 0.15, 0.9)` — dome boundary, bright
- 400m: color `(0.15, 0.22, 0.15, 0.4)`

Label each ring with `visuals.Text`:
- Font: monospace, color matches ring color
- Position: at 45° on each ring, slightly above ground

### Cardinal markers

`visuals.Text` at N/S/E/W positions just outside 250m:
- Text: "N", "S", "E", "W"
- Color: `(0.45, 0.60, 0.45, 0.8)`
- Font size: 16pt monospace

### Protected asset markers

4 tan/sand colored box markers inside dome at:
`(30,20,0)`, `(-25,30,0)`, `(10,-35,0)`, `(-30,-20,0)`

Use `visuals.Box` with color `(0.55, 0.50, 0.38, 1.0)`.

### Intruder visual

```python
# Red diamond marker — use a sphere or custom marker
self._intruder_marker = visuals.Markers(parent=self.view.scene)
self._intruder_marker.set_data(
    pos=np.array([[0, 0, 220]]),
    face_color=(1.0, 0.15, 0.05, 1.0),
    edge_color=(1.0, 0.5, 0.3, 1.0),
    size=14,
    symbol="diamond",
)
```

Trail: `visuals.Line` with 60 points, color fades from bright red at head to transparent at tail.

Label: `visuals.Text` "INTRUDER" in red, offset from marker position.

### Interceptor visual

Same pattern as intruder but:
- Color: `(0.1, 0.5, 1.0, 1.0)` — cyan-blue
- Symbol: "triangle_up"
- Label: "INTERCEPTOR" in cyan

### Predicted intercept point

Amber `visuals.Markers` with symbol "x", size=16, color `(1.0, 0.7, 0.0, 1.0)`.
Dashed amber `visuals.Line` from interceptor to predicted point.

### Radar station

A thin cylinder (mast) + flat disk (dish) at `(0, -200, 0)` using `visuals.Box` shapes.
Color: `(0.4, 0.42, 0.45, 1.0)` — metal gray.

### HUD overlay (2D on top of 3D)

Use a second `ViewBox` in 2D mode pinned to the top-left of the canvas:
```python
self._hud_view = self.canvas.central_widget.add_view()
self._hud_view.camera = scene.PanZoomCamera(aspect=1)
self._hud_view.camera.set_range(x=(0, 1280), y=(0, 720))
```

Draw these HUD elements as `visuals.Text`:
- Top-left status: `"● STATUS: CLEAR"` — large, bold, military green
- Below: `"INTRUDER  rng:---m  spd:---m/s  alt:---m"` — red
- Below: `"INTERCEPTOR  sep:---m  TTI:---s"` — cyan
- Bottom bar: `"SPACE=pause  C=camera  R=restart  Q=quit"` — dim green
- Top-right: mission timer `"T+0.0s  1.0×"` — white monospace

Update HUD text every frame from shared_state.

### Threat bar (HUD)

A `visuals.Rectangle` in the HUD layer:
- Background: `(0.08, 0.10, 0.08, 0.8)` — dark panel
- Fill bar: width proportional to threat level (0=safe, 1=at center)
  - Color: green → amber → red based on threat
- Label: "THREAT" in dim green

---

## STEP 3 — UPDATE LOOP

```python
def update(self, ev):
    """Called by VisPy timer at ~60 Hz."""
    with self._lock:
        state = dict(self._shared_state)  # snapshot

    intruder_pos    = state.get("intruder_pos")
    interceptor_pos = state.get("interceptor_pos")
    status          = state.get("dome_status", "CLEAR")
    predicted_ic    = state.get("predicted_intercept")

    # Update intruder position + trail
    if intruder_pos:
        self._intruder_marker.set_data(pos=np.array([intruder_pos]))
        self._update_trail(self._intruder_trail_pts, intruder_pos,
                           self._intruder_trail_line, (1.0, 0.15, 0.05))

    # Update interceptor position + trail
    if interceptor_pos:
        self._intercept_marker.set_data(pos=np.array([interceptor_pos]))
        self._update_trail(self._intercept_trail_pts, interceptor_pos,
                           self._intercept_trail_line, (0.1, 0.5, 1.0))

    # Update dome color on status change
    if status != self._last_status:
        self.update_dome_color(status)
        self._last_status = status

    # Update HUD text
    self._refresh_hud(state)

    self.canvas.update()
```

Trail fade helper:
```python
def _update_trail(self, pts_list, new_pos, line_visual, base_color, max_pts=60):
    pts_list.append(list(new_pos))
    if len(pts_list) > max_pts:
        pts_list.pop(0)
    if len(pts_list) >= 2:
        n = len(pts_list)
        alphas = np.linspace(0.05, 1.0, n)
        colors = np.array([[*base_color, a] for a in alphas])
        line_visual.set_data(pos=np.array(pts_list), color=colors)
```

---

## STEP 4 — KEYBOARD HANDLING

In the VisPy canvas `on_key_press` event:
```python
@self.canvas.events.key_press.connect
def on_key(event):
    key = event.key.name
    if key == "Space":
        shared_state["paused"] = not shared_state.get("paused", False)
    elif key == "R":
        shared_state["restart"] = True
    elif key == "Q":
        shared_state["quit"] = True
    elif key == "C":
        # cycle camera presets
        self._cycle_camera()
    elif key in ("1","2","3","4","5","6"):
        speeds = {"1":0.25,"2":0.5,"3":1.0,"4":2.0,"5":4.0,"6":8.0}
        shared_state["sim_speed"] = speeds[key]
```

Camera presets (cycle with C):
- Overview: elevation=30, azimuth=45, distance=dome_radius*5
- Top-down: elevation=89, azimuth=0, distance=dome_radius*4
- Chase intruder: elevation=15, azimuth follows intruder bearing
- Side view: elevation=10, azimuth=90, distance=dome_radius*3

---

## STEP 5 — INTEGRATE INTO main.py

### Add launch flag

Add `--no-vispy` CLI flag to keep PyBullet GUI as fallback:
```python
import argparse
parser = argparse.ArgumentParser()
parser.add_argument("--no-vispy", action="store_true", help="Use PyBullet GUI renderer")
args = parser.parse_args()
USE_VISPY = not args.no_vispy
```

### Physics thread

When `USE_VISPY=True`, run physics in a background thread:
```python
import threading

shared_state = {}
state_lock   = threading.Lock()

def physics_thread_fn():
    # existing _run_one_mission logic here
    # replace all pybullet GUI calls with shared_state updates
    # PyBullet connects in DIRECT mode
    pass

phys_thread = threading.Thread(target=physics_thread_fn, daemon=True)
phys_thread.start()
```

### PyBullet mode switch

In `_run_one_mission`, change:
```python
world = PhysicsWorld(gui=not USE_VISPY)
```

Remove all `pybullet.addUserDebugText` HUD calls when `USE_VISPY=True` — VisPy handles HUD.
Remove all `_update_trail` debug line calls when `USE_VISPY=True` — VisPy handles trails.

### shared_state updates

Every 48 physics steps, write to shared_state:
```python
with state_lock:
    shared_state.update({
        "dome_status":         status,
        "intruder_pos":        list(i_pos),
        "interceptor_pos":     list(int_pos) if int_pos else None,
        "predicted_intercept": interceptor_target,
        "intruder_speed":      i_spd,
        "interceptor_speed":   int_spd,
        "tti":                 tti,
        "mission_time":        sim_time,
        "sim_speed":           sim_speed,
        "paused":              paused,
    })
```

Read control signals back from shared_state:
```python
with state_lock:
    if shared_state.get("restart"):
        shared_state["restart"] = False
        mission_result = "RESTART"
    if shared_state.get("quit"):
        mission_result = "QUIT"
    paused    = shared_state.get("paused", paused)
    sim_speed = shared_state.get("sim_speed", sim_speed)
```

### VisPy main loop

In `main()`, after starting physics thread:
```python
if USE_VISPY:
    renderer = SimRenderer(shared_state, state_lock, dome_radius=_DOME_RADIUS)
    timer = app.Timer(interval=1/60, connect=renderer.update, start=True)
    app.run()  # blocks — OpenGL owns main thread
else:
    # existing PyBullet GUI path
    _run_one_mission(...)
```

---

## STEP 6 — VISUAL POLISH

### Debrief overlay

When `shared_state["debrief"]` is set, show a centered semi-transparent panel in the HUD:
```python
# Dark overlay rectangle
# Large result text: "★ INTERCEPTED ★" or "✗ MISSION FAILED"
# Stats: duration, closest approach, ACMI file path
# Color: green for INTERCEPTED, red for FAILURE, amber for TIMEOUT
```

### Intercept flash

When status transitions to INTERCEPTED:
- Flash dome color cyan 3 times at 0.3s intervals
- Show "★ INTERCEPT! ★" text at intercept position for 3 seconds
- Use `vispy.app.Timer` for timed events

### Radar sweep

Rotating sweep line from radar station position:
- Thin bright green line, full dome radius length
- Rotates at _RADAR_OMEGA rad/s
- Fading phosphor afterglow: 6 progressively dimmer/wider lines behind it

---

## STEP 7 — FINAL VERIFICATION

Run:
```
python main.py
```

Verify:
- [ ] VisPy window opens with dark military scene
- [ ] Dark ground with grid visible
- [ ] Dome wireframe visible, glowing green
- [ ] Range rings on ground with labels
- [ ] Cardinal markers N/S/E/W
- [ ] Protected asset boxes inside dome
- [ ] HUD overlay shows status/telemetry
- [ ] Physics runs — intruder moves correctly
- [ ] Red trail behind intruder, fades correctly
- [ ] Interceptor launches and blue trail appears
- [ ] Dome color changes: green → amber → red → cyan
- [ ] Camera cycles with C key
- [ ] Pause/resume with SPACE
- [ ] Speed keys 1-6 work
- [ ] Dashboard window still works alongside VisPy
- [ ] ACMI export still works
- [ ] Fallback: `python main.py --no-vispy` uses original PyBullet GUI

Run all tests:
```
python tests/test_drone.py
python tests/test_radar.py
python tests/test_datalink.py
python tests/test_intercept.py
```

All must pass.
