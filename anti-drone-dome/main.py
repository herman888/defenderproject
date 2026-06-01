"""
Anti-Drone Dome Simulation — main entry point.

BEFORE:
  - Radar at dome centre, raw finite-difference velocity (noise 100s m/s)
  - Pure pursuit guidance, MAX_FORCE 25 N
  - Interceptor spawned at dome centre (0,0,0.5)
  - Interceptor same speed/force as intruder

AFTER:
  - Radar station at south perimeter (0,-10,3), Kalman-filtered tracks,
    60-deg elevation cone, 0.5 m/s clutter fence
  - Augmented Proportional Navigation (N=4), MAX_FORCE 60 N
  - Interceptor teleported to perimeter edge 90-deg offset from threat
    bearing at launch time for optimal PN geometry
  - Interceptor: max_h/v_force=40 N, max_speed=30 m/s (2x intruder)

Threading model: physics runs in daemon thread; matplotlib stays on main
thread (required by TkAgg/Tkinter on Windows).
"""

import math
import time
import threading

import pybullet

from sim.physics import PhysicsWorld
from sim.drone import Drone
from sim.waypoints import WaypointNavigator
from sensors.radar import RadarNode
from comms.datalink import DataLink
from guidance.intercept import PurePursuitGuidance
from dome.killzone import DomeKillZone
from viz.dashboard import Dashboard, SimControl

_TIMESTEP    = 1.0 / 240.0
_MAX_SIM_TIME = 120.0
_DOME_CENTER = (0.0, 0.0, 0.0)
_DOME_RADIUS = 10.0
_LOG_INTERVAL = 48


def _perimeter_launch_pos(threat_pos: tuple, dome_radius: float) -> list:
    """
    Compute interceptor launch position.
    Place at half dome radius (inside dome), 90-deg offset from threat bearing.
    Half radius keeps the interceptor close to the intercept corridor while
    the 90-deg offset gives APN the lateral separation it needs.
    """
    bearing = math.atan2(threat_pos[1], threat_pos[0])
    launch_bearing = bearing - math.pi / 2.0
    launch_r = dome_radius * 0.5                        # inside dome, not edge
    x = launch_r * math.cos(launch_bearing)
    y = launch_r * math.sin(launch_bearing)
    return [x, y, 2.0]


