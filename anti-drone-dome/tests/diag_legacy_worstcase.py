"""
Diagnostic: legacy guidance, fpv_attack / spiral / mid_pad — the worst case.

Runs ONE engagement with _LegacyGuidance only, captures the interceptor's
position, velocity, and range at every step, then prints a plain-language
trajectory summary and writes a Tacview ACMI so the failure mode can be
inspected visually.

Same seed and parameters as tests/test_apn_comparison.py uses for this
scenario (seed = 1000 + 200 + 20 + 1 = 1221), so the trajectory here is
exactly the one that produced the 748 m miss in the matrix run.
"""

import math
import os
import sys
from datetime import datetime

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from tests.test_apn_comparison import (
    _KinematicIntruder,
    _PointMassInterceptor,
    _DT, _MAX_T, _LAUNCH_DELAY, _DOME_RADIUS,
)
from guidance.intercept import _LegacyGuidance
from sensors.radar     import RadarNode
from scenarios         import ATTACK_PATTERNS, INTRUDER_TYPES, get_waypoints_for_path
from config            import HOME_LAT, HOME_LON


SCENARIO = ("fpv_attack", "spiral", 180.0)   # intruder, pattern, pad_off (mid)
SEED     = 1221


# ──────────────────────────────────────────────────────────────────────────
# ACMI emitter — minimal, decoupled from viz/acmi_writer.py so we don't
# pull in main.py's import graph.
# ──────────────────────────────────────────────────────────────────────────
class _MiniACMI:
    _M_PER_DEG = 111111.0

    def __init__(self, path: str):
        self._f = open(path, "w", encoding="utf-8")
        self._f.write("FileType=text/acmi/tabular\n")
        self._f.write("FileVersion=2.0\n")
        self._f.write("0,ReferenceTime=2024-01-01T00:00:00Z\n")
        self._f.write(f"0,ReferenceLatitude={HOME_LAT}\n")
        self._f.write(f"0,ReferenceLongitude={HOME_LON}\n")
        self._f.write("0,Title=Legacy Guidance Worst Case (fpv/spiral/mid)\n")
        self._f.write("0,Author=DefenderProject\n")
        self._f.write("1,Name=Intruder,Type=Air+FixedWing,Color=Red,Coalition=Enemies\n")
        self._f.write("2,Name=Interceptor,Type=Air+Rotorcraft,Color=Blue,Coalition=Allies\n")
        self._f.write("3,Name=Pad,Type=Ground+Static,Color=Blue,Coalition=Allies\n")
        self._f.write("4,Name=DomeCenter,Type=Ground+Static,Color=Green,Coalition=Allies\n")
        self.path = path

    def _ll(self, p):
        lat = HOME_LAT + (p[1] / self._M_PER_DEG)
        lon = HOME_LON + (p[0] / self._M_PER_DEG)
        return lat, lon, max(0.0, float(p[2]))

    def static(self, oid: int, p):
        lat, lon, alt = self._ll(p)
        self._f.write(f"#0.00\n{oid},T={lon:.6f}|{lat:.6f}|{alt:.1f}\n")

    def frame(self, t: float, intr_pos, int_pos, int_launched: bool):
        self._f.write(f"#{t:.2f}\n")
        lat, lon, alt = self._ll(intr_pos)
        self._f.write(f"1,T={lon:.6f}|{lat:.6f}|{alt:.1f}\n")
        if int_launched:
            lat, lon, alt = self._ll(int_pos)
            self._f.write(f"2,T={lon:.6f}|{lat:.6f}|{alt:.1f}\n")

    def close(self):
        self._f.flush()
        self._f.close()


