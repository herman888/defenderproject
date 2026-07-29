"""Regression coverage for the representative fixed-wing cruise controller."""

import math
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

pybullet = pytest.importorskip("pybullet")

from scenarios import INTRUDER_TYPES
from sim.drone import LoiteringMunition


def test_shahed_profile_uses_explicit_representative_cruise_command():
    """A profile speed must be a commanded cruise, not only a speed cap."""
    client = pybullet.connect(pybullet.DIRECT)
    try:
        pybullet.setGravity(0, 0, -9.81, physicsClientId=client)
        pybullet.setTimeStep(1.0 / 240.0, physicsClientId=client)
        intruder = LoiteringMunition(
            "speed-regression",
            (0.0, 0.0, 220.0),
            client,
            INTRUDER_TYPES["shahed136"],
        )
        intruder.set_target(5000.0, 0.0, 220.0)
        for _ in range(2400):  # ten simulation seconds
            intruder.update()
            pybullet.stepSimulation(physicsClientId=client)

        velocity = intruder.get_velocity()
        speed = math.sqrt(sum(component * component for component in velocity))
        assert intruder._fixed_wing is True
        assert intruder._cruise_speed == pytest.approx(51.0)
        # The representative model accelerates toward its command while the
        # explicit aerodynamic drag keeps it just under the 51 m/s cap.
        assert 45.0 <= speed <= 51.1
    finally:
        pybullet.disconnect(client)