def run_sim(sim_control: SimControl, state_bag: dict):
    """Physics simulation thread — no matplotlib calls."""

    print("=" * 60)
    print("  ANTI-DRONE DOME SIMULATION — INITIALIZING")
    print("=" * 60)

    world = PhysicsWorld(gui=False)
    world.draw_dome(_DOME_CENTER, _DOME_RADIUS, color=[0, 1, 0])

    # Intruder: default speed (15 m/s, 15/20 N force limits)
    intruder = Drone("intruder", (15.0, 15.0, 8.0), world.client, color="red")

    # Interceptor: 2x faster, higher force authority
    # Parked at south perimeter until launch teleport fires
    interceptor = Drone(
        "interceptor", (0.0, -_DOME_RADIUS, 0.3), world.client, color="blue",
        max_h_force=40.0, max_v_force=40.0, max_speed=30.0, kp=15.0, kd=7.0,
    )
    interceptor_launched = False

    for _ in range(50):
        world.step()

    nav         = WaypointNavigator()

    # Radar: physical station on south perimeter at 3 m AGL
    radar = RadarNode(
        station_pos      = (0.0, -_DOME_RADIUS, 3.0),
        protected_center = _DOME_CENTER,
        max_range        = 38.0,    # extended for earlier detection (was 25m)
        elev_max_deg     = 60.0,
        min_vel          = 0.5,
        noise_std        = 0.15,
    )

    broadcaster = DataLink(role="broadcast", port=14550)
    guidance    = PurePursuitGuidance()       # now APN internally
    dome        = DomeKillZone(center=_DOME_CENTER, radius=_DOME_RADIUS)

    sim_start        = time.time()
    step             = 0
    pending_events   = []
    mission_result   = None
    closest_approach = float("inf")
    interceptor_target = None

    print("SIMULATION STARTED — intruder begins attack run\n")

    while True:
        if sim_control.stopped:
            mission_result = "ABORTED"
            break

        while sim_control.paused and not sim_control.stopped:
            time.sleep(0.05)

        sim_time = step * _TIMESTEP
        if sim_time >= _MAX_SIM_TIME:
            mission_result = "TIMEOUT"
            break

        # --- Intruder navigation ---
        nav.update(intruder.get_position())
        intruder.set_target(*nav.get_current_target())
        intruder.update()

        # --- Radar scan (Kalman-filtered track) ---
        i_pos        = intruder.get_position()
        radar_return = radar.scan(i_pos)

        # --- MAVLink broadcast (velocity now in scan result, no extra call) ---
        if radar_return.get("detected"):
            broadcaster.send_track(radar_return)

        # --- Dome status ---
        int_pos = interceptor.get_position() if interceptor_launched else None
        dome.update_status(
            intruder_position   = i_pos,
            intruder_detected   = radar_return.get("detected", False),
            interceptor_position= int_pos,
            intercept_radius    = 5.0,  # 5 m kill radius (net/jammer range)
        )
        status = dome.get_status()

        if status == "BREACH":
            world.draw_dome(_DOME_CENTER, _DOME_RADIUS, color=[1, 0, 0])
        elif status == "TRACKING":
            world.draw_dome(_DOME_CENTER, _DOME_RADIUS, color=[1, 1, 0])

        # --- Interceptor launch: teleport to optimal perimeter position ---
        if status in ("TRACKING", "BREACH") and not interceptor_launched:
            launch_pos = _perimeter_launch_pos(i_pos, _DOME_RADIUS)
            pybullet.resetBasePositionAndOrientation(
                interceptor._body, launch_pos, [0, 0, 0, 1],
                physicsClientId=world.client,
            )
            pybullet.resetBaseVelocity(
                interceptor._body, [0, 0, 0], [0, 0, 0],
                physicsClientId=world.client,
            )
            interceptor._prev_error = [0.0, 0.0, 0.0]
            interceptor.set_target(*launch_pos)

            print(f"INTERCEPTOR: LAUNCH from perimeter "
                  f"({launch_pos[0]:.1f}, {launch_pos[1]:.1f}, {launch_pos[2]:.1f}) "
                  f"— APN guidance active")
            interceptor_launched = True
            pending_events.append("Interceptor launched")

        # --- APN guidance + external force ---
        # Coast on last Kalman estimate if radar temporarily loses lock
        guidance_track = (radar_return if radar_return.get("detected")
                          else radar.get_last_track())

        if interceptor_launched:
            interceptor.update()
            if guidance_track:
                f = guidance.compute_guidance(interceptor.get_state(), guidance_track)
                i_body_pos = interceptor.get_position()
                pybullet.applyExternalForce(
                    interceptor._body, -1, list(f), list(i_body_pos),
                    pybullet.WORLD_FRAME, physicsClientId=world.client,
                )
                interceptor_target = guidance_track.get("position_estimate")

            int_pos = interceptor.get_position()
            sep = math.sqrt(sum((int_pos[k] - i_pos[k])**2 for k in range(3)))
            if sep < closest_approach:
                closest_approach = sep

        # --- Terminal conditions ---
        if status == "INTERCEPTED":
            mission_result = "INTERCEPTED"
            break

        # FAILURE: intruder reached final waypoint inside dome (check horizontal dist)
        horiz_dist = math.sqrt(i_pos[0]**2 + i_pos[1]**2)
        if horiz_dist < 2.0 and nav.is_complete():
            mission_result = "FAILURE"
            break

        # --- Console log ---
        if step % _LOG_INTERVAL == 0:
            int_dist_str = "--"
            if interceptor_launched:
                int_pos_now = interceptor.get_position()
                d = math.sqrt(sum((int_pos_now[k]-i_pos[k])**2 for k in range(3)))
                int_dist_str = f"{d:.1f}m"
            rng = radar_return.get("range", 0.0) if radar_return.get("detected") else 0.0
            print(f"T+{sim_time:5.1f}s | INTRUDER ({i_pos[0]:.1f},{i_pos[1]:.1f},{i_pos[2]:.1f}) "
                  f"| RADAR {rng:.1f}m | {status:10s} | INT {int_dist_str}")

        # --- Push state to dashboard ---
        int_v     = interceptor.get_velocity() if interceptor_launched else (0,0,0)
        int_speed = math.sqrt(sum(v**2 for v in int_v))
        i_v       = intruder.get_velocity()
        i_speed   = math.sqrt(sum(v**2 for v in i_v))

        tti_val = float("inf")
        if interceptor_launched and radar_return.get("detected"):
            tti_val = guidance.time_to_intercept(interceptor.get_state(), radar_return)

        state_bag["sim_state"] = {
            "dome_status"       : status,
            "intruder_pos"      : i_pos,
            "interceptor_pos"   : interceptor.get_position() if interceptor_launched else None,
            "radar_return"      : radar_return,
            "radar_station"     : radar.station_pos.tolist(),
            "predicted_intercept": interceptor_target,
            "intruder_speed"    : i_speed,
            "interceptor_speed" : int_speed,
            "tti"               : tti_val,
            "track_confidence"  : radar.track_confidence(),
            "last_detection_time": radar.last_detection_time,
            "events"            : pending_events,
        }
        pending_events = []

        # Speed control
        spd = sim_control.speed
        if spd == 0:
            if step % 2 == 0:
                world.step()
            step += 1
        elif spd == 2:
            world.step()
            world.step()
            step += 2
        else:
            world.step()
            step += 1

    # --- Mission report ---
    total_time = step * _TIMESTEP
    print("\n" + "=" * 60)
    print(f"  MISSION COMPLETE — Result: {mission_result}")
    print("=" * 60)
    print(f"  Simulation time:         {total_time:.1f} s")

    fdt = dome.first_detection_time
    bt  = dome.breach_time
    it  = dome.intercept_time

    print(f"  First detection:         "
          f"{(fdt - sim_start):.1f} s" if fdt else "  First detection:         Never")
    print(f"  Dome breach:             "
          f"{(bt - sim_start):.1f} s"  if bt  else "  Dome breach:             None")
    if it and mission_result == "INTERCEPTED":
        print(f"  Time to intercept:       {(it - sim_start):.1f} s")
    else:
        print(f"  Outcome:                 {mission_result}")
    print(f"  Max penetration depth:   {dome.max_penetration_depth():.1f} m")
    print(f"  Closest approach:        {closest_approach:.1f} m")
    print("=" * 60)

    try:
        pybullet.disconnect(world.client)
    except Exception:
        pass
    broadcaster.close()
    state_bag["done"] = True


def main():
    import matplotlib.pyplot as plt

    sim_control = SimControl()
    state_bag   = {"sim_state": None, "done": False}

    try:
        dashboard = Dashboard(dome_radius=_DOME_RADIUS, sim_control=sim_control)
    except Exception as e:
        print(f"WARNING: Dashboard failed ({e}), running headless")
        dashboard = None

    sim_thread = threading.Thread(
        target=run_sim, args=(sim_control, state_bag), daemon=True
    )
    sim_thread.start()

    while not state_bag["done"] and not sim_control.stopped:
        state = state_bag.get("sim_state")
        if dashboard and state:
            dashboard.update(state)
        else:
            try:
                plt.pause(0.05)
            except Exception:
                break

    sim_thread.join(timeout=3)
    if dashboard:
        dashboard.close()


if __name__ == "__main__":
    main()
