"""Tests for the realistic flight-envelope limiter."""

import os
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from sim.airframe_profiles import get_airframe_profile
from sim.flight_envelope import FlightEnvelope, limit_acceleration, _G

_DT = 0.05


def test_lateral_acceleration_capped_to_g_limit():
    env = FlightEnvelope(max_lateral_accel_g=2.5, min_airspeed_mps=30.0, fixed_wing=True)
    velocity = [50.0, 0.0, 0.0]              # flying east
    accel = limit_acceleration(velocity, [0.0, 1000.0, 0.0], env, _DT)
    lateral = float(np.hypot(accel[0], accel[1]))   # all lateral (perp to east)
    assert lateral == pytest.approx(2.5 * _G, rel=1e-6)


def test_turn_radius_is_finite_and_realistic():
    # A vehicle commanded hard toward the origin from a tangential pass should
    # trace a turn radius near v^2 / a_lat, not pivot in place.
    env = FlightEnvelope(max_lateral_accel_g=2.5)
    v = 51.0
    expected_radius = v * v / (2.5 * _G)     # ~106 m for a Shahed-class turn
    accel = limit_acceleration([v, 0.0, 0.0], [0.0, -1e6, 0.0], env, _DT)
    a_lat = float(abs(accel[1]))
    assert v * v / a_lat == pytest.approx(expected_radius, rel=1e-6)
    assert expected_radius > 90.0            # not a point turn


def test_climb_rate_is_bounded():
    env = FlightEnvelope(max_climb_rate_mps=5.0)
    accel = limit_acceleration([0.0, 0.0, 4.0], [0.0, 0.0, 1000.0], env, _DT)
    assert accel[2] == pytest.approx((5.0 - 4.0) / _DT)


def test_descent_rate_is_bounded():
    env = FlightEnvelope(max_descent_rate_mps=6.0)
    accel = limit_acceleration([0.0, 0.0, -5.0], [0.0, 0.0, -1000.0], env, _DT)
    assert accel[2] == pytest.approx((-6.0 - -5.0) / _DT)


def test_fixed_wing_cannot_decelerate_below_min_airspeed():
    env = FlightEnvelope(min_airspeed_mps=30.0, fixed_wing=True, max_lateral_accel_g=3.0)
    accel = limit_acceleration([35.0, 0.0, 0.0], [-1000.0, 0.0, 0.0], env, _DT)
    # Longitudinal decel capped so speed lands exactly on the 30 m/s floor.
    assert accel[0] == pytest.approx((30.0 - 35.0) / _DT)


def test_multirotor_may_brake_to_a_stop():
    env = FlightEnvelope(min_airspeed_mps=0.0, fixed_wing=False, max_lateral_accel_g=2.0)
    accel = limit_acceleration([10.0, 0.0, 0.0], [-1000.0, 0.0, 0.0], env, _DT)
    # Pure longitudinal braking is not limited for a hover-capable vehicle.
    assert accel[0] == pytest.approx(-1000.0)


def test_from_profile_reads_real_values():
    env = FlightEnvelope.from_profile(
        get_airframe_profile("intruder.shahed136.representative-v1")
    )
    assert env.fixed_wing is True
    assert env.min_airspeed_mps == pytest.approx(30.0)
    assert env.max_lateral_accel_g == pytest.approx(2.5)


def test_from_profile_defaults_when_missing():
    env = FlightEnvelope.from_profile({})
    assert env.fixed_wing is False
    assert env.max_lateral_accel_g == pytest.approx(6.0)
