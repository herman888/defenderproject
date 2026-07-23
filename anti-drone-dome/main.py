"""
Anti-Drone Dome Simulation — V3 main entry point.

Architecture
────────────
Main process / main thread : PyBullet GUI + physics loop (OpenGL owns main thread)
Child process              : PyQtGraph dashboard (own Qt event loop)
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
Click  ▶ START  there to open the PyBullet 3-D view (it does not open until then).
No blocking console prompts.

Keyboard controls (PyBullet 3-D window focus required)
──────────────────────────────────────────────────────
  SPACE   Pause / resume
  R       Restart same scenario
  0–6     Sim speed  0.1× / 0.25× / 0.5× / 1× / 2× / 4× / 8×
  C       Cycle camera modes
  T       Quick-toggle intruder tracking
  + / =   Zoom 3-D view in
  -       Zoom 3-D view out
  I       Toggle intruder 3-D trail
  H       Print help to console
  Q       Return to mission select

Also: PyBullet **User Parameters** (right panel) — + / − zoom sliders; and the
radar dashboard strip — same camera nudge as the keys.

Run:  python main.py
"""

import argparse
import json
import math
import os
import random
import sys
import time
import threading
import multiprocessing as mp

import pybullet
import pybullet_data

USE_VISPY   = False   # set to True by --no-vispy absence in main()
USE_SITL    = False   # set to True by --sitl flag in main()
ML_MODEL    = None
ML_ABSOLUTE_ACTIONS = False
USE_CAMERA_PERCEPTION = False
CAMERA_MODEL = None
ML_DEVICE = "auto"
RENDER_BACKEND = "auto"
INTEGRATED_C2 = True
TELEMETRY_UDP = None
TELEMETRY_RECORD = None
HARDWARE_PROFILE = None
MISSION_RECORD_DIR = os.path.join("missions", "runs")
_SITL_ADDR  = "127.0.0.1"
_SITL_PORT  = 14560
# Setpoint send interval in physics steps (240 Hz ÷ 20 Hz = every 12 steps)
_SITL_SEND_INTERVAL = 12

from sim.physics         import PhysicsWorld
from sim.camera_debug_ui import CameraZoomDebugUi
from sim.drone      import Drone, LoiteringMunition
from sim.waypoints  import WaypointNavigator
from sensors.radar  import RadarNode
from sensors.camera import RenderedCameraSensor
from sensors.fusion import TrackFusion
from comms.datalink    import DataLink
from comms.sitl_bridge import SITLBridge
from guidance.intercept import PurePursuitGuidance
from guidance.setpoint  import GuidanceSetpoint, enu_to_ned
from config             import PAD_ALTITUDE_M, PAD_GROUND_Z_M, TAKEOFF_TOL_M
from dome.killzone  import DomeKillZone
from scenarios      import (INTRUDER_TYPES, ATTACK_PATTERNS, PAD_OFFSETS,
                            get_environment_for_pattern, get_site_config,
                            get_waypoints_for_path)
from viz.acmi_writer import ACMIWriter
from integration.tactical_stream import TacticalUdpPublisher, UdpEndpoint
from integration.mission_record import MissionRecorder
from hardware.profile import load_hardware_profile

# ── Global constants ──────────────────────────────────────────────────
_TIMESTEP     = 1.0 / 240.0
_MAX_SIM_TIME = 240.0          # 4-minute max mission
_DOME_CENTER  = (0.0, 0.0, 0.0)
_DOME_RADIUS  = 200.0          # metres — realistic engagement range
_LOG_INTERVAL = 240            # console log every ~1 s sim time
_RADAR_RPM    = 12.0
_RADAR_OMEGA  = _RADAR_RPM / 60.0 * 2 * math.pi   # rad/s

_SPEED_MAP = {48: 0.1, 49: 0.25, 50: 0.5, 51: 1.0, 52: 2.0, 53: 4.0, 54: 8.0}
# ASCII codes: 0=48, 1=49, 2=50, 3=51, 4=52, 5=53, 6=54

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

def _coalesce_dashboard_messages(messages):
    """Keep ordered lifecycle messages, newest telemetry, and every event."""
    lifecycle = []
    latest = None
    events = []
    for message in messages:
        if isinstance(message, dict) and message.get("type"):
            lifecycle.append(message)
            continue
        if isinstance(message, dict):
            latest = message
            events.extend(message.get("events", []) or [])
    if latest is not None:
        latest = dict(latest)
        latest["events"] = events
    return lifecycle, latest


def _dashboard_worker(
    state_q: mp.Queue,
    ctrl_q: mp.Queue,
    dome_radius: float,
    capture_dir: str = None,
):
    """
    Dashboard child process — Qt event loop driving a PyQtGraph Dashboard.

    State queue is drained by a 16 ms QTimer (so we always render the freshest
    snapshot, never a backlog). A 50 ms QTimer publishes the SimControl snapshot
    back to the main process. A literal "QUIT" sentinel on state_q closes the app.
    """
    from viz.dashboard import Dashboard, SimControl
    from pyqtgraph.Qt import QtCore, QtWidgets

    app  = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    ctrl = SimControl()
    try:
        dash = Dashboard(dome_radius=dome_radius, sim_control=ctrl)
    except Exception as e:
        print(f"[dashboard] init failed: {e}")
        return

    capture_thresholds = (3.0, 8.0, 13.0)
    captured_thresholds = set()

    def _capture_evidence(latest, threshold):
        os.makedirs(capture_dir, exist_ok=True)
        stem = f"dashboard_t{int(threshold):03d}"
        dash.grab().save(os.path.join(capture_dir, f"{stem}.png"))
        history = dash.altitude_history()
        evidence = {
            "capture_threshold_s": threshold,
            "mission_time_s": float(latest.get("mission_time", 0.0)),
            "status": latest.get("dome_status"),
            "intruder_altitude_m": (
                float(latest["intruder_pos"][2])
                if latest.get("intruder_pos") else None
            ),
            "interceptor_altitude_m": (
                float(latest["interceptor_pos"][2])
                if latest.get("interceptor_pos") else None
            ),
            "predicted_intercept_enu_m": latest.get("predicted_intercept"),
            "real_time_factor": float(latest.get("real_time_factor", 0.0)),
            "render_backend": latest.get("render_backend"),
            "terrain_source": latest.get("terrain_source"),
            "intruder_altitude_history": history["intruder"],
            "interceptor_altitude_history": history["interceptor"],
            "event_log": dash._log_text.text(),
        }
        with open(os.path.join(capture_dir, f"{stem}.json"), "w", encoding="utf-8") as handle:
            json.dump(evidence, handle, indent=2)

    # ── State drain: preserve lifecycle and events; coalesce telemetry only ─
    def _drain_state():
        messages = []
        while True:
            try:
                msg = state_q.get_nowait()
            except Exception:
                break
            if msg == "QUIT":
                try:
                    dash.close()
                except Exception:
                    pass
                app.quit()
                return
            messages.append(msg)
        lifecycle, latest = _coalesce_dashboard_messages(messages)
        for message in lifecycle:
            try:
                dash.update(message)
            except Exception as exc:
                print(f"[dashboard] lifecycle update failed: {exc}")
        if latest is not None:
            try:
                dash.update(latest)
                if capture_dir:
                    sim_time = float(latest.get("mission_time", 0.0))
                    for threshold in capture_thresholds:
                        if (
                            threshold not in captured_thresholds
                            and sim_time >= threshold
                        ):
                            _capture_evidence(latest, threshold)
                            captured_thresholds.add(threshold)
            except Exception as exc:
                print(f"[dashboard] update failed: {exc}")

    # ── Control publish: SimControl → ctrl_q ──────────────────────────────
    def _publish_ctrl():
        msg = {
            "paused": ctrl.paused,
            "stopped": ctrl.stopped,
            "runtime_speed": ctrl.runtime_speed,
            "radar_failure": ctrl.radar_failure,
            "camera_failure": ctrl.camera_failure,
            "actuator_failure": ctrl.actuator_failure,
        }
        if ctrl.restart:
            msg["restart"] = True
            ctrl.restart = False
        if ctrl.selected_mission is not None:
            msg["selected_mission"] = ctrl.selected_mission
            msg["initial_speed"]    = ctrl.selected_speed
            msg["selected_pad"]     = ctrl.selected_pad
            msg["selected_pattern"] = ctrl.selected_pattern
            ctrl.selected_mission = None
        if getattr(ctrl, "camera_zoom_pending", None):
            msg["camera_zoom"] = ctrl.camera_zoom_pending
            ctrl.camera_zoom_pending = None
        if getattr(ctrl, "camera_view_pending", None):
            msg["camera_view"] = ctrl.camera_view_pending
            ctrl.camera_view_pending = None
        try:
            ctrl_q.put_nowait(msg)
        except Exception:
            pass

    state_timer = QtCore.QTimer()
    state_timer.timeout.connect(_drain_state)
    state_timer.start(16)            # ~60 Hz drain

    ctrl_timer = QtCore.QTimer()
    ctrl_timer.timeout.connect(_publish_ctrl)
    ctrl_timer.start(50)             # 20 Hz control publish

    app.exec()


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


