"""Coverage for the rocket effector, passive optical tracker, and CPK allocator.

Each test named ``test_*_regression`` pins a specific defect found in the
initial implementations; they should fail if the fix is reverted.
"""

from __future__ import annotations

import os
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from guidance.passive_optical import PassiveOpticalTracker  # noqa: E402
from sim.rocket_effector import (  # noqa: E402
    MicroRocketEffector,
    air_density,
    closest_approach,
    drag_coefficient,
    speed_of_sound,
)
from swarm.cpk_optimizer import CostPerKillOptimizer, probability_of_hit  # noqa: E402


# --------------------------------------------------------------------------
# Rocket effector
# --------------------------------------------------------------------------

def test_atmosphere_matches_isa_at_sea_level():
    assert air_density(0.0) == pytest.approx(1.225, rel=1e-3)
    assert speed_of_sound(0.0) == pytest.approx(340.3, rel=1e-2)
    # Density falls monotonically with altitude.
    assert air_density(3000.0) < air_density(1000.0) < air_density(0.0)


def test_drag_rises_through_transonic_then_decays():
    cd0 = 0.25
    assert drag_coefficient(cd0, 0.5) == pytest.approx(cd0)
    assert drag_coefficient(cd0, 1.2) > drag_coefficient(cd0, 0.9) > cd0
    # Supersonic decay, but never below the floor.
    assert drag_coefficient(cd0, 3.0) >= cd0 * 1.8


def test_thrust_direction_stays_unit_norm_regression():
    """Thrust must never exceed max_thrust.

    The original code updated the heading with ``vel / speed`` where ``speed``
    was the magnitude captured *before* the velocity update, so the "unit"
    vector had magnitude |v_new|/|v_old| > 1 during boost. At low speed that
    inflated thrust several-fold.
    """
    rocket = MicroRocketEffector([0.0, 0.0, 10.0], [0.0, 600.0, 200.0])
    for _ in range(120):
        rocket.step(0.01, [0.0, 600.0, 200.0])
        assert np.linalg.norm(rocket.unit_dir) == pytest.approx(1.0, abs=1e-9)


def test_boost_reaches_design_speed():
    """~1500 N on 2.2 kg for 0.8 s should approach Mach 1.6 (~550 m/s)."""
    rocket = MicroRocketEffector([0.0, 0.0, 100.0], [0.0, 5000.0, 100.0])
    for _ in range(80):
        rocket.step(0.01, [0.0, 5000.0, 100.0])
    speed = float(np.linalg.norm(rocket.vel))
    assert 400.0 < speed < 650.0


def test_lateral_acceleration_is_clamped_regression():
    """PN command must respect fin authority.

    Unclamped PN against a close, fast-crossing target commands hundreds of g,
    which silently turns the effector into a perfect interceptor.
    """
    rocket = MicroRocketEffector([0.0, 0.0, 100.0], [50.0, 0.0, 100.0])
    rocket.vel = np.array([0.0, 300.0, 0.0])
    accel = rocket._pn_acceleration(
        np.array([30.0, 5.0, 0.0]), 30.4, np.array([0.0, -200.0, 0.0]), 300.0
    )
    assert np.linalg.norm(accel) <= rocket.max_lateral_accel + 1e-6


def test_closest_approach_detects_pass_through():
    """A segment that straddles the target must report the true minimum."""
    # Relative position flips sign across the step: passes straight through.
    distance, fraction = closest_approach(
        np.array([0.0, 5.0, 0.0]), np.array([0.0, -5.0, 0.0])
    )
    assert distance == pytest.approx(0.0, abs=1e-9)
    assert 0.0 <= fraction <= 1.0


def test_fast_flyby_is_not_missed_regression():
    """Endpoint-only hit tests tunnel through the target at high speed.

    At 550 m/s with dt=0.01 the body advances 5.5 m per step, further than the
    4 m lethal radius, so both endpoints can lie outside it while the path
    passes through the centre.
    """
    rocket = MicroRocketEffector([0.0, -10.0, 100.0], [0.0, 0.0, 100.0])
    rocket.vel = np.array([0.0, 550.0, 0.0])
    rocket.time_elapsed = 5.0  # past burnout, so no thrust
    _, intercepted = rocket.step(0.02, [0.0, 0.0, 100.0])
    assert intercepted
    assert rocket.miss_distance_m < rocket.detonation_radius


def test_get_state_reports_mach_and_miss_distance():
    rocket = MicroRocketEffector([0.0, 0.0, 50.0], [0.0, 400.0, 50.0])
    rocket.step(0.01, [0.0, 400.0, 50.0])
    state = rocket.get_state()
    assert {"mach", "miss_distance_m", "cost_usd", "time_s"} <= set(state)
    assert state["mach"] >= 0.0


# --------------------------------------------------------------------------
# Passive optical tracker
# --------------------------------------------------------------------------

