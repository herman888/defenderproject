"""Test: placeholder FC inside sim/drone.py — accepts GuidanceSetpoint and
drives the airframe correctly without crashing PyBullet.

Two tiers:
  1. Pure helper `placeholder_fc_accel_enu` — no PyBullet, fast.
  2. `Drone.apply_setpoint` — DIRECT-mode PyBullet, validates the integration.
"""

import math
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pybullet
import pybullet_data

from config             import INTERCEPTOR_MASS, PLACEHOLDER_FC_KV
from guidance.setpoint  import GuidanceSetpoint, ned_to_enu
from sim.drone          import Drone, placeholder_fc_accel_enu


def _vmag(v):
    return math.sqrt(sum(c * c for c in v))


# ── Tier 1: pure helper ────────────────────────────────────────────
def _test_helper(results):
    # Empty setpoint → zero command (caller decides fallback).
    a = placeholder_fc_accel_enu(GuidanceSetpoint(), (0.0, 0.0, 0.0))
    results.append(("helper: empty setpoint → zero accel",
                    a == (0.0, 0.0, 0.0), f"a={a}"))

    # Pure accel setpoint: NED (1, 0, 0) = +north → ENU (0, 1, 0) = +north,
    # plus FC gravity comp (0, 0, 9.81).
    sp = GuidanceSetpoint(accel=(1.0, 0.0, 0.0))
    a  = placeholder_fc_accel_enu(sp, (0.0, 0.0, 0.0))
    results.append(("helper: NED accel north → ENU y + gravity comp",
                    abs(a[0]) < 1e-9 and abs(a[1] - 1.0) < 1e-9
                    and abs(a[2] - 9.81) < 1e-9,
                    f"a={a}"))

    # k_v defaults to 0 in Stage A → velocity setpoint contributes nothing
    # to accel; only gravity comp survives.
    sp = GuidanceSetpoint(velocity=(10.0, 0.0, 0.0))
    a  = placeholder_fc_accel_enu(sp, (0.0, 0.0, 0.0))
    results.append(("helper: velocity-only with k_v=0 → gravity comp only",
                    PLACEHOLDER_FC_KV == 0.0
                    and abs(a[0]) < 1e-9 and abs(a[1]) < 1e-9
                    and abs(a[2] - 9.81) < 1e-9,
                    f"a={a}, k_v={PLACEHOLDER_FC_KV}"))

    # Explicit non-zero k_v → velocity error contributes proportionally.
    sp = GuidanceSetpoint(velocity=(5.0, 0.0, 0.0))   # NED north 5 m/s
    a  = placeholder_fc_accel_enu(sp, (0.0, 0.0, 0.0), k_v=2.0)
    # v_des_enu = (0, 5, 0); a = 2.0·((0,5,0)-(0,0,0)) + (0,0,9.81) = (0, 10, 9.81)
    results.append(("helper: k_v=2.0 with v_des=NED(5,0,0) → ENU (0,10,9.81)",
                    abs(a[0]) < 1e-9 and abs(a[1] - 10.0) < 1e-9
                    and abs(a[2] - 9.81) < 1e-9,
                    f"a={a}"))

    # Vel + accel combined.
    sp = GuidanceSetpoint(velocity=(0.0, 0.0, 0.0), accel=(0.0, 1.0, 0.0))
    a  = placeholder_fc_accel_enu(sp, (0.0, 0.0, 0.0), k_v=1.0)
    # accel NED east → ENU (1, 0, 0); velocity contributes 0 (k_v·0 = 0).
    results.append(("helper: vel+accel combine correctly",
                    abs(a[0] - 1.0) < 1e-9 and abs(a[1]) < 1e-9
                    and abs(a[2] - 9.81) < 1e-9,
                    f"a={a}"))