def _apply_pybullet_zoom(client: int, direction: str) -> None:
    """Nudge debug-visualizer camera distance (free-roam); clamp for 200 m dome."""
    try:
        ret = pybullet.getDebugVisualizerCamera(physicsClientId=client)
    except Exception:
        return
    if len(ret) < 12:
        return
    yaw, pitch, dist, target = float(ret[8]), float(ret[9]), float(ret[10]), list(ret[11])
    factor = 0.90 if direction == "in" else 1.11
    newd = max(120.0, min(9000.0, dist * factor))
    try:
        pybullet.resetDebugVisualizerCamera(
            cameraDistance=newd,
            cameraYaw=yaw,
            cameraPitch=pitch,
            cameraTargetPosition=target,
            physicsClientId=client,
        )
    except Exception:
        pass


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
║  0       Speed 0.1× (ultra slow-motion) ║
║  1       Speed 0.25× (slow-motion)      ║
║  2       Speed 0.5×                     ║
║  3       Speed 1× (normal)              ║
║  4       Speed 2×                       ║
║  5       Speed 4×                       ║
║  6       Speed 8× (fast-forward)        ║
║  C       Cycle camera mode              ║
║  + / =   Zoom 3-D view in (closer)      ║
║  -       Zoom 3-D view out (farther)    ║
║  PyBullet right panel: +/− ZOOM sliders ║
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
    shared_state:  dict  = None,
    state_lock             = None,
) -> dict:
    """
    Run one complete mission.  Returns a result dict.
    intruder_key : key in INTRUDER_TYPES  (shahed136 / consumer_quad / fpv_attack)
    pattern_key  : key in ATTACK_PATTERNS (direct / nap_earth / spiral)
    Termination  : INTERCEPTED / FAILURE / TIMEOUT / RESTART / QUIT / ABORTED
    """
    itype      = INTRUDER_TYPES[intruder_key]
    pattern    = ATTACK_PATTERNS[pattern_key]
    environment = get_environment_for_pattern(pattern_key)
    pad_offset = PAD_OFFSETS.get(pad_key, PAD_OFFSETS["mid"])
    int_start  = (0.0, 0.0, PAD_GROUND_Z_M)
    # Pad position in LOCAL_NED for the placeholder FC's takeoff/loiter
    # setpoint. ENU (0, 0, PAD_ALTITUDE_M)  →  NED (0, 0, -PAD_ALTITUDE_M).
    pad_position_ned = (0.0, 0.0, -PAD_ALTITUDE_M)
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
    site_config = get_site_config()
    pybullet_gui = not USE_VISPY and not INTEGRATED_C2
    world = PhysicsWorld(
        gui=pybullet_gui,
        site_config=site_config,
        render_backend=RENDER_BACKEND,
    )
    if pybullet_gui:
        world.draw_dome(_DOME_CENTER, _DOME_RADIUS, color=[0.0, 0.6, 0.1])

    # Publish intruder type immediately so renderer can build the right mesh
    if USE_VISPY and shared_state is not None:
        with state_lock:
            shared_state["intruder_key"] = intruder_key
            shared_state.pop("intruder_pos", None)
            shared_state.pop("interceptor_pos", None)

    # ACMI export — start at mission begin
    acmi = ACMIWriter()
    mission_recorder = MissionRecorder(
        MISSION_RECORD_DIR,
        mission={
            "intruder_type": intruder_key,
            "pattern": pattern_key,
            "pad": pad_key,
            "initial_speed": initial_speed,
            "site": site_config["name"],
            "environment": pattern.get("environment", "clear"),
        },
        hardware_profile=HARDWARE_PROFILE.summary(),
    )
    tactical_publisher = (
        TacticalUdpPublisher.from_endpoint(
            TELEMETRY_UDP,
            recording_path=TELEMETRY_RECORD,
        )
        if TELEMETRY_UDP else None
    )

    if INTEGRATED_C2:
        print(
            "\n  ▶▶  Integrated command center active — physics and 3-D site view "
            "are fused into the dashboard.\n",
            flush=True,
        )
    else:
        print(
            "\n  ▶▶  PyBullet 3-D sim is running — separate window.\n"
            "      Click that window for keyboard controls (Space, C, Q, …).\n",
            flush=True,
        )
    if sys.platform == "darwin":
        try:
            import subprocess as _sp

            _sp.run(
                [
                    "osascript",
                    "-e",
                    "tell application \"System Events\" to set frontmost "
                    f"of (first process whose unix id is {os.getpid()}) to true",
                ],
                timeout=2.5,
                capture_output=True,
                check=False,
            )
        except Exception:
            pass

    radar_body, spin_joint = _load_radar_station(_DOME_RADIUS, world.client)
    if pybullet_gui and spin_joint >= 0:
        pybullet.setJointMotorControl2(
            radar_body, spin_joint,
            pybullet.VELOCITY_CONTROL,
            targetVelocity=_RADAR_OMEGA, force=5.0,
            physicsClientId=world.client,
        )

    # Multi-line HUD above the dome (PyBullet GUI only)
    _hud_ids = {}
    if pybullet_gui:
        _hud_ids['status'] = pybullet.addUserDebugText(
            "● STATUS: CLEAR",
            [0, 0, 215],
            [0.0, 1.0, 0.4], textSize=1.8, physicsClientId=world.client,
        )
        _hud_ids['intruder'] = pybullet.addUserDebugText(
            "INTRUDER  initializing...",
            [0, 0, 208],
            [1.0, 0.3, 0.2], textSize=1.2, physicsClientId=world.client,
        )
        _hud_ids['interceptor'] = pybullet.addUserDebugText(
            "INTERCEPTOR  on pad",
            [0, 0, 201],
            [0.2, 0.6, 1.0], textSize=1.2, physicsClientId=world.client,
        )
        pybullet.addUserDebugText(
            "SPACE=pause  1-6=speed  C=camera  R=restart  Q=quit",
            [0, 0, 194],
            [0.3, 0.4, 0.3], textSize=0.9, physicsClientId=world.client,
        )

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
        color="multi",
        max_h_force=320.0, max_v_force=320.0, max_speed=70.0,
        kp=6.5, kd=4.2,
        urdf=_int_urdf if os.path.isfile(_int_urdf) else None,
        global_scaling=1.8,
        airframe_profile_id="interceptor.reference-v1",
    )

    for _ in range(50):
        world.step()

    if pybullet_gui:
        try:
            sx, sy, sz = i_start
            pybullet.resetDebugVisualizerCamera(
                cameraDistance       = _DOME_RADIUS * 4,
                cameraYaw            = 45,
                cameraPitch          = -28,
                cameraTargetPosition = [sx * 0.3, sy * 0.3, sz * 0.3],
                physicsClientId      = world.client,
            )
        except Exception:
            pass

    cam_zoom_ui = CameraZoomDebugUi(world.client) if pybullet_gui else None

    waypoints = get_waypoints_for_path(pattern["path"])
    nav     = WaypointNavigator(waypoints=waypoints)
    radar   = RadarNode(
        station_pos      = (0.0, 0.0, 10.0),   # dome centre — matches 3-D GLB model
        protected_center = _DOME_CENTER,
        max_range        = environment["radar_max_range_m"],
        elev_max_deg     = environment["radar_elevation_max_deg"],
        min_vel          = 0.8,
        noise_std        = environment["radar_noise_std_m"],
        process_noise    = environment.get("radar_process_noise", 5.0),
        dwell_steps      = environment.get("radar_dwell_steps", 1),
        latency_steps    = environment.get("radar_latency_steps", 0),
        false_alarm_probability=environment.get(
            "radar_false_alarm_probability", 0.0
        ),
        seed=(
            list(INTRUDER_TYPES).index(intruder_key) * 100
            + list(ATTACK_PATTERNS).index(pattern_key)
        ),
    )
    fusion = TrackFusion()
    camera_sensor = None
    if USE_CAMERA_PERCEPTION:
        camera_sensor = RenderedCameraSensor(
            world.client,
            position=(0.0, 0.0, 12.0),
            max_range_m=min(1200.0, environment["visibility_m"]),
            position_noise_std_m=max(0.5, environment["radar_noise_std_m"]),
            dropout_probability=environment["sensor_dropout_probability"],
            latency_frames=environment.get("camera_latency_frames", 0),
            exposure_gain=environment.get("camera_exposure_gain", 1.0),
            image_noise_std=environment.get("camera_image_noise_std", 0.0),
            lens_distortion_fraction=environment.get(
                "camera_lens_distortion_fraction", 0.0
            ),
            rolling_shutter_readout_s=environment.get(
                "camera_rolling_shutter_readout_s", 0.0
            ),
            model_path=CAMERA_MODEL,
            model_device=(0 if ML_DEVICE == "cuda" else None),
            renderer=world.camera_renderer,
        )
        mode = f"YOLO ({CAMERA_MODEL})" if CAMERA_MODEL else "segmentation reference"
        print(f"[EO] Rendered RGB/depth perception enabled: {mode}")
    broadcaster = DataLink(role="broadcast", port=14550)
    guidance    = PurePursuitGuidance()
    live_policy = None
    if ML_MODEL:
        from ml.policy import LivePolicy
        live_policy = LivePolicy(
            ML_MODEL,
            residual_apn=not ML_ABSOLUTE_ACTIONS,
            device=ML_DEVICE,
        )
        print(
            f"[ML] Loaded interceptor policy: {ML_MODEL} "
            f"(device={live_policy.device})"
        )

    # ── Stage B: SITL bridge (optional) ──────────────────────────────
    sitl_bridge = None
    if USE_SITL:
        sitl_bridge = SITLBridge(addr=_SITL_ADDR, port=_SITL_PORT)
        if not sitl_bridge.connect():
            print("[SITL] Connection failed — falling back to Python placeholder FC")
            sitl_bridge = None
        else:
            print("[SITL] Active — interceptor under ArduPilot SITL control")
    dome        = DomeKillZone(center=_DOME_CENTER, radius=_DOME_RADIUS)

    # ── State variables ───────────────────────────────────────────────
    sim_speed            = initial_speed
    paused               = False
    camera_mode          = 0   # 0=free-roam  1=track intruder  2=track interceptor  3=top-down
    show_trail           = True
    interceptor_engaged = False
    predicted_intercept  = None
    closest_approach     = float("inf")
    pending_events       = []
    mission_result       = None
    _last_dome_status    = "CLEAR"
    fusion_confirmed     = False
    radar_acquired       = False
    radar_locked         = False
    detected_at_step     = None
    first_detect_range   = 0.0
    breach_sim_time      = None
    intercept_sim_time   = None
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
    prev_sep       = float("inf")

    # Wind state
    wind_mean = environment["wind_mean_mps"]
    wind_gust = float(environment["wind_gust_mps"])
    wind_force = list(wind_mean)
    wind_timer = 0
    camera_return = {"detected": False, "source": "camera"}
    camera_cue = i_start
    fused_track = None
    tactical_frame = None
    tactical_overlay = {}

    # Dashboard control cache
    dash_ctrl = {
        "paused": False,
        "stopped": False,
        "speed": 1,
        "camera_view": "overview",
        "radar_failure": False,
        "camera_failure": False,
        "actuator_failure": False,
    }
    previous_failures = {
        "radar_failure": False,
        "camera_failure": False,
        "actuator_failure": False,
    }

    # Wall-clock throttle for dashboard state pushes (decoupled from physics tick rate).
    # At sim_speed >= 4x the inner-loop step counter advances multiple ticks per outer
    # iteration, which made the old `step % 4 == 0` gate fire every iteration. Use a
    # monotonic wall-clock target so the queue never sees more than ~_DASH_PUSH_HZ msg/s.
    _DASH_PUSH_HZ      = 60.0
    _DASH_PUSH_PERIOD  = 1.0 / _DASH_PUSH_HZ
    _last_dash_push    = 0.0
    _dash_push_count   = 0
    _dash_push_window  = time.perf_counter()

    if INTEGRATED_C2:
        print("SIMULATION STARTED — use the command-center controls to manage the mission\n")
    else:
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
                requested_speed = msg.get("runtime_speed")
                if requested_speed in {0.1, 0.25, 0.5, 1.0, 2.0, 4.0, 8.0}:
                    sim_speed = float(requested_speed)
                if pybullet_gui:
                    z = msg.get("camera_zoom")
                    if z in ("in", "out"):
                        _apply_pybullet_zoom(world.client, z)
            except Exception:
                break
        for failure_name, previous in previous_failures.items():
            current = bool(dash_ctrl.get(failure_name))
            if current != previous:
                label = failure_name.replace("_", " ").upper()
                pending_events.append(
                    f"{label} {'INJECTED' if current else 'CLEARED'}"
                )
                if failure_name == "radar_failure":
                    radar.reset_latency()
                elif failure_name == "camera_failure" and camera_sensor:
                    camera_sensor.reset_latency()
                    if current:
                        fusion.clear_camera_track()
                previous_failures[failure_name] = current

        if pybullet_gui:
            try:
                zpb = cam_zoom_ui.poll()
                if zpb in ("in", "out"):
                    _apply_pybullet_zoom(world.client, zpb)
            except Exception:
                pass

        # ── Window alive check (GUI mode only) ──────────────────────
        if pybullet_gui and step % 120 == 0:
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

        # ── VisPy keyboard signal drain ──────────────────────────────
        if USE_VISPY and shared_state is not None:
            with state_lock:
                if shared_state.get("restart"):
                    shared_state["restart"] = False
                    mission_result = "RESTART"
                if shared_state.get("quit"):
                    mission_result = "QUIT"
                paused    = shared_state.get("paused",    paused)
                sim_speed = shared_state.get("sim_speed", sim_speed)

        # ── PyBullet keyboard events (GUI mode only) ──────────────────
        if pybullet_gui:
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
                elif key in (67, 99):  # C / c — cycle camera modes
                    camera_mode = (camera_mode + 1) % 4
                    _mode_names = ["FREE-ROAM", "TRACK INTRUDER", "TRACK INTERCEPTOR", "TOP-DOWN"]
                    print(f"[CAM] {_mode_names[camera_mode]}")
                    i_pos_now   = intruder.get_position()
                    int_pos_now = interceptor.get_position() if interceptor_engaged else None
                    _update_camera(world.client, camera_mode, i_pos_now, int_pos_now)
                elif key in (84, 116):  # T / t — quick-toggle intruder tracking
                    camera_mode = 1 if camera_mode != 1 else 0
                    print(f"[CAM] {'TRACK INTRUDER' if camera_mode == 1 else 'FREE-ROAM'}")
                elif key in (43, 61):  # + or =
                    _apply_pybullet_zoom(world.client, "in")
                elif key == 45:  # -
                    _apply_pybullet_zoom(world.client, "out")
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
        inner_steps  = max(1, min(round(sim_speed), 5))  # cap substeps — reduces CPU at 8×
        slow_sleep   = max(0.0, _TIMESTEP * (1.0 / sim_speed - 1.0)) if sim_speed < 1 else 0.0

        # Wind update every ~2 sim seconds
        if (wind_gust > 0.0 or any(wind_mean)) and (step % 480 == 0):
            wind_force = [
                wind_mean[0] + random.uniform(-wind_gust, wind_gust),
                wind_mean[1] + random.uniform(-wind_gust, wind_gust),
                wind_mean[2],
            ]

        # Initialise per-outer-loop state (overwritten each inner step below)
        radar_return   = {"detected": False}
        guidance_track = radar.get_last_track()

        # ── Inner physics sub-steps ───────────────────────────────────
        # Radar scan and guidance are re-computed every physics step so that
        # detection hit-count and APN force stay accurate at all sim speeds.
        for _sub in range(inner_steps):
            nav.update(intruder.get_position())
            intruder.set_target(*nav.get_current_target())
            intruder.update()

            # Wind disturbance on intruder
            if any(wind_force):
                try:
                    pybullet.applyExternalForce(
                        intruder._body, -1, wind_force, list(intruder.get_position()),
                        pybullet.WORLD_FRAME, physicsClientId=world.client,
                    )
                except Exception:
                    pass

            # Radar scan — every physics step keeps detection rate correct
            i_pos        = intruder.get_position()
            radar_return = (
                {"detected": False, "injected_failure": True, "source": "radar"}
                if dash_ctrl.get("radar_failure")
                else radar.scan(i_pos, target_rcs=target_rcs)
            )
            if radar_return.get("detected") and not radar_acquired:
                radar_acquired = True
                pending_events.append("Radar track acquired")
            if radar_return.get("locked") and not radar_locked:
                radar_locked = True
                pending_events.append("Radar track locked")
            if (
                camera_sensor
                and step % 12 == 0
                and not dash_ctrl.get("camera_failure")
            ):
                radar_cue = radar.get_last_track()
                if radar_cue:
                    camera_cue = radar_cue["position_estimate"]
                elif camera_return.get("detected"):
                    camera_cue = camera_return["position_estimate"]
                camera_return = camera_sensor.observe(
                    intruder.body_id, camera_cue, step * _TIMESTEP
                )
            elif dash_ctrl.get("camera_failure"):
                camera_return = {
                    "detected": False,
                    "source": "camera",
                    "injected_failure": True,
                }
            fused_track = fusion.update(
                radar_return,
                camera_return,
                radar.track_confidence(),
                step * _TIMESTEP,
            )
            guidance_track = fused_track
            if guidance_track is None and not dash_ctrl.get("radar_failure"):
                guidance_track = radar.get_last_track()
            if (
                fused_track
                and fused_track.get("source") == "RADAR+EO"
                and not fusion_confirmed
            ):
                fusion_confirmed = True
                pending_events.append("Radar/EO fusion confirmed")

            # Build interceptor setpoint:
            #   engaged       → guidance setpoint (vel+accel mid-course, accel terminal)
            #   guidance idle → position-hold at last track so the interceptor
            #                   coasts toward it instead of stalling
            #   pre-engaged   → position-hold at pad altitude (placeholder FC takeoff)
            if interceptor_engaged and guidance_track:
                if live_policy:
                    g_setpoint = live_policy.compute_setpoint(
                        interceptor.get_state(),
                        guidance_track,
                        radar.track_confidence(),
                        wind_force,
                        min(1.0, sim_time / _MAX_SIM_TIME),
                    )
                else:
                    g_setpoint = guidance.compute_guidance(
                        interceptor.get_state(), guidance_track)
                if g_setpoint.is_empty and guidance_track.get("position_estimate"):
                    g_setpoint = GuidanceSetpoint(
                        frame    = "LOCAL_NED",
                        position = enu_to_ned(guidance_track["position_estimate"]),
                    )
            else:
                # Pre-engagement: takeoff to pad altitude under the placeholder FC.
                # Stage B: this becomes MAV_CMD_NAV_TAKEOFF then GUIDED mode.
                g_setpoint = GuidanceSetpoint(
                    frame    = "LOCAL_NED",
                    position = pad_position_ned,
                )

            try:
                if dash_ctrl.get("actuator_failure"):
                    pass
                elif USE_SITL and sitl_bridge is not None:
                    # Send setpoint to ArduPilot at 20 Hz; sync PyBullet body
                    # every step so position/velocity reads stay accurate.
                    if step % _SITL_SEND_INTERVAL == 0:
                        sitl_bridge.send_setpoint(g_setpoint)
                    _sp, _sv = sitl_bridge.get_state()
                    pybullet.resetBasePositionAndOrientation(
                        interceptor._body, list(_sp), [0.0, 0.0, 0.0, 1.0],
                        physicsClientId=world.client)
                    pybullet.resetBaseVelocity(
                        interceptor._body, list(_sv), [0.0, 0.0, 0.0],
                        physicsClientId=world.client)
                else:
                    interceptor.apply_setpoint(g_setpoint)
            except Exception:
                mission_result = "ABORTED"
                break

            world.step()
            step += 1

            if slow_sleep > 0:
                time.sleep(slow_sleep)

        if mission_result:
            break

        # ── Refresh positions after inner loop ────────────────────────
        i_pos   = intruder.get_position()
        int_pos = interceptor.get_position() if interceptor_engaged else None
        if INTEGRATED_C2 and step % 24 == 0:
            tactical_capture = world.capture_tactical_view(
                intruder_position=i_pos,
                interceptor_position=int_pos,
                intruder_velocity=intruder.get_velocity(),
                interceptor_velocity=(
                    interceptor.get_velocity() if interceptor_engaged else None
                ),
                predicted_intercept=predicted_intercept,
                view_mode=dash_ctrl.get("camera_view", "overview"),
                include_metadata=True,
            )
            tactical_frame = tactical_capture["frame"]
            tactical_overlay = {
                "view_mode": tactical_capture["view_mode"],
                "screen_points": tactical_capture["screen_points"],
            }

        # ── Dome status ───────────────────────────────────────────────
        dome.update_status(
            intruder_position    = i_pos,
            intruder_detected    = radar_return.get("detected", False),
            interceptor_position = int_pos,
            intercept_radius     = 18.0,   # scaled for 200 m dome
        )
        status = dome.get_status()

        if status != _last_dome_status:
            _dome_colors = {
                "CLEAR"      : [0.0, 0.6, 0.1],
                "TRACKING"   : [0.8, 0.7, 0.0],
                "BREACH"     : [1.0, 0.1, 0.05],
                "INTERCEPTED": [0.0, 0.8, 1.0],
            }
            # ACMI events on status transitions
            if status == "TRACKING" and _last_dome_status == "CLEAR":
                acmi.write_event(sim_time, "RADAR_LOCK")
                pending_events.append("Threat entered engagement zone")
            elif status == "BREACH":
                acmi.write_event(sim_time, "DOME_BREACH")
                pending_events.append("Protected zone breached")
                if breach_sim_time is None:
                    breach_sim_time = sim_time
            elif status == "INTERCEPTED":
                acmi.write_event(sim_time, "INTERCEPT")
                pending_events.append("Intercept confirmed")
                if intercept_sim_time is None:
                    intercept_sim_time = sim_time
            if pybullet_gui:
                try:
                    world.draw_dome(
                        _DOME_CENTER, _DOME_RADIUS,
                        color=_dome_colors.get(status, [0.0, 0.6, 0.1]),
                    )
                except Exception:
                    mission_result = "ABORTED"
                    break
            _last_dome_status = status

        # ── Detection timestamp ───────────────────────────────────────
        if status in ("TRACKING", "BREACH") and detected_at_step is None:
            detected_at_step   = step
            first_detect_range = radar_return.get("range", 0.0)

        # ── Interceptor engagement trigger ────────────────────────────
        # Placeholder FC has been climbing to pad altitude since spawn.
        # Engage guidance once (a) the response delay has elapsed,
        # (b) the radar still has a track, and (c) the climb is within
        # tolerance of pad altitude.  Stage B will map this transition to
        # a GUIDED-mode handoff after MAV_CMD_NAV_TAKEOFF completes.
        if (not interceptor_engaged
                and detected_at_step is not None
                and step >= detected_at_step + response_delay_steps
                and interceptor.get_position()[2] >= PAD_ALTITUDE_M - TAKEOFF_TOL_M):
            interceptor_engaged = True
            int_pos = interceptor.get_position()
            pending_events.append("Interceptor engaged")
            print(f"INTERCEPTOR: ENGAGED  delay={itype['response_delay']:.1f}s  "
                  f"alt={int_pos[2]:.1f}m")

        # ── Track closest approach ────────────────────────────────────
        if interceptor_engaged and int_pos:
            sep = math.sqrt(sum((int_pos[k]-i_pos[k])**2 for k in range(3)))
            if sep < closest_approach:
                closest_approach = sep
            # Flyby-miss detection: interceptor made a genuine approach
            # (got within 150 m) then diverged — end the sim immediately
            # instead of running until the 4-minute timeout.
            if closest_approach < 150.0 and sep > closest_approach + 60.0:
                acmi.write_event(sim_time, "MISS_FLYBY")
                print(f"INTERCEPTOR: MISSED — closest {closest_approach:.1f}m, now {sep:.1f}m away")
                mission_result = "FAILURE"
            prev_sep = sep

        # ── Broadcast track every 2 sim-s ────────────────────────────
        if radar_return.get("detected") and step % 480 == 0:
            broadcaster.send_track(radar_return)

        # ── Terminal conditions ───────────────────────────────────────
        if status == "INTERCEPTED":
            if not flash_shown:
                if pybullet_gui:
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
            acmi.write_event(sim_time, "MISS")
            mission_result = "FAILURE"
            break

        # Camera: free-roam when mode==0, auto-follow when mode 1/2/3 (GUI only)
        if pybullet_gui and camera_mode != 0 and step % 12 == 0:
            _update_camera(world.client, camera_mode, i_pos, int_pos)

        # ── 3-D trail update (PyBullet GUI mode only) ─────────────────
        if pybullet_gui and show_trail and step % 5 == 0:
            i_last_pos = _update_trail(
                i_pos, i_last_pos, i_trail_ids, 30,
                [0.9, 0.12, 0.08], world.client,
            )
            if interceptor_engaged and int_pos:
                int_last_pos = _update_trail(
                    int_pos, int_last_pos, int_trail_ids, 30,
                    [0.10, 0.55, 0.90], world.client,
                )

        # ── Intercept-vector line (PyBullet GUI mode only) ────────────
        if pybullet_gui and interceptor_engaged and predicted_intercept and step % 12 == 0:
            int_pos_now = interceptor.get_position()
            if icept_vec_id is not None:
                try:
                    pybullet.removeUserDebugItem(icept_vec_id, physicsClientId=world.client)
                except Exception:
                    pass
            try:
                icept_vec_id = pybullet.addUserDebugLine(
                    list(int_pos_now), list(predicted_intercept),
                    [1.0, 0.80, 0.0], lineWidth=1.5,
                    physicsClientId=world.client,
                )
            except Exception:
                pass

        predicted_intercept = (
            guidance.predicted_intercept_point(
                interceptor.get_state(),
                guidance_track,
            )
            if interceptor_engaged and guidance_track
            else None
        )

        # ── HUD / shared_state update (every 8 steps ≈ 30 Hz) ────────
        if step % 8 == 0:
            _i_spd   = math.sqrt(sum(v**2 for v in intruder.get_velocity()))
            _int_spd = math.sqrt(sum(v**2 for v in interceptor.get_velocity())) \
                       if interceptor_engaged else 0.0
            tti_val  = guidance.time_to_intercept(interceptor.get_state(), guidance_track) \
                       if (interceptor_engaged and guidance_track) else float("inf")

            # VisPy shared state update
            if USE_VISPY and shared_state is not None:
                _i_state   = intruder.get_state()
                _int_state = interceptor.get_state() if interceptor_engaged else None
                with state_lock:
                    shared_state.update({
                        "dome_status":            status,
                        "intruder_pos":           list(i_pos),
                        "intruder_orientation":   list(_i_state.get("orientation", [0,0,0,1])),
                        "interceptor_pos":        list(int_pos) if int_pos else None,
                        "interceptor_orientation": list(_int_state["orientation"])
                                                   if _int_state else None,
                        "predicted_intercept":    predicted_intercept,
                        "intruder_speed":         _i_spd,
                        "interceptor_speed":      _int_spd,
                        "tti":                    tti_val,
                        "mission_time":           sim_time,
                        "sim_speed":              sim_speed,
                        "paused":                 paused or dash_ctrl.get("paused", False),
                        "radar_return":           radar_return,
                        "camera_return":          camera_return,
                        "fused_track":            fused_track,
                    })

            # PyBullet HUD text (GUI mode only)
            if pybullet_gui:
                _sc = {
                    "CLEAR"      : [0.0, 1.0, 0.4],
                    "TRACKING"   : [1.0, 0.8, 0.0],
                    "BREACH"     : [1.0, 0.2, 0.0],
                    "INTERCEPTED": [0.0, 0.9, 1.0],
                }.get(status, [1, 1, 1])
                _paused_tag = " [PAUSED]" if (paused or dash_ctrl.get("paused")) else ""
                _rng_m   = radar_return.get("range", 0.0) if radar_return.get("detected") else None
                _i_alt   = i_pos[2]
                _rng_str = f"{_rng_m:.0f}m" if _rng_m is not None else "no lock"
                try:
                    _hud_ids['status'] = pybullet.addUserDebugText(
                        f"● {status}{_paused_tag}  {sim_speed:.2g}×",
                        [0, 0, 215], _sc,
                        textSize=1.8, replaceItemUniqueId=_hud_ids.get('status', -1),
                        physicsClientId=world.client,
                    )
                    _hud_ids['intruder'] = pybullet.addUserDebugText(
                        f"INTRUDER  rng:{_rng_str}  spd:{_i_spd:.0f}m/s  alt:{_i_alt:.0f}m",
                        [0, 0, 208], [1.0, 0.3, 0.2],
                        textSize=1.2, replaceItemUniqueId=_hud_ids.get('intruder', -1),
                        physicsClientId=world.client,
                    )
                    if interceptor_engaged and int_pos:
                        _sep = math.sqrt(sum((int_pos[k]-i_pos[k])**2 for k in range(3)))
                        _tti_str = f"{tti_val:.1f}s" if tti_val < 999 else "---"
                        _hud_ids['interceptor'] = pybullet.addUserDebugText(
                            f"INTERCEPTOR  sep:{_sep:.0f}m  TTI:{_tti_str}  spd:{_int_spd:.0f}m/s",
                            [0, 0, 201], [0.2, 0.6, 1.0],
                            textSize=1.2, replaceItemUniqueId=_hud_ids.get('interceptor', -1),
                            physicsClientId=world.client,
                        )
                    else:
                        _hud_ids['interceptor'] = pybullet.addUserDebugText(
                            "INTERCEPTOR  on pad",
                            [0, 0, 201], [0.2, 0.6, 1.0],
                            textSize=1.2, replaceItemUniqueId=_hud_ids.get('interceptor', -1),
                            physicsClientId=world.client,
                        )
                except Exception:
                    pass

            # Console log
            if step % _LOG_INTERVAL == 0:
                rng  = radar_return.get("range", 0.0) if radar_return.get("detected") else 0.0
                sep  = "--"
                if interceptor_engaged and int_pos:
                    sep = f"{math.sqrt(sum((int_pos[k]-i_pos[k])**2 for k in range(3))):.1f}m"
                print(
                    f"T+{sim_time:5.1f}s  INTR ({i_pos[0]:.1f},{i_pos[1]:.1f},{i_pos[2]:.1f})"
                    f"  RADAR {rng:.1f}m  {status:10s}  INT {sep}"
                )

        # ── ACMI update (every 24 steps ≈ 10 Hz) ──────────────────────
        if step % 24 == 0:
            try:
                acmi.update(
                    sim_time,
                    intruder.get_state(),
                    interceptor.get_state() if interceptor_engaged else None,
                )
            except Exception:
                pass
            if tactical_publisher is not None:
                try:
                    intruder_state = intruder.get_state()
                    interceptor_state = (
                        interceptor.get_state()
                        if int_pos is not None else None
                    )
                    tactical_publisher.publish({
                        "mission_time_s": float(sim_time),
                        "timestamp_clock": "simulation-relative",
                        "status": status,
                        "site": site_config["name"],
                        "guidance": (
                            "residual_ai_apn" if live_policy else
                            "ardupilot_sitl" if sitl_bridge else
                            "apn"
                        ),
                        "coordinate_frame": {
                            "type": "local-tangent-plane",
                            "axes": "ENU",
                            "position_unit": "m",
                            "velocity_unit": "m/s",
                            "orientation": "xyzw",
                        },
                        "georeference": {
                            "origin": dict(site_config["origin"]),
                            "status": site_config.get(
                                "origin_status", "placeholder"
                            ),
                        },
                        "terrain": {
                            "source": world.terrain_source,
                            "collision_authoritative": True,
                        },
                        "tracks": {
                            "intruder": {
                                "id": "TRK-001",
                                "role": "intruder",
                                "asset_id": f"intruder/{intruder_key}",
                                "type": intruder_key,
                                "position_enu_m": list(map(float, i_pos)),
                                "velocity_enu_mps": list(map(float, intruder.get_velocity())),
                                "orientation_xyzw": list(map(
                                    float, intruder_state["orientation"]
                                )),
                            },
                            "interceptor": (
                                {
                                    "id": "INT-01",
                                    "role": "interceptor",
                                    "asset_id": "interceptor/default",
                                    "type": "interceptor",
                                    "position_enu_m": list(map(float, int_pos)),
                                    "velocity_enu_mps": list(
                                        map(float, interceptor.get_velocity())
                                    ),
                                    "orientation_xyzw": list(map(
                                        float,
                                        interceptor_state["orientation"],
                                    )),
                                }
                                if int_pos is not None else None
                            ),
                        },
                        "predicted_intercept_enu_m": (
                            list(map(float, predicted_intercept))
                            if predicted_intercept is not None else None
                        ),
                        "sensors": {
                            "radar_locked": bool(radar_return.get("detected")),
                            "eo_locked": bool(camera_return.get("detected")),
                            "fusion_source": (
                                fused_track.get("source")
                                if fused_track else "SEARCHING"
                            ),
                        },
                    })
                except OSError as exc:
                    print(f"[telemetry] UDP stream disabled after send error: {exc}")
                    tactical_publisher.close()
                    tactical_publisher = None

        # ── Dashboard state push (wall-clock 60 Hz) ──────────────────
        i_v   = intruder.get_velocity()
        int_v = interceptor.get_velocity() if interceptor_engaged else (0, 0, 0)
        tti   = float("inf")
        if interceptor_engaged and radar_return.get("detected") and guidance_track:
            tti = guidance.time_to_intercept(interceptor.get_state(), guidance_track)

        _now = time.perf_counter()
        if _now - _last_dash_push >= _DASH_PUSH_PERIOD:
            _last_dash_push = _now
            dashboard_state = {
                    "dome_status"        : status,
                    "intruder_pos"       : i_pos,
                    "interceptor_pos"    : int_pos,
                    "radar_return"       : radar_return,
                    "camera_return"      : camera_return,
                    "fused_track"        : fused_track,
                    "camera_frame"       : tactical_frame,
                    "tactical_overlay"   : tactical_overlay,
                    "intruder_key"       : intruder_key,
                    "pattern_key"        : pattern_key,
                    "environment_name"   : pattern.get("environment", "clear"),
                    "visibility_m"       : environment["visibility_m"],
                    "wind_mps"           : tuple(wind_force),
                    "site_name"          : site_config["name"],
                    "guidance_mode"      : (
                        "RESIDUAL AI + APN" if live_policy else
                        "ARDUPILOT SITL" if sitl_bridge else
                        "APN AUTONOMY"
                    ),
                    "radar_station"      : radar.station_pos.tolist(),
                    "predicted_intercept": predicted_intercept,
                    "intruder_speed"     : math.sqrt(sum(v**2 for v in i_v)),
                    "interceptor_speed"  : math.sqrt(sum(v**2 for v in int_v)),
                    "intruder_velocity"  : tuple(i_v),
                    "interceptor_velocity": tuple(int_v),
                    "tti"                : tti,
                    "track_confidence"   : radar.track_confidence(),
                    "last_detection_time": radar.last_detection_time,
                    "events"             : pending_events,
                    "mission_time"       : sim_time,
                    "sim_speed"          : sim_speed,
                    "real_time_factor"   : sim_time / max(
                        time.time() - sim_start,
                        1e-6,
                    ),
                    "render_backend"     : world.render_backend,
                    "terrain_source"     : world.terrain_source,
                    "compute_backend"    : (
                        f"PYTORCH {live_policy.device.upper()}"
                        if live_policy else "CLASSICAL APN / CPU"
                    ),
                    "hardware_profile"   : HARDWARE_PROFILE.label,
                    "hardware_mode"      : HARDWARE_PROFILE.mode.upper(),
                    "mission_run_id"     : mission_recorder.run_id,
                    "airframe_profiles"  : {
                        "intruder": intruder.get_state().get(
                            "airframe_profile_id"
                        ),
                        "interceptor": interceptor.get_state().get(
                            "airframe_profile_id"
                        ),
                    },
                    "energy_remaining"   : {
                        "intruder": intruder.get_state().get(
                            "energy_remaining_fraction", 1.0
                        ),
                        "interceptor": interceptor.get_state().get(
                            "energy_remaining_fraction", 1.0
                        ),
                    },
                    "injected_failures"  : {
                        key: bool(dash_ctrl.get(key))
                        for key in previous_failures
                    },
                }
            mission_recorder.record_snapshot(dashboard_state)
            pending_events = []
            try:
                state_q.put_nowait(dashboard_state)
            except Exception:
                pass
            else:
                tactical_frame = None
                tactical_overlay = {}
                _dash_push_count += 1

            # 5-second rolling rate report
            if _now - _dash_push_window >= 5.0:
                _rate = _dash_push_count / (_now - _dash_push_window)
                print(f"[dash-throttle] ~{_rate:5.1f} push/s "
                      f"(target {_DASH_PUSH_HZ:.0f}, sim_speed {sim_speed:.2g}x)")
                _dash_push_count  = 0
                _dash_push_window = _now

    # ── Cleanup ───────────────────────────────────────────────────────
    _clear_trail(i_trail_ids,   world.client)
    _clear_trail(int_trail_ids, world.client)

    try:
        pybullet.disconnect(world.client)
    except Exception:
        pass
    broadcaster.close()
    acmi.close()
    if tactical_publisher is not None:
        tactical_publisher.close()
    if sitl_bridge is not None:
        sitl_bridge.close()

    total_sim = step * _TIMESTEP
    result = {
        "result"             : mission_result,
        "intruder_key"       : intruder_key,
        "pattern_key"        : pattern_key,
        "sim_time"           : total_sim,
        "first_detect_sim_t" : (detected_at_step * _TIMESTEP) if detected_at_step else 0.0,
        "first_detect_range" : first_detect_range,
        "breach_sim_time"    : breach_sim_time,
        "intercept_sim_time" : intercept_sim_time,
        "closest_approach"   : closest_approach,
        "max_penetration"    : dome.max_penetration_depth(),
        "sim_start"          : sim_start,
        "acmi_file"          : acmi.filename,
        "mission_run_id"     : mission_recorder.run_id,
        "mission_manifest"   : mission_recorder.manifest_path,
    }
    mission_recorder.finalize(
        result,
        artifacts={"acmi": acmi.filepath},
    )
    return result


