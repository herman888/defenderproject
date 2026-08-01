"""Test: guidance emits GuidanceSetpoint with correct shape per phase.

Stage A contract (see guidance/intercept.py and guidance/setpoint.py):
  - No track detected            → GuidanceSetpoint() (is_empty)
  - Mid-course (rng > _R_TAPER)  → velocity + accel feed-forward + yaw, NED
  - Terminal   (rng <= _R_TERM)  → accel only, free yaw
  - |accel| <= MAX_ACCEL in every phase
  - adaptive mid-course speed remains inside the bounded command envelope
  - frame == "LOCAL_NED" always
"""

import math
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from config             import INTERCEPT_CONTACT_RADIUS_M, MAX_ACCEL
from guidance.intercept import PurePursuitGuidance, _V_INT, _R_TAPER, _R_TERM
from guidance.setpoint  import GuidanceSetpoint


def _vmag(v):
    return math.sqrt(sum(c * c for c in v))


def run_tests():
    guidance = PurePursuitGuidance()
    results  = []

    # ── Mid-course scenario: target well outside taper radius ─────────
    interceptor_mid = {
        "position": (0.0, 0.0, 5.0),
        "velocity": (1.0, 0.5, 0.0),
    }
    target_mid = {
        "detected"          : True,
        "position_estimate" : (60.0, 45.0, 5.0),   # rng ≈ 75 m  >> _R_TAPER
        "velocity"          : (-1.0, 0.0, 0.0),
    }
    sp_mid = guidance.compute_guidance(interceptor_mid, target_mid)

    results.append(("Mid-course returns GuidanceSetpoint",
                    isinstance(sp_mid, GuidanceSetpoint)))
    results.append(("Mid-course frame == LOCAL_NED",
                    sp_mid.frame == "LOCAL_NED"))
    results.append(("Mid-course populates velocity",
                    sp_mid.velocity is not None))
    results.append(("Mid-course populates accel feed-forward",
                    sp_mid.accel is not None))
    results.append(("Mid-course populates yaw",
                    sp_mid.yaw is not None))
    if sp_mid.velocity is not None:
        v_mag = _vmag(sp_mid.velocity)
        results.append((f"Mid-course |v| adaptively bounded <= {_V_INT:.0f}",
                        35.0 <= v_mag <= _V_INT,
                        f"|v|={v_mag:.2f} m/s"))
        results.append(("Adaptive guidance publishes diagnostics",
                        guidance.last_diagnostics["mode"] == "ADAPTIVE_APN"
                        and 3.0 <= guidance.last_diagnostics["navigation_gain"] <= 6.2
                        and abs(
                            guidance.last_diagnostics["command_speed_mps"] - v_mag
                        ) < 1e-6))
    if sp_mid.accel is not None:
        a_mag = _vmag(sp_mid.accel)
        results.append(("Mid-course |a| <= MAX_ACCEL",
                        a_mag <= MAX_ACCEL + 1e-6,
                        f"|a|={a_mag:.2f} m/s², cap={MAX_ACCEL:.2f}"))

    # ── Terminal scenario: target inside terminal radius ──────────────
    interceptor_term = {
        "position": (0.0, 0.0, 5.0),
        "velocity": (1.0, 0.5, 0.0),
    }
    target_term = {
        "detected"          : True,
        "position_estimate" : (8.0, 6.0, 5.0),    # rng = 10 m  <  _R_TERM
        "velocity"          : (-1.0, 0.0, 0.0),
    }
    sp_term = guidance.compute_guidance(interceptor_term, target_term)
    rng_term = math.sqrt(8.0**2 + 6.0**2)
    assert rng_term < _R_TERM, "scenario should be in terminal phase"

    results.append(("Terminal returns accel-only",
                    sp_term.accel is not None
                    and sp_term.velocity is None
                    and sp_term.position is None))
    results.append(("Terminal yaw == None (free yaw)",
                    sp_term.yaw is None))
    results.append(("Terminal controller uses the 1 m physical contact gate",
                    guidance.last_diagnostics["terminal_contact_radius_m"]
                    == INTERCEPT_CONTACT_RADIUS_M == 1.0))
    results.append(("Terminal controller commands a non-zero closing speed",
                    guidance.last_diagnostics["terminal_desired_closing_mps"] > 0.0))
    if sp_term.accel is not None:
        ax, ay, _az = sp_term.accel
        # NED accel: x=north, y=east. ENU pos (8,6,0) → NED LOS = (north=6, east=8).
        # Terminal accel = _TERM_THRUST_ACCEL · r_hat_NED → ax>0 (north), ay>0 (east).
        results.append(("Terminal accel points toward target (NED LOS)",
                        ax > 0 and ay > 0,
                        f"accel_NED=({ax:.2f},{ay:.2f},{_az:.2f})"))
        results.append(("Terminal |a| <= MAX_ACCEL",
                        _vmag(sp_term.accel) <= MAX_ACCEL + 1e-6,
                        f"|a|={_vmag(sp_term.accel):.2f}"))

    # ── No-detection scenario: setpoint is empty ──────────────────────
    sp_none = guidance.compute_guidance(interceptor_mid, {"detected": False})
    results.append(("No-detection returns is_empty setpoint",
                    isinstance(sp_none, GuidanceSetpoint) and sp_none.is_empty))

    # ── TTI and lead angle (unchanged signatures) ─────────────────────
    tti = guidance.time_to_intercept(interceptor_mid, target_mid)
    results.append(("TTI positive and finite",
                    0 < tti < 60.0,
                    f"tti={tti:.2f}s"))
    lead = guidance.lead_angle_deg(interceptor_mid, target_mid)
    results.append(("Lead angle non-zero against moving target",
                    abs(lead) > 0.001,
                    f"lead={lead:.3f}°"))

    print("\n=== test_intercept.py ===")
    for item in results:
        name, passed = item[0], item[1]
        detail = item[2] if len(item) > 2 else ""
        status = "PASS" if passed else "FAIL"
        print(f"  [{status}] {name}" + (f" ({detail})" if detail else ""))


if __name__ == "__main__":
    run_tests()
