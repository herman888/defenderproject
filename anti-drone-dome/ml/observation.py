"""Shared observation encoding used by training and live inference."""

import numpy as np


def encode_observation(
    interceptor_position,
    interceptor_velocity,
    intruder_position,
    intruder_velocity,
    track_confidence,
    wind_velocity,
    elapsed_fraction,
):
    interceptor_position = np.asarray(interceptor_position, dtype=np.float32)
    interceptor_velocity = np.asarray(interceptor_velocity, dtype=np.float32)
    intruder_position = np.asarray(intruder_position, dtype=np.float32)
    intruder_velocity = np.asarray(intruder_velocity, dtype=np.float32)
    return np.concatenate([
        (intruder_position - interceptor_position) / 1000.0,
        (intruder_velocity - interceptor_velocity) / 100.0,
        interceptor_velocity / 70.0,
        intruder_position / 1000.0,
        np.asarray([track_confidence], dtype=np.float32),
        np.asarray(wind_velocity[:2], dtype=np.float32) / 10.0,
        np.asarray([elapsed_fraction], dtype=np.float32),
    ]).astype(np.float32)


def encode_observation_v2(
    interceptor_position,
    interceptor_velocity,
    intruder_position,
    intruder_velocity,
    track_confidence,
    wind_velocity,
    elapsed_fraction,
    battery_fraction,
    sensor_age_fraction,
):
    """Translation-invariant relative geometry for sim-to-real transfer."""
    interceptor_position = np.asarray(interceptor_position, dtype=np.float32)
    interceptor_velocity = np.asarray(interceptor_velocity, dtype=np.float32)
    intruder_position = np.asarray(intruder_position, dtype=np.float32)
    intruder_velocity = np.asarray(intruder_velocity, dtype=np.float32)
    relative_position = intruder_position - interceptor_position
    relative_velocity = intruder_velocity - interceptor_velocity
    separation = float(np.linalg.norm(relative_position))
    line_of_sight = relative_position / max(separation, 1e-6)
    closing_speed = -float(np.dot(relative_velocity, line_of_sight))
    return np.concatenate([
        relative_position / 1500.0,
        relative_velocity / 100.0,
        interceptor_velocity / 70.0,
        line_of_sight,
        np.asarray([separation / 1500.0], dtype=np.float32),
        np.asarray([closing_speed / 100.0], dtype=np.float32),
        np.asarray([track_confidence], dtype=np.float32),
        np.asarray(wind_velocity, dtype=np.float32) / 15.0,
        np.asarray([battery_fraction], dtype=np.float32),
        np.asarray([elapsed_fraction], dtype=np.float32),
        np.asarray([sensor_age_fraction], dtype=np.float32),
    ]).astype(np.float32)
