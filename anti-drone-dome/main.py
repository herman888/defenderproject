"""
Anti-Drone Dome Simulation — V3 main entry point.

Architecture
────────────
Main process / main thread : PyBullet GUI + physics loop (OpenGL owns main thread)
Child process              : Matplotlib dashboard (has its own Tkinter main thread)
IPC                        : multiprocessing.Queue

Mission loop
────────────
  main()  ──►  _wait_for_mission()  ←─── dashboard mission-select buttons
                       │
                       ▼
               _run_one_mission()
                       │
                       ▼
               dashboard debrief overlay  ←─── click scenario to continue

All mission selection, speed choice, pad-distance selection, pause/reset/abort,
and post-mission debrief are handled entirely in the dashboard window.
No blocking console prompts.

Keyboard controls (PyBullet 3-D window focus required)
──────────────────────────────────────────────────────
  SPACE   Pause / resume
  R       Restart same scenario
  1–6     Sim speed  0.25× / 0.5× / 1× / 2× / 4× / 8×
  C       Cycle camera modes
  I       Toggle intruder 3-D trail
  H       Print help to console
  Q       Return to mission select

Run:  python main.py
"""

import math
import os
import random
import sys
import time
import multiprocessing as mp

import pybullet
import pybullet_data

from sim.physics    import PhysicsWorld
from sim.drone      import Drone, LoiteringMunition
from sim.waypoints  import WaypointNavigator
from sensors.radar  import RadarNode
from comms.datalink import DataLink
from guidance.intercept import PurePursuitGuidance
from dome.killzone  import DomeKillZone
from scenarios      import INTRUDER_TYPES, ATTACK_PATTERNS, PAD_OFFSETS, get_waypoints_for_path

# ── Global constants ──────────────────────────────────────────────────
_TIMESTEP     = 1.0 / 240.0
_MAX_SIM_TIME = 240.0          # 4-minute max mission
_DOME_CENTER  = (0.0, 0.0, 0.0)
_DOME_RADIUS  = 200.0          # metres — realistic engagement range
_LOG_INTERVAL = 240            # console log every ~1 s sim time
_RADAR_RPM    = 12.0
_RADAR_OMEGA  = _RADAR_RPM / 60.0 * 2 * math.pi   # rad/s

_SPEED_MAP = {49: 0.25, 50: 0.5, 51: 1.0, 52: 2.0, 53: 4.0, 54: 8.0}
# ASCII codes: 1=49, 2=50, 3=51, 4=52, 5=53, 6=54

_R = _DOME_RADIUS   # shorthand for position calculations below

_CAM_PRESETS = [
    # 0 overview — yaw=45 faces NE so the approaching intruder is always in frame
    dict(distance=_R * 4,   yaw=45,  pitch=-28, target=[_R*0.4, _R*0.4, _R*0.1]),
    None,   # 1 chase intruder  (handled in _update_camera)
    None,   # 2 chase interceptor
    dict(distance=_R * 5,   yaw=0,   pitch=-89, target=[0, 0, 0]),          # 3 top-down
]


# ======================================================================
# Dashboard subprocess entry point  (top-level for Windows spawn)
# ======================================================================

def _dashboard_worker(state_q: mp.Queue, ctrl_q: mp.Queue, dome_radius: float):
    import time as _time
    import matplotlib.pyplot as plt
    from viz.dashboard import Dashboard, SimControl

    ctrl = SimControl()
    try:
        dash = Dashboard(dome_radius=dome_radius, sim_control=ctrl)
    except Exception as e:
        print(f"[dashboard] init failed: {e}")
        return

    while True:
        state = None
        while True:
            try:
                msg = state_q.get_nowait()
            except Exception:
                break
            if msg == "QUIT":
                dash.close()
                return
            state = msg

        if state:
            dash.update(state)
            _time.sleep(0.015)
        else:
            try:
                plt.pause(0.05)
            except Exception:
                return

        try:
            ctrl_msg = {
                "paused" : ctrl.paused,
                "stopped": ctrl.stopped,
            }
            if ctrl.restart:
                ctrl_msg["restart"] = True
                ctrl.restart = False           # consume once
            if ctrl.selected_mission is not None:
                ctrl_msg["selected_mission"] = ctrl.selected_mission
                ctrl_msg["initial_speed"]    = ctrl.selected_speed
                ctrl_msg["selected_pad"]     = ctrl.selected_pad
                ctrl_msg["selected_pattern"] = ctrl.selected_pattern
                ctrl.selected_mission = None   # consume once
            ctrl_q.put_nowait(ctrl_msg)
        except Exception:
            pass


