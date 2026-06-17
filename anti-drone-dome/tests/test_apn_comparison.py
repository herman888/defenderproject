"""
APN vs legacy guidance — A/B comparison across the full scenario matrix
(3 intruder types × 3 attack patterns × 3 pad offsets = 27 engagements).

For each scenario we run the engagement under both guidance laws with the
same RNG seed, so any delta in miss distance is purely attributable to the
guidance law (the radar measurement sequence depends only on the kinematic
intruder's path, which is identical across both runs).

This is a deterministic mini-sim — it intentionally avoids PyBullet so the
suite runs in seconds.  Interceptor is a point mass with an inlined
Stage-A placeholder FC: guidance now outputs a GuidanceSetpoint in NED
frame (raw m/s², no gravity comp), the FC layer converts to ENU, adds
vertical gravity comp, caps to MAX_ACCEL, and integrates.
"""

import math
import os
import random
import sys

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from config              import MAX_ACCEL
from guidance.intercept  import PurePursuitGuidance, _LegacyGuidance
from guidance.setpoint   import ned_to_enu
from sensors.radar       import RadarNode
from scenarios           import (
    ATTACK_PATTERNS,
    INTRUDER_TYPES,
    PAD_OFFSETS,
    get_waypoints_for_path,
)

_DT           = 1.0 / 240.0
_MAX_T        = 60.0          # s — engagement time budget
_MAX_INT_R    = 3000.0        # m — interceptor-from-dome safety stop
_DOME_RADIUS  = 200.0
_V_CAP        = 70.0          # m/s — interceptor airframe speed cap
_LAUNCH_DELAY = 0.5           # s after first detection (radar lock buildup)
_WP_THRESH    = 5.0           # m — kinematic waypoint advance threshold


# ──────────────────────────────────────────────────────────────────────────
# Kinematic waypoint-following intruder
# ──────────────────────────────────────────────────────────────────────────
class _KinematicIntruder:
    """Constant-speed waypoint follower.  Once final waypoint is reached,
    continues on the last heading (so the interceptor still has a target)."""

    def __init__(self, waypoints: list, speed: float, start: tuple):
        self._wps    = [np.array(w, dtype=float) for w in waypoints]
        self._idx    = 0
        self.pos     = np.array(start, dtype=float)
        self._spd    = float(speed)
        self._last_v = np.zeros(3)

    @property
    def velocity(self) -> np.ndarray:
        return self._last_v.copy()

    def step(self, dt: float) -> None:
        if self._idx >= len(self._wps):
            self.pos += self._last_v * dt
            return
        target = self._wps[self._idx]
        delta  = target - self.pos
        dist   = float(np.linalg.norm(delta))
        if dist < _WP_THRESH:
            self._idx += 1
            return
        self._last_v = (delta / dist) * self._spd
        self.pos    += self._last_v * dt


# ──────────────────────────────────────────────────────────────────────────
# Point-mass interceptor + inlined Stage-A FC
# ──────────────────────────────────────────────────────────────────────────
class _PointMassInterceptor:
    """Consumes GuidanceSetpoint.accel (NED).  Inlines the placeholder FC's
    job: NED → ENU, add gravity comp, cap to MAX_ACCEL, integrate."""

    def __init__(self, pad_pos: tuple):
        self.pos = np.array(pad_pos, dtype=float)
        self.vel = np.zeros(3)

    def get_state(self) -> dict:
        return {"position": tuple(self.pos), "velocity": tuple(self.vel)}

    def step(self, setpoint, dt: float) -> None:
        if setpoint is None or setpoint.is_empty or setpoint.accel is None:
            thrust_enu = np.zeros(3)
        else:
            thrust_enu = np.array(ned_to_enu(setpoint.accel), dtype=float)

        # Placeholder FC adds vertical gravity compensation — guidance now
        # commands thrust direction only, the FC keeps the airframe airborne.
        thrust_enu[2] += 9.81
        mag = float(np.linalg.norm(thrust_enu))
        if mag > MAX_ACCEL:
            thrust_enu *= MAX_ACCEL / mag

        # Total acceleration = thrust (incl. gravity comp) + gravity.
        total_accel = thrust_enu + np.array([0.0, 0.0, -9.81])
        self.vel   += total_accel * dt
        spd = float(np.linalg.norm(self.vel))
        if spd > _V_CAP:
            self.vel *= _V_CAP / spd
        self.pos += self.vel * dt


