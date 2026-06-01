"""Test: pure pursuit force direction, magnitude cap, TTI positive, lead angle non-zero."""

import sys
import os
import math

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from guidance.intercept import PurePursuitGuidance


def run_tests():
    guidance = PurePursuitGuidance()
    results = []

    interceptor = {
        "position": (0.0, 0.0, 5.0),
        "velocity": (1.0, 0.5, 0.0),
    }
    target = {
        "detected": True,
        "position_estimate": (10.0, 8.0, 5.0),
        "velocity": (-1.0, 0.0, 0.0),
    }

    force = guidance.compute_guidance(interceptor, target)

    # Test 1: Force vector points toward target (positive x and y components)
    toward_target = force[0] > 0 and force[1] > 0
    results.append(("Force vector points toward target", toward_target,
                    f"force=({force[0]:.2f},{force[1]:.2f},{force[2]:.2f})"))

    # Test 2: Force magnitude <= 25N
    mag = math.sqrt(sum(f**2 for f in force))
    within_limit = mag <= 25.0
    results.append(("Force magnitude <= 25N", within_limit, f"mag={mag:.2f}"))

    # Test 3: TTI is positive and reasonable
    tti = guidance.time_to_intercept(interceptor, target)
    tti_ok = 0 < tti < 60.0
    results.append(("TTI positive and < 60s", tti_ok, f"tti={tti:.2f}s"))

    # Test 4: Lead angle is non-zero when target is moving
    lead = guidance.lead_angle_deg(interceptor, target)
    lead_nonzero = abs(lead) > 0.001
    results.append(("Lead angle non-zero when target moving", lead_nonzero, f"lead={lead:.3f}°"))

    print("\n=== test_intercept.py ===")
    for item in results:
        name, passed = item[0], item[1]
        detail = item[2] if len(item) > 2 else ""
        status = "PASS" if passed else "FAIL"
        print(f"  [{status}] {name}" + (f" ({detail})" if detail else ""))


if __name__ == "__main__":
    run_tests()