# ======================================================================
# Helpers
# ======================================================================

def _find_joint(body: int, name: str, client: int) -> int:
    for i in range(pybullet.getNumJoints(body, physicsClientId=client)):
        info = pybullet.getJointInfo(body, i, physicsClientId=client)
        if info[1].decode() == name:
            return i
    return -1


def _load_radar_station(dome_radius: float, client: int):
    urdf = os.path.normpath(
        os.path.join(os.path.dirname(__file__), "assets", "radar_station.urdf")
    )
    body = pybullet.loadURDF(
        urdf,
        basePosition=[0.0, -dome_radius, 0.1],
        useFixedBase=1,
        physicsClientId=client,
    )
    spin_idx = _find_joint(body, "spin_joint", client)
    return body, spin_idx


def _update_camera(client: int, mode: int, i_pos, int_pos):
    preset = _CAM_PRESETS[mode]
    if preset is not None:
        pybullet.resetDebugVisualizerCamera(
            cameraDistance    = preset["distance"],
            cameraYaw         = preset["yaw"],
            cameraPitch       = preset["pitch"],
            cameraTargetPosition = preset["target"],
            physicsClientId   = client,
        )
    elif mode == 1 and i_pos:
        pybullet.resetDebugVisualizerCamera(_R*0.5, 225, -18, list(i_pos), physicsClientId=client)
    elif mode == 2 and int_pos:
        pybullet.resetDebugVisualizerCamera(_R*0.4, 225, -18, list(int_pos), physicsClientId=client)


def _update_trail(new_pos, last_pos, trail_ids, max_len, color, client):
    """Append one segment to a debug-line trail; prune oldest beyond max_len."""
    if last_pos is not None:
        try:
            lid = pybullet.addUserDebugLine(
                last_pos, list(new_pos), color,
                lineWidth=1.8, physicsClientId=client,
            )
            trail_ids.append(lid)
        except Exception:
            pass
        while len(trail_ids) > max_len:
            try:
                pybullet.removeUserDebugItem(trail_ids.pop(0), physicsClientId=client)
            except Exception:
                pass
    return list(new_pos)


def _clear_trail(trail_ids, client):
    for lid in trail_ids:
        try:
            pybullet.removeUserDebugItem(lid, physicsClientId=client)
        except Exception:
            pass
    trail_ids.clear()


def _print_help():
    print("""
╔══════════════════════════════════════════╗
║         SIM KEYBOARD CONTROLS           ║
╠══════════════════════════════════════════╣
║  SPACE   Pause / resume                 ║
║  R       Restart same scenario          ║
║  1       Speed 0.25× (slow-motion)      ║
║  2       Speed 0.5×                     ║
║  3       Speed 1× (normal)              ║
║  4       Speed 2×                       ║
║  5       Speed 4×                       ║
║  6       Speed 8× (fast-forward)        ║
║  C       Cycle camera mode              ║
║  I       Toggle intruder 3-D trail      ║
║  H       Print this help text           ║
║  Q       Quit to main menu              ║
╚══════════════════════════════════════════╝
""")


# ======================================================================
# Single mission run
# ======================================================================

