"""Regression coverage for the telemetry-driven VTOL interceptor attitude."""

import os
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

pybullet = pytest.importorskip("pybullet")

from sim.drone import Drone


def test_interceptor_propulsion_and_nose_follow_body_x_without_altitude_runaway():
    """The rocket-shaped four-prop interceptor must move nose-first, not sideways."""
    client = pybullet.connect(pybullet.DIRECT)
    try:
        pybullet.setGravity(0, 0, -9.81, physicsClientId=client)
        pybullet.setTimeStep(1.0 / 240.0, physicsClientId=client)
        interceptor = Drone(
            "attitude-regression",
            (0.0, 0.0, 220.0),
            client,
            airframe_profile_id="interceptor.reference-v1",
        )
        interceptor.set_target(1000.0, 0.0, 220.0)
        for _ in range(480):  # two seconds of lateral acceleration
            interceptor.update()
            pybullet.stepSimulation(physicsClientId=client)

        position = np.asarray(interceptor.get_position())
        velocity = np.asarray(interceptor.get_velocity())
        _, orientation = pybullet.getBasePositionAndOrientation(
            interceptor.body_id, physicsClientId=client
        )
        rotation = np.asarray(pybullet.getMatrixFromQuaternion(orientation)).reshape(3, 3)
        forward = rotation[:, 0]
        horizontal_velocity = velocity[:2]

        assert position[0] > 20.0
        assert velocity[0] > 20.0
        assert abs(position[2] - 220.0) < 20.0
        assert np.dot(forward[:2], horizontal_velocity) > 0.0
    finally:
        pybullet.disconnect(client)