# ──────────────────────────────────────────────────────────────────────────
# Single engagement
# ──────────────────────────────────────────────────────────────────────────
def _run_engagement(intruder_key: str, pattern_key: str, pad_off: float,
                    guidance, seed: int) -> dict:
    random.seed(seed)
    np.random.seed(seed)

    intr_def    = INTRUDER_TYPES[intruder_key]
    pattern_def = ATTACK_PATTERNS[pattern_key]
    waypoints   = get_waypoints_for_path(pattern_def["path"])
    intruder    = _KinematicIntruder(waypoints, intr_def["max_speed"],
                                     pattern_def["start"])

    pad_pos     = (0.0, -(_DOME_RADIUS + pad_off), 1.0)
    interceptor = _PointMassInterceptor(pad_pos)

    # Radar config matches main.py production setup.
    radar = RadarNode(
        station_pos      = (0.0, 0.0, 10.0),
        protected_center = (0.0, 0.0, 0.0),
        max_range        = 1500.0,
        elev_max_deg     = 75.0,
        min_vel          = 0.8,
        noise_std        = 0.5,
    )

    rcs           = float(intr_def["rcs"])
    miss_distance = float("inf")
    launched      = False
    detect_time   = None
    sim_t         = 0.0

    # Run the full time budget and track the minimum range observed once
    # launched.  No early-stop on "range increasing" — maneuvering targets
    # (e.g. SPIRAL) produce mid-engagement range fluctuations that would
    # otherwise cut the run short before the true closest approach.
    while sim_t < _MAX_T:
        intruder.step(_DT)

        scan = radar.scan(tuple(intruder.pos), target_rcs=rcs)
        if scan.get("detected") and detect_time is None:
            detect_time = sim_t
        track = scan if scan.get("detected") else radar.get_last_track()

        if (not launched) and detect_time is not None \
                and sim_t - detect_time >= _LAUNCH_DELAY:
            launched = True

        if launched and track:
            setpoint = guidance.compute_guidance(interceptor.get_state(), track)
            interceptor.step(setpoint, _DT)

            r = float(np.linalg.norm(interceptor.pos - intruder.pos))
            if r < miss_distance:
                miss_distance = r

            # Safety stop: interceptor flew off into the distance.
            int_r = float(np.linalg.norm(interceptor.pos))
            if int_r > _MAX_INT_R:
                break

        sim_t += _DT

    return {
        "miss"     : miss_distance,
        "launched" : launched,
        "sim_t"    : sim_t,
        "detect_t" : detect_time,
    }


