"""Coordinated-turn bank for fixed-wing airframes.

The intruder's attitude was previously the minimum-rotation alignment of its
body +X axis to its velocity vector, which carries zero roll. A winged airframe
cannot turn that way - it banks, so that the horizontal component of lift
supplies the centripetal acceleration. Visually the old behaviour read as the
Shahed sliding flat around corners like a weathervane.
"""

from __future__ import annotations

import math
import os
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sim.drone import LoiteringMunition  # noqa: E402

GRAVITY = 9.81
CRUISE_MPS = 51.0          # Shahed-136 class cruise, ~185 km/h
DT = 1.0 / 240.0


class _BankStub:
    """Minimal carrier for the bank state the mixin methods use."""

    def __init__(self, max_lateral_g=2.5, roll_rate_dps=60.0):
        self._max_bank_rad = math.atan(max_lateral_g)
        self._roll_rate_rad_s = math.radians(roll_rate_dps)
        self._bank_rad = 0.0
        self._bank_prev_horizontal_velocity = None

    def bank(self, velocity, dt=DT):
        return LoiteringMunition._coordinated_bank_angle(self, velocity, dt)

    def settle(self, turn_rate_dps, speed=CRUISE_MPS, steps=3000):
        omega = math.radians(turn_rate_dps)
        heading = 0.0
        angle = 0.0
        for _ in range(steps):
            heading += omega * DT
            angle = self.bank(
                (speed * math.cos(heading), speed * math.sin(heading), 0.0)
            )
        return angle


def test_straight_and_level_flight_has_no_bank():
    stub = _BankStub()
    for _ in range(120):
        angle = stub.bank((CRUISE_MPS, 0.0, 0.0))
    assert angle == pytest.approx(0.0, abs=1e-6)


@pytest.mark.parametrize("turn_rate_dps", [1.0, 2.0, 5.0, 10.0])
def test_steady_turn_matches_the_coordinated_turn_relation(turn_rate_dps):
    """tan(phi) = a_lat / g, with a_lat = omega * V."""
    stub = _BankStub()
    angle = stub.settle(turn_rate_dps)
    omega = math.radians(turn_rate_dps)
    expected = math.atan(omega * CRUISE_MPS / GRAVITY)
    assert angle == pytest.approx(expected, rel=1e-3)


def test_bank_is_clamped_to_the_airframe_lateral_envelope():
    """A hard turn must not exceed atan(max_lateral_accel_g)."""
    stub = _BankStub(max_lateral_g=2.5)
    angle = stub.settle(40.0)
    assert angle == pytest.approx(math.atan(2.5), rel=1e-6)
    assert angle < math.radians(90.0)


def test_bank_direction_follows_turn_direction():
    right = _BankStub().settle(+5.0)
    left = _BankStub().settle(-5.0)
    assert right > 0.0 > left
    assert right == pytest.approx(-left, rel=1e-6)


def test_roll_is_rate_limited():
    """Bank cannot snap to its steady-state value in one step."""
    slow = _BankStub(roll_rate_dps=10.0)
    fast = _BankStub(roll_rate_dps=120.0)
    omega = math.radians(20.0)
    heading = 0.0
    for _ in range(30):
        heading += omega * DT
        velocity = (
            CRUISE_MPS * math.cos(heading),
            CRUISE_MPS * math.sin(heading),
            0.0,
        )
        slow_angle = slow.bank(velocity)
        fast_angle = fast.bank(velocity)
    assert abs(slow_angle) < abs(fast_angle)
    # A 10 deg/s limit cannot exceed 10 deg/s * elapsed time.
    assert abs(slow_angle) <= math.radians(10.0) * 30 * DT + 1e-9


def test_slower_aircraft_banks_less_for_the_same_turn_rate():
    """a_lat = omega * V, so bank scales with airspeed."""
    fast = _BankStub().settle(5.0, speed=80.0)
    slow = _BankStub().settle(5.0, speed=30.0)
    assert fast > slow


def test_roll_about_x_preserves_unit_norm():
    for degrees in (0.0, 15.0, -45.0, 90.0, 180.0):
        quaternion = LoiteringMunition._roll_about_x(
            (0.0, 0.0, 0.0, 1.0), math.radians(degrees)
        )
        assert np.linalg.norm(quaternion) == pytest.approx(1.0, abs=1e-12)


def test_roll_about_x_is_identity_for_zero_roll():
    original = (0.1, 0.2, 0.3, 0.927)
    assert LoiteringMunition._roll_about_x(original, 0.0) == original


def test_roll_about_x_rotates_the_body_y_axis():
    """A 90 deg roll must carry body +Y onto body +Z."""
    import pybullet

    quaternion = LoiteringMunition._roll_about_x(
        (0.0, 0.0, 0.0, 1.0), math.radians(90.0)
    )
    rotation = np.asarray(
        pybullet.getMatrixFromQuaternion(quaternion), dtype=float
    ).reshape(3, 3)
    assert rotation @ np.array([0.0, 1.0, 0.0]) == pytest.approx(
        np.array([0.0, 0.0, 1.0]), abs=1e-9
    )


def test_alignment_alone_carries_no_roll_regression():
    """Documents why the bank term is needed at all.

    `_align_x_to_vec` is the minimum-rotation alignment, so body +Y stays
    horizontal no matter how hard the aircraft is turning.
    """
    import pybullet

    heading = math.radians(30.0)
    quaternion = LoiteringMunition._align_x_to_vec(
        (math.cos(heading), math.sin(heading), 0.0)
    )
    rotation = np.asarray(
        pybullet.getMatrixFromQuaternion(quaternion), dtype=float
    ).reshape(3, 3)
    body_y = rotation @ np.array([0.0, 1.0, 0.0])
    assert body_y[2] == pytest.approx(0.0, abs=1e-9)