# ── Tier 2: Drone.apply_setpoint (DIRECT PyBullet) ─────────────────
def _test_drone(results):
    client = pybullet.connect(pybullet.DIRECT)
    pybullet.setAdditionalSearchPath(pybullet_data.getDataPath(),
                                      physicsClientId=client)
    pybullet.setGravity(0, 0, -9.81, physicsClientId=client)
    pybullet.setTimeStep(1.0 / 240.0, physicsClientId=client)
    pybullet.loadURDF("plane.urdf", physicsClientId=client)

    try:
        drone = Drone("fc_test", (0, 0, 5), client, color="blue")
    except Exception as e:
        results.append(("Drone constructs for FC test", False, str(e)))
        pybullet.disconnect(client)
        return
    results.append(("Drone constructs for FC test", True))

    # Empty setpoint → no-op.
    pos_before  = drone.get_position()
    drone.apply_setpoint(GuidanceSetpoint())
    pybullet.stepSimulation(physicsClientId=client)
    pos_after_empty = drone.get_position()
    drift = _vmag(tuple(pos_after_empty[i] - pos_before[i] for i in range(3)))
    # One step of free-fall: 0.5·9.81·(1/240)² ≈ 8.5e-5 m. Anything < 1e-3 m
    # confirms no force was applied (drone falls under gravity only).
    results.append(("apply_setpoint(empty) is no-op (free fall only)",
                    drift < 1e-3,
                    f"drift={drift:.6f} m"))

    # None setpoint also no-ops.
    try:
        drone.apply_setpoint(None)
        results.append(("apply_setpoint(None) is no-op", True))
    except Exception as e:
        results.append(("apply_setpoint(None) is no-op", False, str(e)))

    # Invalid frame raises.
    bad = GuidanceSetpoint(frame="GLOBAL_INT", accel=(0.0, 0.0, 1.0))
    try:
        drone.apply_setpoint(bad)
        results.append(("apply_setpoint rejects non-LOCAL_NED frame",
                        False, "no exception raised"))
    except ValueError:
        results.append(("apply_setpoint rejects non-LOCAL_NED frame", True))
    except Exception as e:
        results.append(("apply_setpoint rejects non-LOCAL_NED frame",
                        False, f"wrong exception: {e!r}"))

    # Position-only setpoint routes through update() — should update _target.
    sp_pos = GuidanceSetpoint(position=(10.0, 0.0, -5.0))   # NED north 10, down 5
    drone.apply_setpoint(sp_pos)
    tgt = drone._target
    expected = ned_to_enu((10.0, 0.0, -5.0))   # ENU east 0, north 10, up 5
    results.append(("position-only setpoint updates Drone._target",
                    all(abs(tgt[i] - expected[i]) < 1e-9 for i in range(3)),
                    f"target={tgt}, expected={expected}"))

    # Accel setpoint: command +north accel, then run for 0.5 s and verify
    # the airframe gained roughly the predicted northward velocity.
    # Command magnitude well under MAX_ACCEL so saturation isn't a factor.
    drone2 = Drone("fc_kin", (0, 0, 10), client, color="red")
    a_cmd_north = 5.0   # m/s², NED north
    sp_acc = GuidanceSetpoint(accel=(a_cmd_north, 0.0, 0.0))
    for _ in range(120):   # 0.5 s at 240 Hz
        drone2.apply_setpoint(sp_acc)
        pybullet.stepSimulation(physicsClientId=client)
    v = drone2.get_velocity()
    # Net ENU accel after gravity cancels: (0, a_cmd_north, 0). Expected
    # vy ≈ 5 · 0.5 = 2.5 m/s. Allow 20% slack for tilt-induced spillover.
    vy_ok = 1.5 < v[1] < 3.5 and abs(v[0]) < 1.0
    results.append(("accel setpoint produces predicted ENU velocity",
                    vy_ok, f"v={tuple(round(c, 3) for c in v)}"))

    # Mass field is populated from URDF / config.
    results.append(("Drone._mass_kg is populated",
                    getattr(drone, "_mass_kg", 0.0) > 0.0,
                    f"mass={getattr(drone, '_mass_kg', None)}"))

    pybullet.disconnect(client)


def run_tests():
    results = []
    _test_helper(results)
    _test_drone(results)

    print("\n=== test_placeholder_fc.py ===")
    for item in results:
        name, passed = item[0], item[1]
        detail = item[2] if len(item) > 2 else ""
        status = "PASS" if passed else "FAIL"
        print(f"  [{status}] {name}" + (f" ({detail})" if detail else ""))


if __name__ == "__main__":
    run_tests()