# ──────────────────────────────────────────────────────────────────────────
# Main test entry
# ──────────────────────────────────────────────────────────────────────────
def run_tests():
    intruder_keys = ["shahed136", "consumer_quad", "fpv_attack"]
    pattern_keys  = ["direct", "nap_earth", "spiral"]
    pad_keys      = list(PAD_OFFSETS.keys())   # near, mid, far

    rows          = []
    apn_better    = 0
    apn_eq        = 0
    legacy_better = 0
    deltas        = []

    # Use fixed seeds (not hash()-based) so results are stable across runs.
    for s_idx, ikey in enumerate(intruder_keys):
        for p_idx, pkey in enumerate(pattern_keys):
            for k_idx, padk in enumerate(pad_keys):
                pad_off = PAD_OFFSETS[padk]
                seed    = 1000 + s_idx * 100 + p_idx * 10 + k_idx

                print(f"  running {ikey:<14} {pkey:<10} {padk:<5} ...",
                      flush=True)

                legacy = _run_engagement(ikey, pkey, pad_off,
                                         _LegacyGuidance(), seed)
                apn    = _run_engagement(ikey, pkey, pad_off,
                                         PurePursuitGuidance(N_prime=4.0), seed)

                delta = apn["miss"] - legacy["miss"]
                rows.append((ikey, pkey, padk, legacy["miss"],
                             apn["miss"], delta, apn["launched"]))
                if math.isfinite(delta):
                    deltas.append(delta)

                if apn["miss"] < legacy["miss"] - 0.1:
                    apn_better += 1
                elif apn["miss"] > legacy["miss"] + 0.1:
                    legacy_better += 1
                else:
                    apn_eq += 1

    # ── Results table ────────────────────────────────────────────────────
    print("\n=== test_apn_comparison.py ===")
    print(f"  {'intruder':<14} {'pattern':<10} {'pad':<5} "
          f"{'legacy':>9} {'apn':>9} {'delta':>9}")
    print("  " + "-" * 60)
    for ikey, pkey, padk, legacy_m, apn_m, delta, launched in rows:
        if not launched:
            print(f"  {ikey:<14} {pkey:<10} {padk:<5}     "
                  f"NO LAUNCH (radar never acquired)")
            continue
        marker = "  " if abs(delta) < 0.1 else ("v " if delta < 0 else "^ ")
        print(f"  {ikey:<14} {pkey:<10} {padk:<5} "
              f"{legacy_m:>9.2f} {apn_m:>9.2f} {marker}{delta:>+7.2f}")
    print("  " + "-" * 60)

    n          = len(rows)
    mean_delta = sum(deltas) / len(deltas) if deltas else 0.0
    best_delta = min(deltas) if deltas else 0.0
    print(f"  APN better: {apn_better}/{n}   "
          f"equal: {apn_eq}/{n}   legacy better: {legacy_better}/{n}")
    print(f"  Mean delta (apn - legacy): {mean_delta:+.2f} m   "
          f"max improvement: {best_delta:+.2f} m")

    # ── Pass criteria ────────────────────────────────────────────────────
    # Two checks:
    #   1. Mean miss across the whole matrix is lower under APN.
    #   2. Catastrophic failures (legacy misses by >50 m) are recovered by
    #      APN (within 10 m).  This is the primary motivation for APN —
    #      maneuvering / low-RCS targets where the legacy law diverges.
    legacy_means = [r[3] for r in rows if math.isfinite(r[3])]
    apn_means    = [r[4] for r in rows if math.isfinite(r[4])]
    legacy_mean  = sum(legacy_means) / len(legacy_means) if legacy_means else 0.0
    apn_mean     = sum(apn_means)    / len(apn_means)    if apn_means    else 0.0

    catastrophic = [(r[0], r[1], r[2], r[3], r[4])
                    for r in rows if r[3] > 50.0]
    recovered    = [c for c in catastrophic if c[4] < 10.0]

    results = []
    results.append(("APN mean miss < legacy mean miss", apn_mean < legacy_mean,
                    f"apn={apn_mean:.1f} m, legacy={legacy_mean:.1f} m"))
    if catastrophic:
        recovery_ok = len(recovered) >= int(0.8 * len(catastrophic))
        results.append(("APN recovers >=80% of legacy catastrophic failures",
                        recovery_ok,
                        f"{len(recovered)}/{len(catastrophic)} recovered"))
    else:
        results.append(("No catastrophic legacy failures to recover",
                        True, ""))

    print()
    for item in results:
        name, passed = item[0], item[1]
        detail = item[2] if len(item) > 2 else ""
        status = "PASS" if passed else "FAIL"
        print(f"  [{status}] {name}" + (f" ({detail})" if detail else ""))


if __name__ == "__main__":
    run_tests()
