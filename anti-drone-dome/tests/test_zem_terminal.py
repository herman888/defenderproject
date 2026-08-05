"""Zero-effort-miss terminal guidance.

ZEM replaced a relative-position PD that drove range to zero but did not null
the *lateral* miss. In a slow crossing geometry the interceptor would overshoot,
then orbit the target at 8-9 m for the rest of the episode, spending 87% of the
run in TERMINAL while commanding only 10-40% of available acceleration.

Proportional navigation cannot recover from that state either: its command is
N' * Vc * lambda_dot, so it backs off exactly when closing speed collapses and
line-of-sight rate spikes - the worst geometry. ZEM commands
N * ZEM / t_go^2, which *grows* as t_go shrinks.
"""

from __future__ import annotations

import math
import os
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from guidance.intercept import (  # noqa: E402
    _ZEM_MAX_TGO,
    _ZEM_MIN_TGO,
    PurePursuitGuidance,
    time_to_go,
    zero_effort_miss,
)


# --------------------------------------------------------------------------
# ZEM geometry
# --------------------------------------------------------------------------

def test_collision_course_has_zero_miss():
    """Closing straight down the line of sight predicts a hit."""
    r_vec = np.array([100.0, 0.0, 0.0])
    v_rel = np.array([-50.0, 0.0, 0.0])   # target closing on the interceptor
    zem = zero_effort_miss(r_vec, v_rel, np.zeros(3), t_go=2.0)
    assert np.linalg.norm(zem) == pytest.approx(0.0, abs=1e-9)


def test_crossing_geometry_predicts_lateral_miss():
    """A pure crossing target is missed by its own crossing displacement."""
    r_vec = np.array([100.0, 0.0, 0.0])
    v_rel = np.array([-50.0, 20.0, 0.0])
    zem = zero_effort_miss(r_vec, v_rel, np.zeros(3), t_go=2.0)
    assert zem[0] == pytest.approx(0.0, abs=1e-9)
    assert zem[1] == pytest.approx(40.0)      # 20 m/s over 2 s


def test_target_acceleration_enters_quadratically():
    r_vec = np.array([100.0, 0.0, 0.0])
    v_rel = np.array([-50.0, 0.0, 0.0])
    a_target = np.array([0.0, 4.0, 0.0])
    zem = zero_effort_miss(r_vec, v_rel, a_target, t_go=2.0)
    assert zem[1] == pytest.approx(0.5 * 4.0 * 4.0)   # 0.5*a*t^2


def test_zero_time_to_go_returns_current_separation():
    r_vec = np.array([3.0, 4.0, 0.0])
    zem = zero_effort_miss(r_vec, np.array([-10.0, 0.0, 0.0]), np.zeros(3), 0.0)
    assert np.linalg.norm(zem) == pytest.approx(5.0)


# --------------------------------------------------------------------------
# Time-to-go
# --------------------------------------------------------------------------

def test_time_to_go_is_range_over_closing_speed():
    assert time_to_go(100.0, 50.0, 60.0) == pytest.approx(2.0)


def test_time_to_go_is_clamped_at_both_ends():
    # Very close and very fast would divide toward zero and blow up the command.
    assert time_to_go(0.001, 500.0, 60.0) == pytest.approx(_ZEM_MIN_TGO)
    # Barely closing would otherwise dilute ZEM to nothing.
    assert time_to_go(10_000.0, 0.5, 60.0) == pytest.approx(_ZEM_MAX_TGO)


def test_opening_range_falls_back_to_command_speed():
    """A negative closing rate has no meaningful range/rate quotient."""
    opening = time_to_go(50.0, -20.0, 60.0)
    assert opening == pytest.approx(min(50.0 / 60.0, _ZEM_MAX_TGO))
    assert opening > 0.0


# --------------------------------------------------------------------------
# The property that matters: command grows as t_go shrinks
# --------------------------------------------------------------------------

def _terminal_accel(guidance, separation, closing, lateral):
    """Commanded acceleration magnitude at a given terminal geometry."""
    state = {
        "position": (0.0, 0.0, 100.0),
        "velocity": (closing, 0.0, 0.0),
        "energy_remaining_fraction": 0.9,
    }
    track = {
        "detected": True,
        "position_estimate": (separation, 0.0, 100.0),
        "velocity": (0.0, lateral, 0.0),
        "acceleration": (0.0, 0.0, 0.0),
        "track_confidence": 0.9,
    }
    setpoint = guidance.compute_guidance(state, track)
    if setpoint.accel is None:
        return 0.0
    return float(np.linalg.norm(np.asarray(setpoint.accel, dtype=float)))


def test_zem_commands_harder_as_range_closes_regression():
    """The core fix.

    The PD law backed off near the target, which is how the 8-9 m orbit became
    stable. ZEM must do the opposite.
    """
    zem = PurePursuitGuidance(terminal_law="zem")
    far = _terminal_accel(zem, separation=12.0, closing=20.0, lateral=8.0)
    near = _terminal_accel(zem, separation=3.0, closing=20.0, lateral=8.0)
    assert near > far


def test_zem_outcommands_the_pd_law_in_the_orbit_geometry():
    """At the measured limit-cycle state - ~9 m, slow closure, high LOS rate."""
    zem = _terminal_accel(
        PurePursuitGuidance(terminal_law="zem"), 9.0, 12.0, 10.0
    )
    pd = _terminal_accel(
        PurePursuitGuidance(terminal_law="pd"), 9.0, 12.0, 10.0
    )
    assert zem > pd


def test_terminal_law_selection_is_validated():
    with pytest.raises(ValueError):
        PurePursuitGuidance(terminal_law="nonsense")


def test_both_laws_produce_finite_bounded_commands():
    """No NaN, no divergence, at a range of terminal geometries."""
    for law in ("zem", "pd"):
        guidance = PurePursuitGuidance(terminal_law=law)
        for separation in (0.5, 1.0, 5.0, 15.0, 40.0):
            for closing in (-10.0, 0.0, 5.0, 60.0, 150.0):
                magnitude = _terminal_accel(
                    guidance, separation, closing, lateral=12.0
                )
                assert math.isfinite(magnitude), (law, separation, closing)
                assert magnitude < 1e4, (law, separation, closing)


def test_diagnostics_expose_the_terminal_law_and_time_to_go():
    guidance = PurePursuitGuidance(terminal_law="zem")
    _terminal_accel(guidance, separation=6.0, closing=25.0, lateral=5.0)
    diagnostics = guidance.last_diagnostics
    assert diagnostics["terminal_law"] == "zem"
    assert math.isfinite(diagnostics["terminal_time_to_go_s"])
    assert diagnostics["terminal_time_to_go_s"] >= _ZEM_MIN_TGO


def test_pd_law_remains_available_for_comparison():
    """The previous law is retained so the two can be measured, not swapped
    on faith."""
    guidance = PurePursuitGuidance(terminal_law="pd")
    assert _terminal_accel(guidance, 8.0, 15.0, 6.0) > 0.0
    assert guidance.last_diagnostics["terminal_law"] == "pd"