def _identity_camera():
    """Camera looking along +Y (ENU north) with Z-forward/X-right/Y-down."""
    # camera x_right -> world +X, camera y_down -> world -Z, camera z_fwd -> world +Y
    return np.array([
        [1.0, 0.0, 0.0],
        [0.0, 0.0, 1.0],
        [0.0, -1.0, 0.0],
    ])


def test_range_from_width_uses_linear_pinhole():
    tracker = PassiveOpticalTracker(focal_length_px=800.0, reference_width_m=0.8)
    # Z = W * f / w  ->  0.8 * 800 / 32 = 20 m
    rng, sigma = tracker._range_from_width(32.0)
    assert rng == pytest.approx(20.0)
    # Fractional range error equals fractional width error.
    assert sigma / rng == pytest.approx(1.0 / 32.0)


def test_range_uncertainty_grows_with_distance():
    tracker = PassiveOpticalTracker()
    near, near_sigma = tracker._range_from_width(64.0)
    far, far_sigma = tracker._range_from_width(8.0)
    assert far > near
    assert far_sigma / far > near_sigma / near


def test_centred_detection_projects_along_boresight():
    tracker = PassiveOpticalTracker(principal_point_px=(640.0, 360.0))
    pos, _ = tracker.update_from_bbox(
        [640.0, 360.0, 32.0, 32.0], 0.0, [0.0, 0.0, 100.0], _identity_camera()
    )
    # 20 m straight down the boresight (+Y), no lateral or vertical offset.
    assert pos[0] == pytest.approx(0.0, abs=1e-6)
    assert pos[1] == pytest.approx(20.0, rel=1e-6)
    assert pos[2] == pytest.approx(100.0, abs=1e-6)


def test_principal_point_is_configurable_regression():
    """The principal point was hardcoded to (640, 360) regardless of sensor."""
    tracker = PassiveOpticalTracker(principal_point_px=(320.0, 240.0))
    pos, _ = tracker.update_from_bbox(
        [320.0, 240.0, 32.0, 32.0], 0.0, [0.0, 0.0, 100.0], _identity_camera()
    )
    assert pos[0] == pytest.approx(0.0, abs=1e-6)
    assert pos[2] == pytest.approx(100.0, abs=1e-6)


def test_velocity_converges_on_constant_motion_regression():
    """Alpha-beta needs a prediction step.

    Without propagating the state by ``v * dt`` before differencing, the
    residual absorbs the entire inter-frame displacement, so position lags
    permanently and velocity never settles on the true value.
    """
    tracker = PassiveOpticalTracker(focal_length_px=800.0, reference_width_m=0.8)
    camera = _identity_camera()
    dt = 0.05
    # Target closing along -Y at 20 m/s, starting 40 m out.
    for step in range(120):
        t = step * dt
        true_range = 40.0 - 20.0 * t
        if true_range < 5.0:
            break
        width = (0.8 * 800.0) / true_range
        tracker.update_from_bbox(
            [640.0, 360.0, width, width], t, [0.0, 0.0, 100.0], camera
        )

    _, velocity = tracker.state[:3], tracker.state[3:]
    assert velocity[1] == pytest.approx(-20.0, rel=0.15)


def test_track_dict_is_fusion_shaped():
    tracker = PassiveOpticalTracker()
    assert tracker.track()["detected"] is False

    tracker.update_from_bbox(
        [640.0, 360.0, 40.0, 40.0], 1.0, [0.0, 0.0, 100.0], _identity_camera()
    )
    track = tracker.track()
    assert track["detected"] is True
    assert {"position_estimate", "velocity", "track_confidence",
            "measurement_time_s"} <= set(track)
    assert 0.0 < track["track_confidence"] <= 1.0
    # Monocular range is not observable; consumers must know that.
    assert track["range_observable"] is False


def test_confidence_falls_with_range_uncertainty():
    camera = _identity_camera()
    near = PassiveOpticalTracker()
    near.update_from_bbox([640.0, 360.0, 80.0, 80.0], 0.0, [0, 0, 100.0], camera)
    far = PassiveOpticalTracker()
    far.update_from_bbox([640.0, 360.0, 6.0, 6.0], 0.0, [0, 0, 100.0], camera)
    assert near.track()["track_confidence"] > far.track()["track_confidence"]


# --------------------------------------------------------------------------
# Cost-per-kill optimizer
# --------------------------------------------------------------------------

def test_head_on_shot_is_not_rejected_regression():
    """Speed alone is the wrong feasibility test.

    The original model gave any quad facing a faster threat p_hit=0.2, which
    wrongly discards head-on and crossing geometries where the threat closes
    the distance itself.
    """
    # Threat inbound toward the effector at 80 m/s; effector only makes 30 m/s.
    head_on = probability_of_hit(
        [0.0, 0.0, 100.0], 30.0, [0.0, 500.0, 100.0], [0.0, -80.0, 0.0],
        is_kinematically_limited=True,
    )
    tail_chase = probability_of_hit(
        [0.0, 0.0, 100.0], 30.0, [0.0, 500.0, 100.0], [0.0, 80.0, 0.0],
        is_kinematically_limited=True,
    )
    assert head_on > tail_chase
    assert tail_chase == pytest.approx(0.05)