# ======================================================================
# Mission debrief
# ======================================================================

def _print_debrief(result: str, stats: dict):
    w = 52
    R = "\033[91m"   # red
    G = "\033[92m"   # green
    X = "\033[0m"    # reset
    result_str  = "★  INTERCEPT SUCCESS" if result == "INTERCEPTED" else "✗  MISSION FAILED"
    result_color = G if result == "INTERCEPTED" else R
    print("\n" + "═" * w)
    print(f"{'MISSION DEBRIEF':^{w}}")
    print("═" * w)
    print(f"{result_color}{result_str:^{w}}{X}")
    print("─" * w)
    print(f"  Duration          {stats['duration']:.1f}s")
    print(f"  Intruder type     {stats['intruder_type']}")
    print(f"  Attack pattern    {stats['pattern']}")
    if stats.get('first_detect'):
        print(f"  First detection   T+{stats['first_detect']:.1f}s at {stats['detect_range']:.0f}m")
    if stats.get('breach_time') is not None:
        print(f"  Dome breach       T+{stats['breach_time']:.1f}s")
    print(f"  Max penetration   {stats['max_penetration']:.0f}m into dome")
    if result == "INTERCEPTED":
        if stats.get('intercept_time') is not None:
            print(f"  Intercept time    T+{stats['intercept_time']:.1f}s")
        ca = stats.get('closest_approach', float('inf'))
        if ca < 9999:
            print(f"  Closest approach  {ca:.1f}m")
    print(f"  ACMI file saved   missions/{stats.get('acmi_file', '---')}")
    print("═" * w)
    print("  [R] Run again  [M] Main menu in dashboard  [Q] Quit")
    print("═" * w + "\n")