def _run_one_mission(
    state_q:       mp.Queue,
    ctrl_q:        mp.Queue,
    intruder_key:  str   = "shahed136",
    pattern_key:   str   = "direct",
    initial_speed: float = 1.0,
    pad_key:       str   = "mid",
) -> dict:
    """
    Run one complete mission.  Returns a result dict.
    intruder_key : key in INTRUDER_TYPES  (shahed136 / consumer_quad / fpv_attack)
    pattern_key  : key in ATTACK_PATTERNS (direct / nap_earth / spiral)
    Termination  : INTERCEPTED / FAILURE / TIMEOUT / RESTART / QUIT / ABORTED
    """
    itype      = INTRUDER_TYPES[intruder_key]
    pattern    = ATTACK_PATTERNS[pattern_key]
    pad_offset = PAD_OFFSETS.get(pad_key, PAD_OFFSETS["mid"])
    int_start  = (0.0, -(_DOME_RADIUS + pad_offset), 5.0)
    i_start    = pattern["start"]
    target_rcs = itype["rcs"]

    sys.stdout.reconfigure(line_buffering=True) if hasattr(sys.stdout, "reconfigure") else None
    print("=" * 68)
    print(f"  INTRUDER : {itype['label']}  —  {itype['description']}")
    print(f"  PATTERN  : {pattern['label']}  |  PAD: {pad_key.upper()}  |  SPEED: {initial_speed}×")
    print("=" * 68)

    try:
        state_q.put_nowait({"type": "mission_start"})
    except Exception:
        pass

    # ── PyBullet world ────────────────────────────────────────────────
    world = PhysicsWorld(gui=True)
    world.draw_dome(_DOME_CENTER, _DOME_RADIUS, color=[0, 1, 0])

    radar_body, spin_joint = _load_radar_station(_DOME_RADIUS, world.client)
    if spin_joint >= 0:
        pybullet.setJointMotorControl2(
            radar_body, spin_joint,
            pybullet.VELOCITY_CONTROL,
            targetVelocity=_RADAR_OMEGA, force=5.0,
            physicsClientId=world.client,
        )
    pybullet.addUserDebugText(
        "RADAR STATION",
        [0, -_DOME_RADIUS, _DOME_RADIUS * 0.12],
        [0.2, 1.0, 0.2], textSize=1.2, physicsClientId=world.client,
    )

    _hx, _hy = -_DOME_RADIUS * 1.4, -_DOME_RADIUS * 1.4
    _hud_status  = pybullet.addUserDebugText("STATUS: CLEAR",    [_hx, _hy, _DOME_RADIUS*0.65], [0,1,0],   textSize=2.0, physicsClientId=world.client)
    _hud_intrudr = pybullet.addUserDebugText("INTRUDER: ---",    [_hx, _hy, _DOME_RADIUS*0.55], [1,0.3,0], textSize=1.5, physicsClientId=world.client)
    _hud_intercp = pybullet.addUserDebugText("INTERCEPTOR: ---", [_hx, _hy, _DOME_RADIUS*0.45], [0,0.8,1], textSize=1.5, physicsClientId=world.client)
    _hud_sep     = pybullet.addUserDebugText("SEP: ---",         [_hx, _hy, _DOME_RADIUS*0.35], [1,1,0],   textSize=1.5, physicsClientId=world.client)
    _hud_speed   = pybullet.addUserDebugText("SPEED: 1×",        [_hx, _hy, _DOME_RADIUS*0.25], [1,1,0],   textSize=1.3, physicsClientId=world.client)

    _int_urdf = os.path.normpath(
        os.path.join(os.path.dirname(__file__), "assets", "interceptor.urdf")
    )

    # ── Build intruder from type config ──────────────────────────────
    intruder = LoiteringMunition(
        "intruder", i_start, world.client,
        intruder_cfg=itype,
    )
    interceptor = Drone(
        "interceptor", int_start, world.client,
        color="blue",
        max_h_force=280.0, max_v_force=280.0, max_speed=60.0,
        kp=5.0, kd=2.5,
        urdf=_int_urdf if os.path.isfile(_int_urdf) else None,
        global_scaling=10.0,   # visible at 200 m dome scale
    )

    for _ in range(50):
        world.step()

    waypoints = get_waypoints_for_path(pattern["path"])
    nav     = WaypointNavigator(waypoints=waypoints)
    radar   = RadarNode(
        station_pos      = (0.0, -_DOME_RADIUS, 10.0),
        protected_center = _DOME_CENTER,
        max_range        = 1500.0,
        elev_max_deg     = 75.0,
        min_vel          = 0.8,
        noise_std        = 0.5,
    )
    broadcaster = DataLink(role="broadcast", port=14550)
    guidance    = PurePursuitGuidance()
    dome        = DomeKillZone(center=_DOME_CENTER, radius=_DOME_RADIUS)

    # ── State variables ───────────────────────────────────────────────
    sim_speed            = initial_speed
    paused               = False
    camera_mode          = 0
    show_trail           = True
    interceptor_launched = False
    interceptor_target   = None
    closest_approach     = float("inf")
    pending_events       = []
    mission_result       = None
    _last_dome_status    = "CLEAR"
    detected_at_step     = None
    response_delay_steps = int(itype["response_delay"] / _TIMESTEP)
    step                 = 0
    sim_start            = time.time()

    # Trail state
    i_trail_ids    = []
    int_trail_ids  = []
    i_last_pos     = None
    int_last_pos   = None
    icept_vec_id   = None
    flash_shown    = False

    # Wind state
    wind_force = [0.0, 0.0, 0.0]
    wind_timer = 0

    # Dashboard control cache
    dash_ctrl = {"paused": False, "stopped": False, "speed": 1}

    print("SIMULATION STARTED — press H in the PyBullet window for keyboard help\n")

    # ================================================================
    # Physics loop
    # ================================================================
    while True:

        # ── Dashboard control drain ──────────────────────────────────
        while True:
            try:
                msg = ctrl_q.get_nowait()
                dash_ctrl.update(msg)
            except Exception:
                break

        # ── Window alive check ───────────────────────────────────────
        if step % 120 == 0:
            try:
                pybullet.getConnectionInfo(world.client)
            except Exception:
                mission_result = "ABORTED"
                break

        if dash_ctrl.get("stopped"):
            mission_result = "ABORTED"
            break

        if dash_ctrl.get("restart"):
            dash_ctrl["restart"] = False
            mission_result = "RESTART"
            break

        # ── Keyboard events ───────────────────────────────────────────
        try:
            keys = pybullet.getKeyboardEvents(physicsClientId=world.client)
        except Exception:
            keys = {}

        for key, kstate in keys.items():
            if not (kstate & 4):   # KEY_WAS_TRIGGERED
                continue
            if key == 32:          # SPACE
                paused = not paused
            elif key in (82, 114): # R / r
                mission_result = "RESTART"
            elif key in (81, 113): # Q / q
                mission_result = "QUIT"
            elif key in (67, 99):  # C / c
                camera_mode = (camera_mode + 1) % len(_CAM_PRESETS)
                i_pos_now  = intruder.get_position()
                int_pos_now = interceptor.get_position() if interceptor_launched else None
                _update_camera(world.client, camera_mode, i_pos_now, int_pos_now)
            elif key in (73, 105): # I / i
                show_trail = not show_trail
                if not show_trail:
                    _clear_trail(i_trail_ids, world.client)
                    _clear_trail(int_trail_ids, world.client)
            elif key in (72, 104): # H / h
                _print_help()
            elif key in _SPEED_MAP:
                sim_speed = _SPEED_MAP[key]

        if mission_result:
            break

        if paused or dash_ctrl.get("paused"):
            time.sleep(0.05)
            continue

        sim_time = step * _TIMESTEP
        if sim_time >= _MAX_SIM_TIME:
            mission_result = "TIMEOUT"
            break

        # ── Determine physics sub-steps this iteration ────────────────
        inner_steps  = max(1, round(sim_speed))
        slow_sleep   = max(0.0, _TIMESTEP * (1.0 / sim_speed - 1.0)) if sim_speed < 1 else 0.0

        # Compute guidance force once per outer loop (position changes slowly)
        i_pos   = intruder.get_position()
        int_pos = interceptor.get_position() if interceptor_launched else None

        radar_return    = radar.scan(i_pos, target_rcs=target_rcs)
        guidance_track  = (radar_return if radar_return.get("detected")
                           else radar.get_last_track())

        # Wind update every ~2 sim seconds
        if pattern.get("wind") and (step % 480 == 0):
            wind_force = [
                random.uniform(-0.5, 0.5),
                random.uniform(-0.5, 0.5),
                0.0,
            ]

        # Guidance force
        g_force = (0.0, 0.0, 0.0)
        if interceptor_launched and guidance_track:
            t_pos = guidance_track.get("position_estimate")
            if t_pos:
                interceptor.set_target(*t_pos)
            g_force = guidance.compute_guidance(interceptor.get_state(), guidance_track)

        # ── Inner physics sub-steps ───────────────────────────────────
        for _sub in range(inner_steps):
            nav.update(intruder.get_position())
            intruder.set_target(*nav.get_current_target())
            intruder.update()

            # Wind disturbance on intruder
            if pattern.get("wind") and any(wind_force):
                try:
                    pybullet.applyExternalForce(
                        intruder._body, -1, wind_force, list(intruder.get_position()),
                        pybullet.WORLD_FRAME, physicsClientId=world.client,
                    )
                except Exception:
                    pass

            if interceptor_launched:
                if any(abs(v) > 1e-6 for v in g_force):
                    # APN guidance active: orient body toward thrust vector only.
                    # PD controller is bypassed to prevent double gravity compensation
                    # and competing force vectors that cause the interceptor to miss.
                    interceptor.set_orientation_from_thrust(list(g_force))
                    try:
                        pybullet.applyExternalForce(
                            interceptor._body, -1, list(g_force),
                            list(interceptor.get_position()),
                            pybullet.WORLD_FRAME, physicsClientId=world.client,
                        )
                    except Exception:
                        mission_result = "ABORTED"
                        break
                else:
                    # No guidance signal yet — PD hover at launch position
                    interceptor.update()

            world.step()
            step += 1

            if slow_sleep > 0:
                time.sleep(slow_sleep)

        if mission_result:
            break

        # ── Refresh positions after inner loop ────────────────────────
        i_pos   = intruder.get_position()
        int_pos = interceptor.get_position() if interceptor_launched else None

        # ── Dome status ───────────────────────────────────────────────
        dome.update_status(
            intruder_position    = i_pos,
            intruder_detected    = radar_return.get("detected", False),
            interceptor_position = int_pos,
            intercept_radius     = 12.0,   # scaled for 200 m dome
        )
        status = dome.get_status()

        if status != _last_dome_status:
            _dome_colors = {
                "CLEAR"      : [0.0, 1.0, 0.0],
                "TRACKING"   : [1.0, 1.0, 0.0],
                "BREACH"     : [1.0, 0.5, 0.0],
                "INTERCEPTED": [1.0, 0.0, 0.0],
            }
            try:
                world.draw_dome(
                    _DOME_CENTER, _DOME_RADIUS,
                    color=_dome_colors.get(status, [0, 1, 0]),
                )
            except Exception:
                mission_result = "ABORTED"
                break
            _last_dome_status = status

        # ── Detection timestamp ───────────────────────────────────────
        if status in ("TRACKING", "BREACH") and detected_at_step is None:
            detected_at_step = step

        # ── Interceptor launch (after response delay) ─────────────────
        if (not interceptor_launched and detected_at_step is not None
                and step >= detected_at_step + response_delay_steps):
            lp = list(interceptor.get_position())
            dx, dy = i_pos[0] - lp[0], i_pos[1] - lp[1]
            dh = max(math.sqrt(dx**2 + dy**2), 0.1)
            kick = [18.0 * dx / dh, 18.0 * dy / dh, 8.0]
            pybullet.resetBaseVelocity(
                interceptor._body, kick, [0, 0, 0],
                physicsClientId=world.client,
            )
            interceptor._prev_error = [0.0, 0.0, 0.0]
            interceptor_launched = True
            int_pos = interceptor.get_position()
            pending_events.append("Interceptor launched")
            print(f"INTERCEPTOR: LAUNCH  delay={scenario['interceptor_response_delay']:.1f}s")

        # ── Track closest approach ────────────────────────────────────
        if interceptor_launched and int_pos:
            sep = math.sqrt(sum((int_pos[k]-i_pos[k])**2 for k in range(3)))
            if sep < closest_approach:
                closest_approach = sep

        # ── Broadcast track every 2 sim-s ────────────────────────────
        if radar_return.get("detected") and step % 480 == 0:
            broadcaster.send_track(radar_return)

        # ── Terminal conditions ───────────────────────────────────────
        if status == "INTERCEPTED":
            if not flash_shown:
                try:
                    pybullet.addUserDebugText(
                        "★ INTERCEPT! ★", list(i_pos),
                        [1, 1, 0], textSize=3.0, lifeTime=4.0,
                        physicsClientId=world.client,
                    )
                except Exception:
                    pass
                flash_shown = True
            mission_result = "INTERCEPTED"
            time.sleep(1.5)   # linger so user sees the flash
            break

        horiz = math.sqrt(i_pos[0]**2 + i_pos[1]**2)
        if horiz < 2.0 and nav.is_complete():
            mission_result = "FAILURE"
            break

        # ── Camera update (every 24 steps ≈ 10 Hz) ────────────────────
        if step % 24 == 0:
            _update_camera(world.client, camera_mode, i_pos, int_pos)

        # ── 3-D trail update (every 5 physics steps) ──────────────────
        if show_trail and step % 5 == 0:
            i_last_pos = _update_trail(
                i_pos, i_last_pos, i_trail_ids, 30,
                [0.9, 0.12, 0.08], world.client,
            )
            if interceptor_launched and int_pos:
                int_last_pos = _update_trail(
                    int_pos, int_last_pos, int_trail_ids, 30,
                    [0.10, 0.55, 0.90], world.client,
                )

        # ── Intercept-vector line update (every 12 steps) ─────────────
        if interceptor_launched and interceptor_target and step % 12 == 0:
            int_pos_now = interceptor.get_position()
            if icept_vec_id is not None:
                try:
                    pybullet.removeUserDebugItem(icept_vec_id, physicsClientId=world.client)
                except Exception:
                    pass
            try:
                icept_vec_id = pybullet.addUserDebugLine(
                    list(int_pos_now), list(interceptor_target),
                    [1.0, 0.80, 0.0], lineWidth=1.5,
                    physicsClientId=world.client,
                )
            except Exception:
                pass

        if guidance_track:
            interceptor_target = guidance_track.get("position_estimate")

        # ── PyBullet HUD update (every 48 steps ≈ 5 Hz) ──────────────
        if step % 48 == 0:
            sc = {
                "CLEAR": [0,1,0], "TRACKING": [1,1,0],
                "BREACH": [1,0.5,0], "INTERCEPTED": [1,0,0],
            }.get(status, [1,1,1])
            paused_tag = " [PAUSED]" if (paused or dash_ctrl.get("paused")) else ""
            try:
                _hud_speed = pybullet.addUserDebugText(
                    f"SPEED: {sim_speed:.2g}x{paused_tag}",
                    [-14,-14,4], [1,1,0], textSize=1.3,
                    replaceItemUniqueId=_hud_speed,
                    physicsClientId=world.client,
                )
                _hud_status = pybullet.addUserDebugText(
                    f"STATUS: {status}", [-14,-14,12], sc, textSize=2.0,
                    replaceItemUniqueId=_hud_status,
                    physicsClientId=world.client,
                )
                rng_str = f"{radar_return.get('range',0):.1f}m" if radar_return.get("detected") else "---"
                _hud_intrudr = pybullet.addUserDebugText(
                    f"INTRUDER  ({i_pos[0]:.1f},{i_pos[1]:.1f},{i_pos[2]:.1f})  rng:{rng_str}",
                    [-14,-14,10], [1,0.3,0], textSize=1.5,
                    replaceItemUniqueId=_hud_intrudr,
                    physicsClientId=world.client,
                )
                if interceptor_launched and int_pos:
                    d   = math.sqrt(sum((int_pos[k]-i_pos[k])**2 for k in range(3)))
                    tti = guidance.time_to_intercept(interceptor.get_state(), guidance_track) \
                          if guidance_track else float("inf")
                    tti_s = f"{tti:.1f}s" if tti < 999 else "---"
                    _hud_intercp = pybullet.addUserDebugText(
                        f"INTERCEPTOR ({int_pos[0]:.1f},{int_pos[1]:.1f},{int_pos[2]:.1f})",
                        [-14,-14,8], [0,0.8,1], textSize=1.5,
                        replaceItemUniqueId=_hud_intercp,
                        physicsClientId=world.client,
                    )
                    _hud_sep = pybullet.addUserDebugText(
                        f"SEP: {d:.1f}m  TTI: {tti_s}",
                        [-14,-14,6], [1,1,0], textSize=1.5,
                        replaceItemUniqueId=_hud_sep,
                        physicsClientId=world.client,
                    )
                else:
                    _hud_intercp = pybullet.addUserDebugText(
                        "INTERCEPTOR: on pad — awaiting launch",
                        [-14,-14,8], [0,0.8,1], textSize=1.5,
                        replaceItemUniqueId=_hud_intercp,
                        physicsClientId=world.client,
                    )
            except Exception:
                pass

            # Console log
            if step % _LOG_INTERVAL == 0:
                rng  = radar_return.get("range", 0.0) if radar_return.get("detected") else 0.0
                sep  = "--"
                if interceptor_launched and int_pos:
                    sep = f"{math.sqrt(sum((int_pos[k]-i_pos[k])**2 for k in range(3))):.1f}m"
                print(
                    f"T+{sim_time:5.1f}s  INTR ({i_pos[0]:.1f},{i_pos[1]:.1f},{i_pos[2]:.1f})"
                    f"  RADAR {rng:.1f}m  {status:10s}  INT {sep}"
                )

        # ── Dashboard state push ──────────────────────────────────────
        i_v   = intruder.get_velocity()
        int_v = interceptor.get_velocity() if interceptor_launched else (0, 0, 0)
        tti   = float("inf")
        if interceptor_launched and radar_return.get("detected") and guidance_track:
            tti = guidance.time_to_intercept(interceptor.get_state(), guidance_track)

        try:
            state_q.put_nowait({
                "dome_status"        : status,
                "intruder_pos"       : i_pos,
                "interceptor_pos"    : int_pos,
                "radar_return"       : radar_return,
                "radar_station"      : radar.station_pos.tolist(),
                "predicted_intercept": interceptor_target,
                "intruder_speed"     : math.sqrt(sum(v**2 for v in i_v)),
                "interceptor_speed"  : math.sqrt(sum(v**2 for v in int_v)),
                "tti"                : tti,
                "track_confidence"   : radar.track_confidence(),
                "last_detection_time": radar.last_detection_time,
                "events"             : pending_events,
                "mission_time"       : sim_time,
                "sim_speed"          : sim_speed,
            })
        except Exception:
            pass
        pending_events = []

    # ── Cleanup ───────────────────────────────────────────────────────
    _clear_trail(i_trail_ids,   world.client)
    _clear_trail(int_trail_ids, world.client)

    try:
        pybullet.disconnect(world.client)
    except Exception:
        pass
    broadcaster.close()

    total_sim = step * _TIMESTEP
    return {
        "result"         : mission_result,
        "scenario"       : scenario_key,
        "sim_time"       : total_sim,
        "first_detection": dome.first_detection_time,
        "breach_time"    : dome.breach_time,
        "intercept_time" : dome.intercept_time,
        "closest_approach": closest_approach,
        "max_penetration": dome.max_penetration_depth(),
        "sim_start"      : sim_start,
    }