# ──────────────────────────────────────────────────────────────────────────
# Trajectory phases (for the plain-language report)
# ──────────────────────────────────────────────────────────────────────────
def _classify_trajectory(samples):
    """samples: list of (t, intr_pos, int_pos, range, int_speed, lead_deg)."""
    rs = [s[3] for s in samples]
    if not rs:
        return "no data"

    # Range trajectory
    r_min      = min(rs)
    r_min_idx  = rs.index(r_min)
    r_min_t    = samples[r_min_idx][0]
    r_max      = max(rs)
    r_max_idx  = rs.index(r_max)
    r_max_t    = samples[r_max_idx][0]
    r_first    = rs[0]
    r_last     = rs[-1]

    # Interceptor speed
    speeds   = [s[4] for s in samples]
    spd_max  = max(speeds)
    spd_end  = speeds[-1]

    # Lead angle (degrees off the LOS)
    leads    = [s[5] for s in samples]
    lead_max = max(leads)

    # Did the interceptor reverse?  Compute cumulative path length /
    # straight-line distance to see if it overshot and turned around.
    path_len  = 0.0
    for i in range(1, len(samples)):
        a = samples[i - 1][2]
        b = samples[i][2]
        path_len += float(np.linalg.norm(b - a))
    line_len  = float(np.linalg.norm(samples[-1][2] - samples[0][2]))
    sinuosity = path_len / max(line_len, 1.0)

    # Final position relative to dome (origin in ENU)
    fp = samples[-1][2]
    fp_r = float(np.linalg.norm(fp[:2]))
    fp_alt = float(fp[2])

    # Intruder final position
    ip = samples[-1][1]

    return {
        "r_first":   r_first,
        "r_min":     r_min,
        "r_min_t":   r_min_t,
        "r_max":     r_max,
        "r_max_t":   r_max_t,
        "r_last":    r_last,
        "spd_max":   spd_max,
        "spd_end":   spd_end,
        "lead_max":  lead_max,
        "path_len":  path_len,
        "line_len":  line_len,
        "sinuosity": sinuosity,
        "int_final_xy": fp_r,
        "int_final_z":  fp_alt,
        "int_final":    fp,
        "intr_final":   ip,
    }


# ──────────────────────────────────────────────────────────────────────────
# Engagement with logging
# ──────────────────────────────────────────────────────────────────────────
def run(scenario, seed, out_dir):
    import random
    random.seed(seed)
    np.random.seed(seed)

    intr_key, pat_key, pad_off = scenario
    intr_def    = INTRUDER_TYPES[intr_key]
    pat_def     = ATTACK_PATTERNS[pat_key]
    waypoints   = get_waypoints_for_path(pat_def["path"])
    intruder    = _KinematicIntruder(waypoints, intr_def["max_speed"], pat_def["start"])
    pad_pos     = (0.0, -(_DOME_RADIUS + pad_off), 1.0)
    interceptor = _PointMassInterceptor(pad_pos)

    radar = RadarNode(
        station_pos      = (0.0, 0.0, 10.0),
        protected_center = (0.0, 0.0, 0.0),
        max_range        = 1500.0,
        elev_max_deg     = 75.0,
        min_vel          = 0.8,
        noise_std        = 0.5,
    )

    guidance = _LegacyGuidance()
    rcs      = float(intr_def["rcs"])

    os.makedirs(out_dir, exist_ok=True)
    acmi_path = os.path.join(out_dir, f"legacy_{intr_key}_{pat_key}_mid.acmi")
    csv_path  = os.path.join(out_dir, f"legacy_{intr_key}_{pat_key}_mid.csv")
    acmi      = _MiniACMI(acmi_path)
    acmi.static(3, pad_pos)
    acmi.static(4, (0, 0, 0))

    csv = open(csv_path, "w", encoding="utf-8")
    csv.write("t,intr_x,intr_y,intr_z,int_x,int_y,int_z,int_vx,int_vy,int_vz,range,int_speed,lead_deg,launched\n")

    samples       = []      # post-launch only
    miss_distance = float("inf")
    miss_time     = 0.0
    launched      = False
    detect_time   = None
    sim_t         = 0.0
    frame_every   = int(round(0.05 / _DT))   # 20 Hz acmi/csv
    step          = 0

    while sim_t < _MAX_T:
        intruder.step(_DT)

        scan = radar.scan(tuple(intruder.pos), target_rcs=rcs)
        if scan.get("detected") and detect_time is None:
            detect_time = sim_t
        track = scan if scan.get("detected") else radar.get_last_track()

        if (not launched) and detect_time is not None and \
                sim_t - detect_time >= _LAUNCH_DELAY:
            launched = True

        if launched and track:
            setpoint = guidance.compute_guidance(interceptor.get_state(), track)
            interceptor.step(setpoint, _DT)

            r = float(np.linalg.norm(interceptor.pos - intruder.pos))
            if r < miss_distance:
                miss_distance = r
                miss_time     = sim_t

            # Lead angle: degrees between interceptor velocity and LOS to
            # intruder. 0° = pursuing perfectly; 90° = flying sideways
            # relative to the target.
            v   = interceptor.vel
            spd = float(np.linalg.norm(v))
            r_v = intruder.pos - interceptor.pos
            rng = float(np.linalg.norm(r_v))
            if spd > 0.5 and rng > 0.5:
                cos_a    = float(np.clip(np.dot(v / spd, r_v / rng), -1.0, 1.0))
                lead_deg = math.degrees(math.acos(cos_a))
            else:
                lead_deg = 0.0

            samples.append((
                sim_t,
                intruder.pos.copy(),
                interceptor.pos.copy(),
                r,
                spd,
                lead_deg,
            ))

        if step % frame_every == 0:
            acmi.frame(sim_t, intruder.pos, interceptor.pos, launched)
            csv.write(
                f"{sim_t:.3f},"
                f"{intruder.pos[0]:.2f},{intruder.pos[1]:.2f},{intruder.pos[2]:.2f},"
                f"{interceptor.pos[0]:.2f},{interceptor.pos[1]:.2f},{interceptor.pos[2]:.2f},"
                f"{interceptor.vel[0]:.2f},{interceptor.vel[1]:.2f},{interceptor.vel[2]:.2f},"
            )
            if samples:
                last = samples[-1]
                csv.write(f"{last[3]:.2f},{last[4]:.2f},{last[5]:.2f},")
            else:
                csv.write(",,,")
            csv.write(f"{int(launched)}\n")

        sim_t += _DT
        step  += 1

    acmi.close()
    csv.close()

    launch_t = (detect_time + _LAUNCH_DELAY) if detect_time is not None else None
    return {
        "miss":        miss_distance,
        "miss_time":   miss_time,
        "detect_t":    detect_time,
        "launch_t":    launch_t,
        "acmi":        acmi_path,
        "csv":         csv_path,
        "samples":     samples,
        "intr_start":  pat_def["start"],
        "pad_pos":     pad_pos,
    }


