"""Tests for the multi-target sensor boundary used by future swarm runs."""

from __future__ import annotations

import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sensors.radar_batch import MultiTargetRadar  # noqa: E402


class AlwaysDetect:
    def p_detect(self, range_m, rcs_m2):
        return 1.0


def _radar(seed=7):
    return MultiTargetRadar(
        station_pos=(0.0, 0.0, 0.0),
        max_range=200.0,
        noise_std=0.01,
        confirmation_hits=2,
        detection_model=AlwaysDetect(),
        seed=seed,
    )


def test_multi_target_radar_creates_independent_confirmed_tracks():
    radar = _radar()
    targets = [
        {"id": "scenario-secret-a", "position": (25.0, 0.0, 5.0)},
        {"id": "scenario-secret-b", "position": (0.0, 35.0, 7.0)},
    ]
    assert radar.scan(targets) == []  # tentative tracks are not published
    tracks = radar.scan(targets)
    assert len(tracks) == 2
    assert all(track["confirmed"] for track in tracks)
    assert {track["id"] for track in tracks} == {"radar-0001", "radar-0002"}
    assert "scenario-secret-a" not in repr(tracks)
    positions = np.asarray([track["position_estimate"] for track in tracks])
    assert any(np.linalg.norm(position - (25.0, 0.0, 5.0)) < 0.2 for position in positions)
    assert any(np.linalg.norm(position - (0.0, 35.0, 7.0)) < 0.2 for position in positions)


def test_multi_target_association_tracks_motion_without_target_identity():
    radar = _radar()
    for step in range(8):
        tracks = radar.scan([
            # 0.05 m per 1/240 s scan is a 12 m/s target, within the
            # constant-acceleration track model.  A 1 m step would represent
            # an implausible 240 m/s target and should correctly gate out.
            {"id": "one", "position": (20.0 + 0.05 * step, 0.0, 5.0)},
            {"id": "two", "position": (0.0, 30.0 - 0.05 * step, 6.0)},
        ])
    assert len(tracks) == 2
    velocities = sorted(track["velocity"] for track in tracks)
    assert any(velocity[0] > 0.03 for velocity in velocities)
    assert any(velocity[1] < -0.03 for velocity in velocities)


def test_multi_target_radar_is_seed_reproducible():
    targets = [{"position": (30.0, -4.0, 6.0), "rcs_m2": 0.01}]
    first, second = _radar(seed=99), _radar(seed=99)
    traces = []
    for radar in (first, second):
        trace = []
        for _ in range(4):
            trace.append(radar.scan(targets))
        traces.append(trace)
    assert traces[0] == traces[1]


def test_tracks_coast_then_expire_after_missed_measurements():
    radar = MultiTargetRadar(
        station_pos=(0.0, 0.0, 0.0), max_range=200.0, noise_std=0.01,
        confirmation_hits=1, max_misses=2, detection_model=AlwaysDetect(), seed=3,
    )
    assert len(radar.scan([{"position": (20.0, 0.0, 5.0)}])) == 1
    coasting = radar.scan([])
    assert len(coasting) == 1 and coasting[0]["coasted"]
    radar.scan([])
    assert radar.scan([]) == []


def test_sensor_accepts_an_explicit_scan_interval():
    radar = MultiTargetRadar(
        station_pos=(0.0, 0.0, 0.0), max_range=200.0, noise_std=0.01,
        confirmation_hits=1, detection_model=AlwaysDetect(), dt=0.05, seed=4,
    )
    for step in range(5):
        tracks = radar.scan([{"position": (20.0 + step, 0.0, 5.0)}])
    assert tracks[0]["velocity"][0] > 5.0