# ======================================================================
# Controls banner (console only — all UX is in the dashboard)
# ======================================================================

def _print_controls():
    if INTEGRATED_C2:
        print(
            "\nANTI-DRONE DOME V3 — integrated command center\n"
            "Mission selection, playback, camera, reset, and abort controls are in one window.\n"
        )
        return
    print("""
╔══════════════════════════════════════════════════════════╗
║         ANTI-DRONE DOME  V3  —  KEYBOARD CONTROLS       ║
╠══════════════════════════════════════════════════════════╣
║  PyBullet 3-D window must have focus for keys to work   ║
╠══════════════════════════════════════════════════════════╣
║  SPACE   Pause / resume                                 ║
║  R       Restart same scenario                          ║
║  0–6     Sim speed  0.1× / 0.25× / 0.5× / 1× / 2× / 4× / 8×  ║
║  C       Cycle camera  (free-roam/track intruder/       ║
║            track interceptor/top-down)                  ║
║  T       Quick-toggle intruder tracking on/off          ║
║  + / =   Zoom 3-D view in (closer)                       ║
║  -       Zoom 3-D view out (farther)                     ║
║  I       Toggle 3-D trail                               ║
║  H       Print this help                                ║
║  Q       Return to mission select                       ║
╠══════════════════════════════════════════════════════════╣
║  PYBULLET: right panel — “3D +/− ZOOM” sliders (slide→1, ║
║  back→0)  +  keys +/−  +  dashboard strip — same zoom.   ║
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

    if INTEGRATED_C2:
        print(
            "\n[SIM] Command center ready — choose a threat, route, launch pad, and speed,\n"
            "      then select START. The live 3-D site view stays embedded in this window.\n"
        )
    else:
        print(
            "\n[SIM] Dashboard is ready — choose a mission and select START.\n"
            "      The separate 3-D renderer may open behind this window.\n"
        )

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


def _mission_loop(state_q, ctrl_q, dash_proc, shared_state=None, state_lock=None):
    """Full mission loop — runs in main thread (no-vispy) or a background thread (vispy)."""
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

            if isinstance(current_intruder, str) and current_intruder.startswith("swarm:"):
                _run_swarm_mission(
                    current_intruder.split(":", 1)[1],
                    state_q=state_q, ctrl_q=ctrl_q,
                )
                current_intruder = None
                continue

            result = _run_one_mission(
                state_q, ctrl_q,
                intruder_key  = current_intruder,
                pattern_key   = current_pattern,
                initial_speed = chosen_speed,
                pad_key       = chosen_pad,
                shared_state  = shared_state,
                state_lock    = state_lock,
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

            # Console debrief
            if mr in ("INTERCEPTED", "FAILURE", "TIMEOUT"):
                _print_debrief(mr, {
                    "duration"        : result["sim_time"],
                    "intruder_type"   : INTRUDER_TYPES[current_intruder]["label"],
                    "pattern"         : ATTACK_PATTERNS[current_pattern]["label"],
                    "first_detect"    : result.get("first_detect_sim_t", 0.0),
                    "detect_range"    : result.get("first_detect_range", 0.0),
                    "breach_time"     : result.get("breach_sim_time"),
                    "max_penetration" : result.get("max_penetration", 0.0),
                    "intercept_time"  : result.get("intercept_sim_time"),
                    "closest_approach": result.get("closest_approach", float("inf")),
                    "acmi_file"       : result.get("acmi_file", "---"),
                })

            # Send debrief to dashboard and VisPy
            debrief_msg = {
                "type":             "debrief",
                "result":           mr,
                "sim_time":         result["sim_time"],
                "closest_approach": result.get("closest_approach", float("inf")),
                "intruder":         current_intruder,
            }
            try:
                state_q.put_nowait(debrief_msg)
            except Exception:
                pass
            if USE_VISPY and shared_state is not None:
                with state_lock:
                    shared_state["debrief"] = debrief_msg
                time.sleep(4.0)
                with state_lock:
                    shared_state.pop("debrief", None)

            current_intruder, current_pattern, chosen_speed, chosen_pad = \
                _wait_for_mission(state_q, ctrl_q, dash_proc)

    except KeyboardInterrupt:
        print("\n[SIM] Interrupted by user.")
    except Exception as e:
        import traceback
        print(f"\n[SIM] Crash: {e}")
        traceback.print_exc()

    if USE_VISPY and shared_state is not None:
        with state_lock:
            shared_state["app_quit"] = True


def _run_swarm_mission(scenario_id, *, telemetry_udp=None,
                       state_q=None, ctrl_q=None) -> int:
    """PyBullet swarm engagement: an airborne coordinator directs an interceptor
    swarm against a saturation attack.

    Reuses the real Drone dynamics, APN guidance, and the shared ``swarm``
    coordination brain. When ``state_q`` is given it drives the live command
    center (pushing a multi-entity ``swarm`` block the dashboard renders on the
    tactical picture, and honouring pause/stop on ``ctrl_q``); otherwise it runs
    fully headless. Optionally streams ``aegis.swarm-coordination.v1`` telemetry.
    """
    import numpy as np

    from swarm.coordinator import SwarmCoordinator
    from swarm.rf_link import RfLinkModel
    from swarm.scenario import get_swarm_scenario
    from swarm.telemetry import SwarmTelemetryPublisher, build_swarm_packet

    try:
        scenario = get_swarm_scenario(scenario_id)
    except (OSError, ValueError, KeyError) as exc:
        print(f"[swarm] {exc}")
        if state_q is not None:
            try:
                state_q.put_nowait({"type": "show_menu"})
            except Exception:
                pass
        return 2

    center = [float(c) for c in scenario.protected_center_enu_m]
    guidance = PurePursuitGuidance()
    world = PhysicsWorld(gui=False, site_config=None, render_backend="tiny")

    coord_spec = scenario.coordinator
    coordinator_body = Drone(
        coord_spec.id, tuple(coord_spec.start_enu_m), world.client,
        color="gray", airframe_profile_id="interceptor.reference-v1",
    )
    coordinator_body.set_target(*coord_spec.start_enu_m)

    interceptors = [
        {"spec": spec, "drone": Drone(
            spec.id, tuple(spec.start_enu_m), world.client,
            color="multi", airframe_profile_id=spec.airframe_profile_id,
        ), "expended": False}
        for spec in scenario.interceptors
    ]
    threats = [
        {"spec": spec, "munition": LoiteringMunition(
            spec.id, tuple(spec.start_enu_m), world.client,
            intruder_cfg=INTRUDER_TYPES.get(spec.type, {}),
        ), "status": "ACTIVE", "resolved_time": None}
        for spec in scenario.threats
    ]

    coordinator = SwarmCoordinator(
        RfLinkModel(coord_spec.rf_link, seed=scenario.seed),
        protected_center=tuple(center), guidance=guidance, policy=coord_spec.policy,
    )

    publisher = None
    if telemetry_udp:
        publisher = SwarmTelemetryPublisher.from_endpoint(telemetry_udp)

    dt = 1.0 / 240.0
    max_steps = int(scenario.duration_limit_s / dt)
    intercept_r = scenario.intercept_radius_m
    breach_r = scenario.breach_radius_m
    t = 0.0
    print(
        f"[swarm] {scenario.scenario_id}: {len(interceptors)} interceptors vs "
        f"{len(threats)} threats, policy={coord_spec.policy}, seed={scenario.seed}"
    )
    if state_q is not None:
        try:
            state_q.put_nowait({"type": "mission_start"})
        except Exception:
            pass

    def _margin(order):
        if order is None or not math.isfinite(order.link_margin_db):
            return -999.0
        return float(order.link_margin_db)

    def _swarm_body():
        return build_swarm_packet(
            mission_time_s=t,
            coordinator={
                "id": coord_spec.id,
                "position_enu_m": [float(c) for c in coordinator_body.get_position()],
                "velocity_enu_mps": [0.0, 0.0, 0.0],
            },
            interceptors=[{
                "id": it["spec"].id,
                "position_enu_m": [float(c) for c in it["drone"].get_position()],
                "velocity_enu_mps": [float(c) for c in it["drone"].get_velocity()],
                "assigned_threat_id": (
                    plan.orders[it["spec"].id].assigned_threat_id
                    if plan and it["spec"].id in plan.orders else None
                ),
                "state": "EXPENDED" if it["expended"] else (
                    plan.orders[it["spec"].id].state
                    if plan and it["spec"].id in plan.orders else "RESERVE"
                ),
                "link_margin_db": _margin(plan.orders.get(it["spec"].id)) if plan else -999.0,
                "energy_remaining_fraction": float(
                    it["drone"].get_state().get("energy_remaining_fraction", 1.0)
                ),
            } for it in interceptors],
            threats=[{
                "id": th["spec"].id, "type": th["spec"].type,
                "threat_level": th["spec"].threat_level,
                "position_enu_m": [float(c) for c in th["munition"].get_position()],
                "velocity_enu_mps": [float(c) for c in th["munition"].get_velocity()],
                "status": th["status"],
            } for th in threats],
            assignment=dict(plan.assignment) if plan else {},
            link_health=plan.link_health if plan else {},
        )

    paused = False
    stopped = False
    last_push = 0.0
    last_cam = -1.0
    wall_start = time.time()

    plan = None
    try:
        for step in range(max_steps):
            # ── Live command-center control (pause/stop) ──────────────────
            if ctrl_q is not None:
                try:
                    while True:
                        msg = ctrl_q.get_nowait()
                        if isinstance(msg, dict):
                            paused = bool(msg.get("paused", paused))
                            if msg.get("stopped") or msg.get("restart"):
                                stopped = True
                except Exception:
                    pass
                if stopped:
                    break
                if paused:
                    if state_q is not None:
                        try:
                            state_q.put_nowait({
                                "dome_status": "PAUSED", "mission_time": t,
                                "sim_speed": 1.0, "swarm": _swarm_body(),
                            })
                        except Exception:
                            pass
                    time.sleep(0.05)
                    continue

            active_threats = [th for th in threats if th["status"] == "ACTIVE"]
            active_interceptors = [it for it in interceptors if not it["expended"]]
            if not active_threats or not active_interceptors:
                break

            interceptor_states = []
            for it in active_interceptors:
                state = it["drone"].get_state()
                state["id"] = it["spec"].id
                interceptor_states.append(state)
            threat_tracks = [{
                "id": th["spec"].id, "type": th["spec"].type,
                "threat_level": th["spec"].threat_level,
                "position_estimate": list(th["munition"].get_position()),
                "velocity": list(th["munition"].get_velocity()),
            } for th in active_threats]

            coord_state = {
                "position": list(coordinator_body.get_position()),
                "velocity": [0.0, 0.0, 0.0],
            }
            plan = coordinator.plan(coord_state, interceptor_states, threat_tracks, t)

            threat_by_id = {th["spec"].id: th for th in active_threats}
            for it in active_interceptors:
                order = plan.orders.get(it["spec"].id)
                target = threat_by_id.get(order.assigned_threat_id) if order else None
                if target is not None:
                    track = {
                        "detected": True,
                        "position_estimate": list(target["munition"].get_position()),
                        "velocity": list(target["munition"].get_velocity()),
                    }
                    it["drone"].apply_setpoint(
                        guidance.compute_guidance(it["drone"].get_state(), track)
                    )
                else:
                    hold = it["drone"].get_position()
                    it["drone"].set_target(hold[0], hold[1], hold[2])
                    it["drone"].update()

            for th in active_threats:
                th["munition"].set_target(center[0], center[1], max(center[2], 5.0))
                th["munition"].update()
            coordinator_body.update()

            world.step()
            t += dt

            # Pace to real time so the command center shows a watchable engagement
            # (headless runs, with no state_q, stay as fast as possible).
            if state_q is not None:
                target_wall = wall_start + t
                lag = target_wall - time.time()
                if lag > 0:
                    time.sleep(min(lag, 0.05))

            for th in active_threats:
                if th["status"] != "ACTIVE":
                    continue
                tpos = np.asarray(th["munition"].get_position(), dtype=float)
                best, best_d = None, intercept_r
                for it in active_interceptors:
                    if it["expended"]:
                        continue
                    d = float(np.linalg.norm(
                        np.asarray(it["drone"].get_position(), dtype=float) - tpos
                    ))
                    if d <= best_d:
                        best_d, best = d, it
                if best is not None:
                    th["status"], th["resolved_time"] = "NEUTRALIZED", t
                    best["expended"] = True
                    continue
                if float(np.linalg.norm(tpos - np.asarray(center))) <= breach_r:
                    th["status"], th["resolved_time"] = "BREACHED", t

            if publisher is not None and step % 12 == 0:
                publisher.publish(_swarm_body())

            # ── Push the live swarm picture to the command center (~60 Hz) ──
            if state_q is not None and (t - last_push) >= (1.0 / 60.0):
                # Capture an oblique 3-D overview for the centre preview at ~20 Hz.
                frame = None
                if (t - last_cam) >= (1.0 / 20.0):
                    positions = [it["drone"].get_position() for it in interceptors
                                 if not it["expended"]]
                    positions += [th["munition"].get_position() for th in threats
                                  if th["status"] == "ACTIVE"]
                    positions.append(coordinator_body.get_position())
                    try:
                        frame = world.capture_swarm_view(positions, protected_center=center)
                    except Exception:
                        frame = None
                    last_cam = t
                push = {
                    "dome_status": "ENGAGING",
                    "mission_time": t,
                    "sim_speed": 1.0,
                    "events": [],
                    "swarm": _swarm_body(),
                }
                if frame is not None:
                    push["camera_frame"] = frame
                try:
                    state_q.put_nowait(push)
                except Exception:
                    pass
                last_push = t
    finally:
        if publisher is not None:
            publisher.close()
        try:
            pybullet.disconnect(world.client)
        except Exception:
            pass

    for th in threats:
        if th["status"] == "ACTIVE":
            th["status"] = "LEAKER"
    neutralized = sum(th["status"] == "NEUTRALIZED" for th in threats)
    breached = sum(th["status"] == "BREACHED" for th in threats)
    leaked = sum(th["status"] == "LEAKER" for th in threats)
    link = coordinator._link_health(plan.orders) if plan is not None else {}

    print(f"[swarm] T+{t:5.1f}s  neutralized {neutralized}/{len(threats)}  "
          f"breached {breached}  leaked {leaked}  "
          f"interceptors used {sum(it['expended'] for it in interceptors)}/{len(interceptors)}  "
          f"link delivery {link.get('delivery_ratio', 1.0):.2f}")
    for th in threats:
        when = f"@T+{th['resolved_time']:.1f}s" if th["resolved_time"] is not None else ""
        print(f"    {th['spec'].id:8s} {th['spec'].type:14s} "
              f"{th['spec'].threat_level:6s} {th['status']} {when}")

    if state_q is not None:
        outcome = "INTERCEPTED" if leaked == 0 and breached == 0 else "FAILURE"
        summary = (
            f"SWARM DEBRIEF  —  {scenario.scenario_id}\n"
            f"neutralized {neutralized}/{len(threats)}   "
            f"breached {breached}   leaked {leaked}\n"
            f"interceptors used {sum(it['expended'] for it in interceptors)}"
            f"/{len(interceptors)}   link {link.get('delivery_ratio', 1.0)*100:.0f}%"
        )
        try:
            state_q.put_nowait({
                "type": "debrief", "result": outcome, "summary": summary,
                "closest_approach": 0.0, "sim_time": t,
            })
        except Exception:
            pass
    return 0


def main():
    global USE_VISPY, USE_SITL, ML_MODEL, ML_ABSOLUTE_ACTIONS
    global USE_CAMERA_PERCEPTION, CAMERA_MODEL, ML_DEVICE, RENDER_BACKEND
    global INTEGRATED_C2, TELEMETRY_UDP, TELEMETRY_RECORD
    global _SITL_ADDR, _SITL_PORT
    global HARDWARE_PROFILE, MISSION_RECORD_DIR
    mp.freeze_support()
    try:
        sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

    parser = argparse.ArgumentParser(description="Anti-Drone Dome Simulation")
    parser.add_argument("--no-vispy", action="store_true",
                        help="Use PyBullet GUI renderer instead of VisPy")
    parser.add_argument("--sitl", action="store_true",
                        help="Connect interceptor to ArduCopter SITL via MAVLink")
    parser.add_argument(
        "--allow-sitl-arm",
        action="store_true",
        help="Explicitly acknowledge that ArduPilot SITL may arm and take off",
    )
    parser.add_argument("--sitl-addr", default="127.0.0.1",
                        help="SITL UDP address (default: 127.0.0.1)")
    parser.add_argument("--sitl-port", type=int, default=14560,
                        help="SITL UDP port (default: 14560)")
    parser.add_argument("--ml-model",
                        help="Stable-Baselines3 PPO policy path for interceptor guidance")
    parser.add_argument("--ml-absolute-actions", action="store_true",
                        help="Interpret ML actions as absolute commands instead of APN residuals")
    parser.add_argument("--camera-perception", action="store_true",
                        help="Fuse rendered RGB/depth camera detections with radar tracks")
    parser.add_argument("--camera-model",
                        help="YOLO weights for rendered camera detections")
    parser.add_argument(
        "--ml-device",
        choices=("auto", "cpu", "cuda"),
        default="auto",
        help="PyTorch inference device for PPO/YOLO",
    )
    parser.add_argument(
        "--render-backend",
        choices=("auto", "opengl", "tiny"),
        default="auto",
        help="Tactical camera renderer; auto prefers OpenGL",
    )
    parser.add_argument("--legacy-windows", action="store_true",
                        help="Use separate 3-D and dashboard windows")
    parser.add_argument("--auto-start", action="store_true",
                        help="Immediately launch the default critical-site mission")
    parser.add_argument(
        "--capture-ui-dir",
        help="Save live dashboard screenshots and state at T+3, T+8, and T+13",
    )
    parser.add_argument(
        "--telemetry-udp",
        metavar="HOST:PORT",
        help="Stream versioned tactical state to an external renderer",
    )
    parser.add_argument(
        "--telemetry-record",
        metavar="PATH",
        help="Record transmitted tactical packets as validated JSONL",
    )
    parser.add_argument(
        "--hardware-profile",
        default="hardware_profiles/reference_sil.json",
        help="Validated hardware/SIL profile JSON",
    )
    parser.add_argument(
        "--mission-record-dir",
        default=os.path.join("missions", "runs"),
        help="Directory for versioned mission manifests and JSONL telemetry",
    )
    parser.add_argument(
        "--swarm",
        metavar="SCENARIO",
        help="Run a headless coordinator-directed interceptor-swarm engagement "
             "(scenario id from scenario_data/swarm_scenarios_v1.json) and exit",
    )
    parser.add_argument(
        "--swarm-live",
        metavar="SCENARIO",
        help="Launch the command center and run the swarm scenario live in it",
    )
    args = parser.parse_args()
    if args.telemetry_udp:
        try:
            UdpEndpoint.parse(args.telemetry_udp)
        except (ValueError, TypeError) as exc:
            parser.error(str(exc))
    if args.telemetry_record and not args.telemetry_udp:
        parser.error("--telemetry-record requires --telemetry-udp")
    if args.swarm:
        raise SystemExit(_run_swarm_mission(args.swarm, telemetry_udp=args.telemetry_udp))
    if args.sitl and args.ml_model:
        parser.error("--sitl and --ml-model are mutually exclusive guidance sources")
    if args.sitl and not args.allow_sitl_arm:
        parser.error("--sitl requires explicit --allow-sitl-arm acknowledgement")
    try:
        HARDWARE_PROFILE = load_hardware_profile(args.hardware_profile)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        parser.error(f"invalid hardware profile: {exc}")
    if args.sitl and (
        HARDWARE_PROFILE.mode != "sitl"
        or HARDWARE_PROFILE.protocol != "mavlink"
    ):
        parser.error(
            "--sitl requires a SITL profile using the MAVLink protocol"
        )
    INTEGRATED_C2 = not args.legacy_windows
    USE_VISPY  = not args.no_vispy and args.legacy_windows
    USE_SITL   = args.sitl
    _SITL_ADDR = args.sitl_addr
    _SITL_PORT = args.sitl_port
    ML_MODEL    = args.ml_model
    ML_ABSOLUTE_ACTIONS = args.ml_absolute_actions
    CAMERA_MODEL = args.camera_model
    ML_DEVICE = args.ml_device
    RENDER_BACKEND = args.render_backend
    if ML_DEVICE == "cuda":
        try:
            import torch
        except ImportError:
            parser.error("--ml-device cuda requires PyTorch")
        if not torch.cuda.is_available():
            parser.error(
                "--ml-device cuda requested, but this PyTorch build has no CUDA"
            )
    TELEMETRY_UDP = args.telemetry_udp
    TELEMETRY_RECORD = args.telemetry_record
    MISSION_RECORD_DIR = args.mission_record_dir
    USE_CAMERA_PERCEPTION = (
        INTEGRATED_C2 or args.camera_perception or bool(args.camera_model)
    )

    state_q = mp.Queue(maxsize=2)
    ctrl_q  = mp.Queue(maxsize=20)

    dash_proc = mp.Process(
        target=_dashboard_worker,
        args=(state_q, ctrl_q, _DOME_RADIUS, args.capture_ui_dir),
        daemon=True,
        name="dashboard",
    )
    dash_proc.start()
    if args.auto_start:
        ctrl_q.put({
            "selected_mission": "shahed136",
            "selected_pattern": "direct",
            "selected_pad": "mid",
            "initial_speed": 1.0,
            "paused": False,
            "stopped": False,
        })

    try:
        if USE_VISPY:
            from vispy import app as vispy_app
            from viz.vispy_renderer import SimRenderer

            shared_state = {}
            state_lock   = threading.Lock()

            phys_thread = threading.Thread(
                target=_mission_loop,
                args=(state_q, ctrl_q, dash_proc, shared_state, state_lock),
                daemon=True,
                name="physics",
            )
            phys_thread.start()

            renderer = SimRenderer(shared_state, state_lock, dome_radius=_DOME_RADIUS)
            timer    = vispy_app.Timer(interval=1/60, connect=renderer.update, start=True)
            vispy_app.run()  # blocks — OpenGL owns main thread

            shared_state["app_quit"] = True
            phys_thread.join(timeout=4)
        else:
            if args.swarm_live:
                _run_swarm_mission(
                    args.swarm_live, telemetry_udp=args.telemetry_udp,
                    state_q=state_q, ctrl_q=ctrl_q,
                )
            else:
                _mission_loop(state_q, ctrl_q, dash_proc)

    except KeyboardInterrupt:
        print("\n[SIM] Interrupted by user.")
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