# ======================================================================
# Controls banner (console only — all UX is in the dashboard)
# ======================================================================

def _print_controls():
    print("""
╔══════════════════════════════════════════════════════════╗
║         ANTI-DRONE DOME  V3  —  KEYBOARD CONTROLS       ║
╠══════════════════════════════════════════════════════════╣
║  PyBullet 3-D window must have focus for keys to work   ║
╠══════════════════════════════════════════════════════════╣
║  SPACE   Pause / resume                                 ║
║  R       Restart same scenario                          ║
║  1–6     Sim speed  0.25× / 0.5× / 1× / 2× / 4× / 8×  ║
║  C       Cycle camera  (overview/chase/top-down)        ║
║  I       Toggle 3-D trail                               ║
║  H       Print this help                                ║
║  Q       Return to mission select                       ║
╠══════════════════════════════════════════════════════════╣
║  All mission select, pad, speed, pause, reset, abort    ║
║  and debrief are handled in the DASHBOARD window.       ║
╚══════════════════════════════════════════════════════════╝
""")


# ======================================================================
# Entry point
# ======================================================================

def _wait_for_mission(state_q: mp.Queue, ctrl_q: mp.Queue, dash_proc) -> tuple:
    """
    Poll until the dashboard sends a mission selection.
    Returns (scenario_key, initial_speed, pad_key) or ('quit', 1.0, 'mid').
    """
    try:
        state_q.put_nowait({"type": "show_menu"})
    except Exception:
        pass

    print("\n[SIM] Waiting for mission selection in the Dashboard window …")

    while True:
        if not dash_proc.is_alive():
            print("[SIM] Dashboard closed — quitting.")
            return ("quit", "direct", 1.0, "mid")

        while True:
            try:
                msg = ctrl_q.get_nowait()
            except Exception:
                break
            intruder = msg.get("selected_mission")
            if intruder:
                speed   = float(msg.get("initial_speed", 1.0))
                pad     = msg.get("selected_pad", "mid")
                pattern = msg.get("selected_pattern", "direct")
                print(f"[SIM] ▶ {intruder.upper()}  pattern={pattern}  pad={pad}  speed={speed}×")
                return (intruder, pattern, speed, pad)

        time.sleep(0.10)