def test_threat_value_is_used_regression():
    """``value`` was documented in the interface but never read."""
    optimizer = CostPerKillOptimizer()
    effectors = [{"id": 0, "pos": [0, 0, 100], "type": "rocket",
                  "speed": 500.0, "cost": 1800.0}]
    cheap = [{"id": 0, "pos": [0, 400, 100], "vel": [0, -50, 0], "value": 500.0}]
    valuable = [{"id": 0, "pos": [0, 400, 100], "vel": [0, -50, 0],
                 "value": 100000.0}]
    # Spending $1800 on a $500 decoy must score worse than on a $100k asset.
    assert (optimizer.build_cost_matrix(effectors, cheap)[0, 0]
            > optimizer.build_cost_matrix(effectors, valuable)[0, 0])


def test_expected_cost_accounts_for_hit_probability():
    """A cheap effector that rarely connects is not actually cheap."""
    optimizer = CostPerKillOptimizer(w_tti=0.0, w_phit=0.0, w_cpk=1.0)
    # Same effector and same threat value; only the engagement range differs,
    # so the whole cost delta comes from p_hit feeding the expected-shots term.
    effector = [{"id": 0, "pos": [0, 0, 100], "type": "rocket",
                 "speed": 500.0, "cost": 1000.0}]
    threat_near = [{"id": 0, "pos": [0, 50, 100], "value": 20000.0}]
    threat_far = [{"id": 0, "pos": [0, 2900, 100], "value": 20000.0}]

    near_cost = optimizer.build_cost_matrix(effector, threat_near)[0, 0]
    far_cost = optimizer.build_cost_matrix(effector, threat_far)[0, 0]
    assert far_cost > near_cost
    # p_hit 0.95 -> ~1.05 shots -> $1053 of $20k; p_hit floor 0.05 -> $20k.
    assert near_cost == pytest.approx(1000.0 / 0.95 / 20000.0, rel=1e-6)
    assert far_cost == pytest.approx(1.0, rel=1e-6)


def test_weights_are_normalised():
    optimizer = CostPerKillOptimizer(w_tti=4.0, w_phit=3.0, w_cpk=3.0)
    assert optimizer.w_tti + optimizer.w_phit + optimizer.w_cpk == pytest.approx(1.0)
    with pytest.raises(ValueError):
        CostPerKillOptimizer(w_tti=0.0, w_phit=0.0, w_cpk=0.0)


def test_unavailable_effector_is_never_assigned():
    optimizer = CostPerKillOptimizer()
    effectors = [
        {"id": 0, "pos": [0, 0, 100], "type": "rocket", "speed": 500.0,
         "cost": 1800.0, "available": False},
        {"id": 1, "pos": [0, 0, 100], "type": "rocket", "speed": 500.0,
         "cost": 1800.0},
    ]
    threats = [{"id": 9, "pos": [0, 400, 100], "vel": [0, -50, 0]}]
    records = optimizer.compute_assignment(effectors, threats)
    assert [r["effector_id"] for r in records] == [1]


def test_more_threats_than_effectors_leak_rather_than_crash():
    optimizer = CostPerKillOptimizer()
    effectors = [{"id": 0, "pos": [0, 0, 100], "type": "rocket",
                  "speed": 500.0, "cost": 1800.0}]
    threats = [
        {"id": 0, "pos": [0, 300, 100], "vel": [0, -50, 0]},
        {"id": 1, "pos": [0, 600, 100], "vel": [0, -50, 0]},
        {"id": 2, "pos": [0, 900, 100], "vel": [0, -50, 0]},
    ]
    result = optimizer.solve(effectors, threats)
    assert len(result.pairs) == 1
    assert len(result.leakers) == 2


def test_empty_inputs_are_handled():
    optimizer = CostPerKillOptimizer()
    assert optimizer.compute_assignment([], []) == []
    result = optimizer.solve([], [{"id": 0, "pos": [0, 0, 0]}])
    assert result.leakers == [0]


def test_assignment_is_deterministic():
    optimizer = CostPerKillOptimizer()
    effectors = [
        {"id": i, "pos": [i * 10.0, 0.0, 100.0], "type": "rocket",
         "speed": 500.0, "cost": 1800.0}
        for i in range(4)
    ]
    threats = [
        {"id": j, "pos": [0.0, 300.0 + j * 50.0, 100.0], "vel": [0.0, -60.0, 0.0]}
        for j in range(4)
    ]
    first = optimizer.compute_assignment(effectors, threats)
    for _ in range(5):
        assert optimizer.compute_assignment(effectors, threats) == first
