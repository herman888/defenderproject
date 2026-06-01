"""
Anti-Drone Dome Simulation — main entry point.

BEFORE:
  - Physics in background thread, matplotlib on main thread
  - PyBullet GUI crashed (OpenGL needs main thread on Windows)
  - No physical radar model in the 3D scene

AFTER:
  - PyBullet GUI runs on main process / main thread (correct)
  - Matplotlib dashboard runs in a separate child PROCESS (has its own
    main thread so TkAgg/Tkinter is happy)
  - Communication via multiprocessing.Queue (state → dash, ctrl ← dash)
  - Physical radar station URDF loaded and spinning dish driven at 20 RPM
  - PyBullet debug sliders for speed/pause control inside the 3D window

Run: python main.py
"""

import math
import os
import time
import multiprocessing as mp

import pybullet
import pybullet_data

from sim.physics import PhysicsWorld
from sim.drone import Drone
from sim.waypoints import WaypointNavigator
from sensors.radar import RadarNode
from comms.datalink import DataLink
from guidance.intercept import PurePursuitGuidance
from dome.killzone import DomeKillZone

_TIMESTEP     = 1.0 / 240.0
_MAX_SIM_TIME = 120.0
_DOME_CENTER  = (0.0, 0.0, 0.0)
_DOME_RADIUS  = 10.0
_LOG_INTERVAL = 48
_RADAR_RPM    = 20.0                          # dish rotation speed
_RADAR_OMEGA  = _RADAR_RPM / 60.0 * 2 * math.pi   # rad/s


# ---------------------------------------------------------------------------
# Dashboard subprocess entry point  (must be top-level for Windows spawn)
# ---------------------------------------------------------------------------

def _dashboard_worker(state_q: mp.Queue, ctrl_q: mp.Queue, dome_radius: float):
    """
    Runs in a child process — owns matplotlib/TkAgg on its own main thread.
    Reads sim state from state_q, writes control signals to ctrl_q.
    """
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
        # Drain queue — only keep the freshest state
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
            _time.sleep(0.015)   # cap CPU burn; flush_events inside update() handles Tk
        else:
            try:
                plt.pause(0.05)  # keep window alive when idle
            except Exception:
                return

        # Push control snapshot back to main process
        try:
            ctrl_q.put_nowait({
                "paused" : ctrl.paused,
                "stopped": ctrl.stopped,
                "speed"  : ctrl.speed,
            })
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _find_joint(body: int, name: str, client: int) -> int:
    for i in range(pybullet.getNumJoints(body, physicsClientId=client)):
        info = pybullet.getJointInfo(body, i, physicsClientId=client)
        if info[1].decode() == name:
            return i
    return -1


def _load_radar_station(dome_radius: float, client: int) -> tuple[int, int]:
    """Load radar_station.urdf, return (body_id, spin_joint_index)."""
    urdf = os.path.normpath(
        os.path.join(os.path.dirname(__file__), "assets", "radar_station.urdf")
    )
    body = pybullet.loadURDF(
        urdf,
        basePosition=[0.0, -dome_radius, 0.1],   # south perimeter, base sits on ground
        useFixedBase=1,
        physicsClientId=client,
    )
    spin_idx = _find_joint(body, "spin_joint", client)
    return body, spin_idx


def _perimeter_launch_pos(threat_pos: tuple, dome_radius: float) -> list:
    """
    Interceptor launch point: half dome radius, 90-deg offset from threat
    bearing for good APN lateral separation.
    """
    bearing        = math.atan2(threat_pos[1], threat_pos[0])
    launch_bearing = bearing - math.pi / 2.0
    r              = dome_radius * 0.5
    return [r * math.cos(launch_bearing), r * math.sin(launch_bearing), 2.0]


# ---------------------------------------------------------------------------
# Main simulation (runs on main process / main thread — owns PyBullet GUI)
# ---------------------------------------------------------------------------