def main():
    mp.freeze_support()

    state_q = mp.Queue(maxsize=2)
    ctrl_q  = mp.Queue(maxsize=20)

    dash_proc = mp.Process(
        target=_dashboard_worker,
        args=(state_q, ctrl_q, _DOME_RADIUS),
        daemon=True,
        name="dashboard",
    )
    dash_proc.start()

    _print_controls()

    current_intruder = None
    current_pattern  = "direct"
    chosen_speed     = 1.0
    chosen_pad       = "mid"

    try:
        while True:
            if current_intruder is None:
                current_intruder, current_pattern, chosen_speed, chosen_pad = \
                    _wait_for_mission(state_q, ctrl_q, dash_proc)

            if current_intruder == "quit":
                break

            result = _run_one_mission(
                state_q, ctrl_q,
                intruder_key  = current_intruder,
                pattern_key   = current_pattern,
                initial_speed = chosen_speed,
                pad_key       = chosen_pad,
            )
            mr = result["result"]

            if mr == "QUIT":
                current_intruder = None
                continue

            if mr == "RESTART":
                continue

            if mr == "ABORTED":
                current_intruder = None
                continue

            try:
                state_q.put_nowait({
                    "type":             "debrief",
                    "result":           mr,
                    "sim_time":         result["sim_time"],
                    "closest_approach": result.get("closest_approach", float("inf")),
                    "intruder":         current_intruder,
                })
            except Exception:
                pass

            current_intruder, current_pattern, chosen_speed, chosen_pad = \
                _wait_for_mission(state_q, ctrl_q, dash_proc)

    except KeyboardInterrupt:
        print("\n[SIM] Interrupted by user.")
    except Exception as e:
        import traceback
        print(f"\n[SIM] Crash: {e}")
        traceback.print_exc()
    finally:
        try:
            state_q.put_nowait("QUIT")
        except Exception:
            pass
        dash_proc.join(timeout=4)
        if dash_proc.is_alive():
            dash_proc.terminate()


if __name__ == "__main__":
    main()