# ──────────────────────────────────────────────────────────────────────────
def main():
    out_dir = os.path.join(os.path.dirname(__file__), "..", "missions", "diag")
    out_dir = os.path.normpath(out_dir)
    res = run(SCENARIO, SEED, out_dir)
    info = _classify_trajectory(res["samples"])

    print()
    print("=" * 72)
    print("LEGACY GUIDANCE — WORST-CASE DIAGNOSTIC")
    print(f"Scenario: intruder={SCENARIO[0]}  pattern={SCENARIO[1]}  pad_off={SCENARIO[2]} m")
    print(f"Seed: {SEED}   miss = {res['miss']:.2f} m  at  t = {res['miss_time']:.2f} s")
    print("=" * 72)
    print(f"Radar first detected the target  : t = {res['detect_t']:.2f} s")
    print(f"Interceptor launched             : t = {res['launch_t']:.2f} s")
    print(f"Intruder spawn                   : {res['intr_start']}")
    print(f"Interceptor pad                  : {res['pad_pos']}")
    print(f"Engagement window (post-launch)  : {len(res['samples'])} samples")
    print()
    print("Range trajectory (interceptor -> intruder):")
    print(f"  first frame post-launch  : {info['r_first']:>8.1f} m")
    print(f"  minimum (closest pass)   : {info['r_min']:>8.1f} m  at t = {info['r_min_t']:.2f} s")
    print(f"  maximum                  : {info['r_max']:>8.1f} m  at t = {info['r_max_t']:.2f} s")
    print(f"  final frame              : {info['r_last']:>8.1f} m")
    print()
    print("Interceptor kinematics:")
    print(f"  peak speed               : {info['spd_max']:>8.1f} m/s")
    print(f"  final speed              : {info['spd_end']:>8.1f} m/s")
    print(f"  peak lead angle off LOS  : {info['lead_max']:>8.1f} °")
    print(f"  path length flown        : {info['path_len']:>8.1f} m")
    print(f"  straight-line dist       : {info['line_len']:>8.1f} m")
    print(f"  sinuosity (path/line)    : {info['sinuosity']:>8.2f}  (1.0 = straight)")
    print()
    print(f"Final positions:")
    print(f"  interceptor : ({info['int_final'][0]:8.1f}, {info['int_final'][1]:8.1f}, {info['int_final'][2]:8.1f})  | xy from dome: {info['int_final_xy']:.1f} m")
    print(f"  intruder    : ({info['intr_final'][0]:8.1f}, {info['intr_final'][1]:8.1f}, {info['intr_final'][2]:8.1f})")
    print()
    print(f"ACMI : {res['acmi']}")
    print(f"CSV  : {res['csv']}")


if __name__ == "__main__":
    main()
