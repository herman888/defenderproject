"""Test: drone loading, hover control, waypoint navigation, state fields."""

import sys
import os
import math
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pybullet
import pybullet_data
from sim.drone import Drone
from sim.waypoints import WaypointNavigator


def run_tests():
    client = pybullet.connect(pybullet.DIRECT)
    pybullet.setAdditionalSearchPath(pybullet_data.getDataPath(), physicsClientId=client)
    pybullet.setGravity(0, 0, -9.81, physicsClientId=client)
    pybullet.setTimeStep(1.0 / 240.0, physicsClientId=client)
    pybullet.loadURDF("plane.urdf", physicsClientId=client)

    results = []

    # Test 1: Drone loads without crashing
    try:
        drone = Drone("test", (0, 0, 5), client, color="blue")
        results.append(("Drone loads without crashing", True))
    except Exception as e:
        results.append(("Drone loads without crashing", False, str(e)))
        pybullet.disconnect(client)
        _print_results(results)
        return

    # Test 2: Hover controller maintains altitude within 0.5m after 5 seconds
    drone.set_target(0, 0, 5)
    for _ in range(240 * 5):
        drone.update()
        pybullet.stepSimulation(physicsClientId=client)
    pos = drone.get_position()
    alt_ok = abs(pos[2] - 5.0) < 0.5
    results.append(("Hover altitude within 0.5m after 5s", alt_ok,
                    f"altitude={pos[2]:.2f}"))

    # Test 3: Waypoint navigation reaches target within 2m
    drone2 = Drone("nav_test", (0, 0, 5), client, color="red")
    drone2.set_target(3, 3, 5)
    for _ in range(240 * 10):
        drone2.update()
        pybullet.stepSimulation(physicsClientId=client)
    pos2 = drone2.get_position()
    dist = math.sqrt((pos2[0] - 3) ** 2 + (pos2[1] - 3) ** 2 + (pos2[2] - 5) ** 2)
    results.append(("Waypoint navigation within 2m", dist < 2.0, f"dist={dist:.2f}"))

    # Test 4: get_state() has required fields
    state = drone.get_state()
    required = {"position", "velocity", "orientation", "timestamp", "target", "speed"}
    has_fields = required.issubset(set(state.keys()))
    results.append(("get_state() returns all required fields", has_fields,
                    f"keys={set(state.keys())}"))

    pybullet.disconnect(client)
    _print_results(results)


def _print_results(results):
    print("\n=== test_drone.py ===")
    for item in results:
        name, passed = item[0], item[1]
        detail = item[2] if len(item) > 2 else ""
        status = "PASS" if passed else "FAIL"
        print(f"  [{status}] {name}" + (f" ({detail})" if detail else ""))


if __name__ == "__main__":
    run_tests()
