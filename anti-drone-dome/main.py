"""
Anti-Drone Dome Simulation
Full system: intruder drone, ground radar, MAVLink data link,
interceptor drone with pure pursuit guidance, kill zone logic,
real-time dashboard visualization.

Run: python main.py
"""

import math
import sys
import time
import os
import threading

import pybullet
import pybullet_data

from sim.physics import PhysicsWorld
from sim.drone import Drone
from sim.waypoints import WaypointNavigator
from sensors.radar import RadarNode
from comms.datalink import DataLink
from guidance.intercept import PurePursuitGuidance
from dome.killzone import DomeKillZone
from viz.dashboard import Dashboard, SimControl

_TIMESTEP = 1.0 / 240.0
_MAX_SIM_TIME = 120.0
_DOME_CENTER = (0.0, 0.0, 0.0)
_DOME_RADIUS = 10.0
_LOG_INTERVAL = 48


def run_sim(sim_control, state_bag):
    """Physics simulation — runs in a background thread, no matplotlib calls."""
    print("=" * 60)
    print("  ANTI-DRONE DOME SIMULATION — INITIALIZING")
    print("=" * 60)

    try:
        world = PhysicsWorld(gui=True)
    except Exception as e:
        print(f"WARNING: GUI failed ({e}), switching to DIRECT mode")
        world = PhysicsWorld(gui=False)

    world.draw_dome(_DOME_CENTER, _DOME_RADIUS, color=[0, 1, 0])

    intruder    = Drone("intruder",    (15.0, 15.0, 8.0), world.client, color="red")
    interceptor = Drone("interceptor", (0.0, 0.0, 0.5),   world.client, color="blue")
    interceptor_launched = False

    for _ in range(50):
        world.step()

    nav         = WaypointNavigator()
    radar       = RadarNode(protected_center=_DOME_CENTER, max_range=20.0, noise_std=0.3)
    broadcaster = DataLink(role="broadcast", port=14550)
    guidance    = PurePursuitGuidance()
    dome        = DomeKillZone(center=_DOME_CENTER, radius=_DOME_RADIUS)

    sim_start        = time.time()
    step             = 0
    pending_events   = []
    mission_result   = None
    closest_approach = float("inf")
    interceptor_target = None

    print("SIMULATION STARTED — intruder begins attack run\n")

    while True:
        # Stop button
        if sim_control.stopped:
            mission_result = "ABORTED"
            break

        # Pause — wait without doing any physics
        while sim_control.paused and not sim_control.stopped:
            time.sleep(0.05)

        sim_time = step * _TIMESTEP

        if sim_time >= _MAX_SIM_TIME:
            mission_result = "TIMEOUT"
            break

        # --- Intruder navigation ---
        nav.update(intruder.get_position())
        wp = nav.get_current_target()
        intruder.set_target(*wp)
        intruder.update()

        # --- Radar scan ---
        i_pos = intruder.get_position()
        radar_return = radar.scan(i_pos)

        # --- MAVLink broadcast ---
        if radar_return.get("detected"):
            vel_est = radar.get_track_velocity()
            radar_return["velocity"] = vel_est
            broadcaster.send_track(radar_return)

        # --- Dome status ---
        int_pos = interceptor.get_position() if interceptor_launched else None
        dome.update_status(
            intruder_position=i_pos,
            intruder_detected=radar_return.get("detected", False),
            interceptor_position=int_pos,
            intercept_radius=3.0,
        )
        status = dome.get_status()

        if status == "BREACH":
            world.draw_dome(_DOME_CENTER, _DOME_RADIUS, color=[1, 0, 0])
        elif status == "TRACKING":
            world.draw_dome(_DOME_CENTER, _DOME_RADIUS, color=[1, 1, 0])

        # --- Interceptor launch ---
        if status in ("TRACKING", "BREACH") and not interceptor_launched:
            print("INTERCEPTOR: LAUNCH — beginning pursuit")
            interceptor_launched = True
            pending_events.append("Interceptor launched")

        # --- Interceptor guidance ---
        if interceptor_launched:
            interceptor.update()
            if radar_return.get("detected"):
                track = dict(radar_return)
                f = guidance.compute_guidance(interceptor.get_state(), track)
                i_body_pos = interceptor.get_position()
                pybullet.applyExternalForce(
                    interceptor._body, -1, list(f), list(i_body_pos),
                    pybullet.WORLD_FRAME, physicsClientId=world.client,
                )
                interceptor_target = track.get("position_estimate")

            int_pos = interceptor.get_position()
            sep = math.sqrt(sum((int_pos[i] - i_pos[i]) ** 2 for i in range(3)))
            if sep < closest_approach:
                closest_approach = sep

        # --- Terminal conditions ---
        if status == "INTERCEPTED":
            mission_result = "INTERCEPTED"
            break

        center_dist = math.sqrt(sum(i_pos[i] ** 2 for i in range(3)))
        if center_dist < 1.5 and nav.is_complete():
            mission_result = "FAILURE"
            break

        # --- Console log ---
        if step % _LOG_INTERVAL == 0:
            int_dist_str = "—"
            if interceptor_launched:
                int_pos_now = interceptor.get_position()
                int_dist = math.sqrt(sum((int_pos_now[i] - i_pos[i]) ** 2 for i in range(3)))
                int_dist_str = f"{int_dist:.1f}m"
            rng = radar_return.get("range", 0.0) if radar_return.get("detected") else 0.0
            print(f"T+{sim_time:5.1f}s | INTRUDER: ({i_pos[0]:.1f},{i_pos[1]:.1f},{i_pos[2]:.1f}) | "
                  f"RADAR: {rng:.1f}m | DOME: {status:10s} | INTERCEPTOR: {int_dist_str} to target")

        # --- Push state to dashboard (thread-safe via simple dict) ---
        int_v = interceptor.get_velocity() if interceptor_launched else (0, 0, 0)
        int_speed = math.sqrt(sum(v**2 for v in int_v))
        i_v = intruder.get_velocity()
        i_speed = math.sqrt(sum(v**2 for v in i_v))

        tti_val = float("inf")
        if interceptor_launched and radar_return.get("detected"):
            tti_val = guidance.time_to_intercept(interceptor.get_state(), radar_return)

        state_bag["sim_state"] = {
            "dome_status": status,
            "intruder_pos": i_pos,
            "interceptor_pos": interceptor.get_position() if interceptor_launched else None,
            "radar_return": radar_return,
            "predicted_intercept": interceptor_target,
            "intruder_speed": i_speed,
            "interceptor_speed": int_speed,
            "tti": tti_val,
            "track_confidence": radar.track_confidence(),
            "last_detection_time": radar.last_detection_time,
            "events": pending_events,
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
    print(f"  Simulation time:        {total_time:.1f}s")

    fdt = dome.first_detection_time
    bt  = dome.breach_time
    it  = dome.intercept_time

    if fdt:
        print(f"  Time to first detection: {fdt - sim_start:.1f}s")
    else:
        print("  Time to first detection: Never detected")

    if bt:
        print(f"  Time to dome breach:     {bt - sim_start:.1f}s")
    else:
        print("  Time to dome breach:     No breach")

    if it and mission_result == "INTERCEPTED":
        print(f"  Time to intercept:       {it - sim_start:.1f}s")
    else:
        print(f"  Outcome:                 {mission_result}")

    print(f"  Max penetration depth:   {dome.max_penetration_depth():.1f}m")
    print(f"  Closest approach:        {closest_approach:.1f}m")
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

    # Dashboard runs on main thread (required by TkAgg/Tkinter on Windows)
    try:
        dashboard = Dashboard(dome_radius=_DOME_RADIUS, sim_control=sim_control)
    except Exception as e:
        print(f"WARNING: Dashboard failed ({e}), running headless")
        dashboard = None

    # Physics sim runs on a background thread
    sim_thread = threading.Thread(target=run_sim, args=(sim_control, state_bag), daemon=True)
    sim_thread.start()

    # Main thread: pump matplotlib events and update dashboard at ~20 Hz
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