def _run_sim(state_q: mp.Queue, ctrl_q: mp.Queue, dash_proc_holder: list):
    import sys
    # Force line-buffered output (safe fallback if reconfigure unavailable)
    try:
        sys.stdout.reconfigure(line_buffering=True)
    except Exception:
        pass
    print("=" * 60, flush=True)
    print("  ANTI-DRONE DOME SIMULATION — INITIALIZING", flush=True)
    print("=" * 60, flush=True)

    print("Connecting to PyBullet...", flush=True)
    world = PhysicsWorld(gui=True)
    world.draw_dome(_DOME_CENTER, _DOME_RADIUS, color=[0, 1, 0])
    print("PyBullet ready. Starting dashboard...", flush=True)

    # Start dashboard AFTER PyBullet GUI is up — avoids the race where the
    # child process imports pybullet while the parent is still connecting,
    # which caused a segfault / empty scene on Windows.
    dash_proc = mp.Process(
        target=_dashboard_worker,
        args=(state_q, ctrl_q, _DOME_RADIUS),
        daemon=True,
        name="dashboard",
    )
    dash_proc.start()
    dash_proc_holder.append(dash_proc)
    print("Dashboard started. Loading scene objects...", flush=True)

    # ── Physical radar station ──────────────────────────────────────────
    radar_body, spin_joint = _load_radar_station(_DOME_RADIUS, world.client)
    if spin_joint >= 0:
        pybullet.setJointMotorControl2(
            radar_body, spin_joint,
            pybullet.VELOCITY_CONTROL,
            targetVelocity=_RADAR_OMEGA,
            force=5.0,
            physicsClientId=world.client,
        )

    # Label above the station
    pybullet.addUserDebugText(
        "RADAR STATION", [0, -_DOME_RADIUS, 4.2],
        [0.2, 1.0, 0.2], textSize=1.2, physicsClientId=world.client,
    )

    # ── HUD text IDs (updated each frame) ───────────────────────────────
    _hud_status  = pybullet.addUserDebugText("STATUS: CLEAR",      [-14, -14, 12], [0,1,0],   textSize=2.0, physicsClientId=world.client)
    _hud_intruder= pybullet.addUserDebugText("INTRUDER: ---",      [-14, -14, 10], [1,0.3,0], textSize=1.5, physicsClientId=world.client)
    _hud_intercept=pybullet.addUserDebugText("INTERCEPTOR: ---",   [-14, -14,  8], [0,0.8,1], textSize=1.5, physicsClientId=world.client)
    _hud_sep     = pybullet.addUserDebugText("SEP: ---",           [-14, -14,  6], [1,1,0],   textSize=1.5, physicsClientId=world.client)

    # ── Drones ──────────────────────────────────────────────────────────
    intruder = Drone("intruder", (15.0, 15.0, 8.0), world.client, color="red",
                     max_h_force=25.0, max_speed=12.0)  # faster intruder
    # Interceptor sits on a launch pad inside the dome (not on the radar station)
    # No hover force applied until launch, so gravity holds it on the ground.
    interceptor = Drone(
        "interceptor", (3.0, -3.0, 0.3), world.client, color="blue",
        max_h_force=70.0, max_v_force=70.0, max_speed=50.0, kp=20.0, kd=8.0,
    )
    interceptor_launched = False

    for _ in range(50):
        world.step()

    nav     = WaypointNavigator()
    radar   = RadarNode(
        station_pos      = (0.0, -_DOME_RADIUS, 3.0),
        protected_center = _DOME_CENTER,
        max_range        = 38.0,
        elev_max_deg     = 60.0,
        min_vel          = 0.5,
        noise_std        = 0.15,
    )
    broadcaster = DataLink(role="broadcast", port=14550)
    guidance    = PurePursuitGuidance()
    dome        = DomeKillZone(center=_DOME_CENTER, radius=_DOME_RADIUS)

    sim_start        = time.time()
    step             = 0
    pending_events   = []
    mission_result   = None
    closest_approach = float("inf")
    interceptor_target = None
    _last_dome_status = "CLEAR"   # initial dome already drawn green above

    # Control state read from dashboard process
    ctrl = {"paused": False, "stopped": False, "speed_mult": 4.0}

    print("SIMULATION STARTED — intruder begins attack run\n")

    while True:
        # ── Read dashboard controls (non-blocking) ──────────────────────
        while True:
            try:
                msg = ctrl_q.get_nowait()
                ctrl.update(msg)
            except Exception:
                break

        # ── Check PyBullet GUI still alive (every 120 steps) ────────────
        if step % 120 == 0:
            try:
                pybullet.getConnectionInfo(world.client)
            except Exception:
                mission_result = "ABORTED"
                break

        if ctrl["stopped"]:
            mission_result = "ABORTED"
            break

        if ctrl["paused"]:
            time.sleep(0.05)
            continue

        sim_time = step * _TIMESTEP
        if sim_time >= _MAX_SIM_TIME:
            mission_result = "TIMEOUT"
            break

        # ── Intruder navigation — cache position to avoid duplicate IPC ─
        i_pos = intruder.get_position()
        nav.update(i_pos)
        intruder.set_target(*nav.get_current_target())
        intruder.update()

        # ── Radar scan ──────────────────────────────────────────────────
        radar_return = radar.scan(i_pos)

        # Broadcast every 2 s of sim time — not every frame (was 240x/s)
        if radar_return.get("detected") and step % 480 == 0:
            broadcaster.send_track(radar_return)

        # ── Dome status ─────────────────────────────────────────────────
        int_pos = interceptor.get_position() if interceptor_launched else None
        dome.update_status(
            intruder_position    = i_pos,
            intruder_detected    = radar_return.get("detected", False),
            interceptor_position = int_pos,
            intercept_radius     = 5.0,
        )
        status = dome.get_status()

        if status != _last_dome_status:
            _dome_colors = {"CLEAR":[0,1,0],"TRACKING":[1,1,0],"BREACH":[1,0.5,0],"INTERCEPTED":[1,0,0]}
            try:
                world.draw_dome(_DOME_CENTER, _DOME_RADIUS, color=_dome_colors.get(status,[0,1,0]))
            except pybullet.error:
                mission_result = "ABORTED"
                break
            _last_dome_status = status

        # ── Interceptor launch ──────────────────────────────────────────
        if status in ("TRACKING", "BREACH") and not interceptor_launched:
            launch_pos = list(interceptor.get_position())
            # Kick toward intruder to immediately break ground contact and
            # give APN a head start — horizontal toward threat + upward.
            dx = i_pos[0] - launch_pos[0]
            dy = i_pos[1] - launch_pos[1]
            dist_h = max(math.sqrt(dx**2 + dy**2), 0.1)
            kick = [18.0 * dx / dist_h, 18.0 * dy / dist_h, 8.0]
            pybullet.resetBaseVelocity(
                interceptor._body, kick, [0, 0, 0],
                physicsClientId=world.client,
            )
            interceptor._prev_error = [0.0, 0.0, 0.0]
            print(f"INTERCEPTOR: LAUNCH from pad "
                  f"({launch_pos[0]:.1f}, {launch_pos[1]:.1f}, {launch_pos[2]:.1f}) — APN active")
            interceptor_launched = True
            int_pos = interceptor.get_position()   # cache valid for this step
            pending_events.append("Interceptor launched")

        # ── APN guidance ────────────────────────────────────────────────
        guidance_track = (radar_return if radar_return.get("detected")
                          else radar.get_last_track())
        if interceptor_launched:
            if guidance_track:
                # Sync PD target to intruder position so PD *assists* APN
                # instead of fighting it (both point toward the intruder).
                t_pos = guidance_track.get("position_estimate")
                if t_pos:
                    interceptor.set_target(*t_pos)
            interceptor.update()
            if guidance_track:
                f = guidance.compute_guidance(interceptor.get_state(), guidance_track)
                try:
                    pybullet.applyExternalForce(
                        interceptor._body, -1, list(f), list(int_pos),
                        pybullet.WORLD_FRAME, physicsClientId=world.client,
                    )
                except pybullet.error:
                    mission_result = "ABORTED"
                    break
                interceptor_target = guidance_track.get("position_estimate")

            sep = math.sqrt(sum((int_pos[k]-i_pos[k])**2 for k in range(3)))
            if sep < closest_approach:
                closest_approach = sep

        # ── Terminal conditions ─────────────────────────────────────────
        if status == "INTERCEPTED":
            mission_result = "INTERCEPTED"
            break

        horiz = math.sqrt(i_pos[0]**2 + i_pos[1]**2)
        if horiz < 2.0 and nav.is_complete():
            mission_result = "FAILURE"
            break

        # ── PyBullet HUD update ─────────────────────────────────────────
        if step % 48 == 0:
            status_colors = {"CLEAR":[0,1,0],"TRACKING":[1,1,0],"BREACH":[1,0.5,0],"INTERCEPTED":[1,0,0]}
            sc = status_colors.get(status, [1,1,1])
            try:
                _hud_status   = pybullet.addUserDebugText(f"STATUS: {status}", [-14,-14,12], sc, textSize=2.0, replaceItemUniqueId=_hud_status, physicsClientId=world.client)
                rng_str = f"{radar_return.get('range',0):.1f}m" if radar_return.get("detected") else "---"
                _hud_intruder = pybullet.addUserDebugText(f"INTRUDER  ({i_pos[0]:.1f},{i_pos[1]:.1f},{i_pos[2]:.1f})  rng:{rng_str}", [-14,-14,10], [1,0.3,0], textSize=1.5, replaceItemUniqueId=_hud_intruder, physicsClientId=world.client)
                if interceptor_launched:
                    ip  = int_pos
                    d   = math.sqrt(sum((ip[k]-i_pos[k])**2 for k in range(3)))
                    tti = guidance.time_to_intercept(interceptor.get_state(), guidance_track) if guidance_track else float("inf")
                    tti_str = f"{tti:.1f}s" if tti < 999 else "---"
                    _hud_intercept = pybullet.addUserDebugText(f"INTERCEPTOR ({ip[0]:.1f},{ip[1]:.1f},{ip[2]:.1f})", [-14,-14,8], [0,0.8,1], textSize=1.5, replaceItemUniqueId=_hud_intercept, physicsClientId=world.client)
                    _hud_sep       = pybullet.addUserDebugText(f"SEP: {d:.1f}m  TTI: {tti_str}", [-14,-14,6], [1,1,0], textSize=1.5, replaceItemUniqueId=_hud_sep, physicsClientId=world.client)
                else:
                    _hud_intercept = pybullet.addUserDebugText("INTERCEPTOR: on pad — awaiting launch", [-14,-14,8], [0,0.8,1], textSize=1.5, replaceItemUniqueId=_hud_intercept, physicsClientId=world.client)
            except Exception:
                pass  # never let HUD errors crash the sim

        # ── Console log ─────────────────────────────────────────────────
        if step % _LOG_INTERVAL == 0:
            rng = radar_return.get("range", 0.0) if radar_return.get("detected") else 0.0
            sep_str = "--"
            if interceptor_launched:
                sep_str = f"{math.sqrt(sum((int_pos[k]-i_pos[k])**2 for k in range(3))):.1f}m"
            print(f"T+{sim_time:5.1f}s | INTRUDER ({i_pos[0]:.1f},{i_pos[1]:.1f},{i_pos[2]:.1f})"
                  f" | RADAR {rng:.1f}m | {status:10s} | INT {sep_str}")

        # ── Push state to dashboard process ─────────────────────────────
        int_v = interceptor.get_velocity() if interceptor_launched else (0,0,0)
        i_v   = intruder.get_velocity()
        tti   = float("inf")
        if interceptor_launched and radar_return.get("detected"):
            tti = guidance.time_to_intercept(interceptor.get_state(), radar_return)

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
            })
        except Exception:
            pass   # queue full — dashboard is behind, skip frame
        pending_events = []

        # ── Physics step — no sleep, run at max CPU speed ────────────────
        # Forces are applied once per loop iteration so physics must only
        # step ONCE here. Removing sleep lets the CPU run freely (~1000+
        # steps/sec = 4-8x real time naturally on modern hardware).
        world.step()
        step += 1

    # ── Mission report ───────────────────────────────────────────────────
    total = step * _TIMESTEP
    print("\n" + "=" * 60)
    print(f"  MISSION COMPLETE — {mission_result}")
    print("=" * 60)
    print(f"  Sim time:          {total:.1f} s")
    fdt, bt, it = dome.first_detection_time, dome.breach_time, dome.intercept_time
    print(f"  First detection:   {(fdt-sim_start):.1f} s" if fdt else "  First detection:   Never")
    print(f"  Dome breach:       {(bt-sim_start):.1f} s"  if bt  else "  Dome breach:       None")
    if it and mission_result == "INTERCEPTED":
        print(f"  Time to intercept: {(it-sim_start):.1f} s")
    print(f"  Closest approach:  {closest_approach:.1f} m")
    print("=" * 60)

    try:
        pybullet.disconnect(world.client)
    except Exception:
        pass
    broadcaster.close()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    mp.freeze_support()

    state_q         = mp.Queue(maxsize=2)
    ctrl_q          = mp.Queue(maxsize=20)
    dash_proc_holder = []   # filled inside _run_sim after PyBullet connects

    try:
        _run_sim(state_q, ctrl_q, dash_proc_holder)
    except Exception as e:
        import traceback
        print(f"SIM CRASH: {e}", flush=True)
        traceback.print_exc()
    finally:
        try:
            state_q.put_nowait("QUIT")
        except Exception:
            pass
        for dp in dash_proc_holder:
            dp.join(timeout=4)
            if dp.is_alive():
                dp.terminate()


if __name__ == "__main__":
    main()
