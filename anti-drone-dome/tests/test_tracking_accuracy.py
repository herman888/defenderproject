"""Accuracy regressions for tracking, fusion, and future-point guidance."""

import numpy as np

from guidance.intercept import PurePursuitGuidance
from sensors.fusion import TrackFusion
from sensors.radar import KalmanTracker


def test_constant_acceleration_tracker_has_bounded_maneuver_error():
    rng = np.random.default_rng(42)
    dt = 1.0 / 60.0
    position = np.asarray((600.0, -200.0, 80.0), dtype=float)
    velocity = np.asarray((-34.0, 16.0, 0.0), dtype=float)
    tracker = KalmanTracker(
        position + rng.normal(0.0, 0.15, 3),
        meas_std=0.15,
        dt=dt,
    )
    position_errors = []
    velocity_errors = []
    acceleration_errors = []

    for step in range(1200):
        timestamp = step * dt
        acceleration = np.asarray((
            4.0 * np.sin(0.7 * timestamp),
            7.0 * np.cos(0.45 * timestamp),
            2.0 * np.sin(0.3 * timestamp),
        ))
        velocity += acceleration * dt
        position += velocity * dt + 0.5 * acceleration * dt**2
        tracker.step(position + rng.normal(0.0, 0.15, 3))
        if step > 120:
            position_errors.append(
                np.linalg.norm(np.asarray(tracker.pos) - position)
            )
            velocity_errors.append(
                np.linalg.norm(np.asarray(tracker.vel) - velocity)
            )
            acceleration_errors.append(
                np.linalg.norm(np.asarray(tracker.acc) - acceleration)
            )

    assert np.sqrt(np.mean(np.square(position_errors))) < 0.12
    assert np.sqrt(np.mean(np.square(velocity_errors))) < 0.65
    assert np.sqrt(np.mean(np.square(acceleration_errors))) < 1.8


def test_tracker_coast_is_predict_only_not_a_synthetic_measurement():
    tracker = KalmanTracker(np.asarray((10.0, 20.0, 5.0)), 0.1, dt=0.1)
    tracker.x[3:6] = (4.0, -2.0, 1.0)
    tracker.x[6:9] = (1.0, 0.5, -0.25)
    expected = (
        tracker.x[:3]
        + tracker.x[3:6] * tracker.dt
        + 0.5 * tracker.x[6:9] * tracker.dt**2
    )
    tracker.step(None)
    assert np.allclose(tracker.pos, expected)


def test_fusion_projects_delayed_tracks_to_a_common_epoch():
    fused = TrackFusion().update(
        {
            "detected": True,
            "position_estimate": (95.0, 0.0, 10.0),
            "velocity": (50.0, 0.0, 0.0),
            "measurement_time_s": 0.9,
            "position_variance_m2": 0.04,
        },
        {
            "detected": True,
            "position_estimate": (75.0, 0.0, 10.0),
            "velocity": (50.0, 0.0, 0.0),
            "measurement_time_s": 0.5,
            "position_variance_m2": 1.0,
            "confidence": 0.8,
        },
        radar_confidence=0.9,
        timestamp=1.0,
    )
    assert fused["source"] == "RADAR+EO"
    assert abs(fused["position_estimate"][0] - 100.0) < 1e-6
    assert fused["innovation_m"] < 1e-6


def test_fusion_rejects_a_large_eo_innovation():
    fused = TrackFusion().update(
        {
            "detected": True,
            "position_estimate": (100.0, 20.0, 10.0),
            "velocity": (-10.0, 0.0, 0.0),
            "position_variance_m2": 0.04,
        },
        {
            "detected": True,
            "position_estimate": (280.0, -150.0, 80.0),
            "velocity": (30.0, 20.0, 0.0),
            "position_variance_m2": 1.0,
            "confidence": 0.99,
        },
        radar_confidence=0.95,
        timestamp=2.0,
    )
    assert fused["source"] == "RADAR"
    assert fused["rejected_sources"] == ["EO"]
    assert np.allclose(fused["position_estimate"], (100.0, 20.0, 10.0))


def test_guidance_aims_ahead_of_a_crossing_maneuver():
    guidance = PurePursuitGuidance()
    interceptor = {
        "position": (0.0, 0.0, 5.0),
        "velocity": (0.0, 0.0, 0.0),
    }
    track = {
        "detected": True,
        "position_estimate": (300.0, 0.0, 50.0),
        "velocity": (-8.0, 30.0, 0.0),
        "acceleration": (0.0, 4.0, 0.0),
        "confidence": 0.95,
    }
    setpoint = guidance.compute_guidance(interceptor, track)
    predicted = guidance.predicted_intercept_point(interceptor, track)
    assert setpoint.velocity is not None
    assert predicted is not None
    assert predicted[1] > 100.0
    assert guidance.last_diagnostics["lead_time_s"] > 0.0
    assert guidance.last_diagnostics["lead_angle_deg"] > 5.0
