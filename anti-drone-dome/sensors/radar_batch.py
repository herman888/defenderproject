"""Multi-target pulse-Doppler radar with measurement-level association.

``RadarNode`` intentionally remains the compact single-target implementation
used by the legacy one-engagement path.  This module is the swarm-safe sensor
boundary: true target state is used only to generate noisy detections, then
discarded before Mahalanobis-gated association and track updates.  Consumers
receive sensor-created track IDs, never scenario object IDs.

It is still a synthetic sensor.  Its radar budget and measurement covariance
must be calibrated before any swarm result is treated as field evidence.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Iterable, Mapping

import numpy as np

from sensors.radar import KalmanTracker, _DT, _PROC_NOISE
from sensors.radar_model import RadarDetectionModel
from swarm.assignment import hungarian_assignment


@dataclass
class _Track:
    tracker: KalmanTracker
    hits: int
    misses: int
    last_measurement_time_s: float


class MultiTargetRadar:
    """Generate and associate multiple position-only radar detections.

    Input dictionaries may contain an ``id`` for scenario bookkeeping, but it
    is deliberately ignored after measurement generation.  This prevents the
    coordinator from receiving omniscient target identity through the sensor
    API.
    """

    def __init__(
        self,
        station_pos=(0.0, -10.0, 3.0),
        max_range: float = 25.0,
        elev_max_deg: float = 60.0,
        noise_std: float = 0.15,
        process_noise: float = _PROC_NOISE,
        confirmation_hits: int = 3,
        max_misses: int = 8,
        association_gate_chi2: float = 16.27,
        dt: float = _DT,
        seed: int | None = None,
        detection_model=None,
    ):
        if max_range <= 0.0 or noise_std <= 0.0:
            raise ValueError("max_range and noise_std must be positive")
        if confirmation_hits <= 0 or max_misses < 0:
            raise ValueError("confirmation_hits must be positive and max_misses non-negative")
        if association_gate_chi2 <= 0.0 or dt <= 0.0:
            raise ValueError("association_gate_chi2 and dt must be positive")
        self.station_pos = np.asarray(station_pos, dtype=float)
        self.max_range = float(max_range)
        self._elev_max = math.radians(float(elev_max_deg))
        self._noise_std = float(noise_std)
        self._process_noise = float(process_noise)
        self._confirmation_hits = int(confirmation_hits)
        self._max_misses = int(max_misses)
        self._gate = float(association_gate_chi2)
        self._dt = float(dt)
        self._rng = np.random.default_rng(seed)
        self._detection_model = detection_model or RadarDetectionModel(
            max_range_m=self.max_range
        )
        self._tracks: dict[str, _Track] = {}
        self._next_track_number = 1
        self._scan_index = 0

    def _in_beam(self, position: np.ndarray) -> tuple[bool, float, float, float]:
        delta = position - self.station_pos
        range_m = float(np.linalg.norm(delta))
        if range_m < 0.1 or range_m > self.max_range:
            return False, range_m, 0.0, 0.0
        horizontal = math.hypot(float(delta[0]), float(delta[1]))
        elevation = math.atan2(float(delta[2]), horizontal)
        bearing = math.degrees(math.atan2(float(delta[1]), float(delta[0]))) % 360.0
        return (
            position[2] >= 0.5 and 0.0 <= elevation <= self._elev_max,
            range_m,
            elevation,
            bearing,
        )

    def _measure(self, targets: Iterable[Mapping]) -> list[dict]:
        """Return unlabelled measurements generated from in-beam targets."""
        measurements: list[dict] = []
        for target in targets:
            position = np.asarray(
                target.get("position_estimate", target.get("position")), dtype=float
            )
            if position.shape != (3,):
                raise ValueError("each radar target requires a three-axis position")
            in_beam, range_m, elevation, bearing = self._in_beam(position)
            rcs = float(target.get("rcs_m2", target.get("target_rcs", 0.05)))
            if not in_beam or self._rng.random() > self._detection_model.p_detect(range_m, rcs):
                continue
            measurements.append({
                "position": position + self._rng.normal(0.0, self._noise_std, 3),
                "range_m": range_m,
                "bearing_deg": bearing,
                "elevation_deg": math.degrees(elevation),
            })
        return measurements

    def _associate(self, measurements: list[dict]) -> dict[int, str]:
        """Associate measurements to predicted tracks by Mahalanobis distance."""
        track_ids = sorted(self._tracks)
        if not track_ids or not measurements:
            return {}
        cost = np.full((len(track_ids), len(measurements)), np.inf, dtype=float)
        for row, track_id in enumerate(track_ids):
            track = self._tracks[track_id].tracker
            covariance = track.P[:3, :3] + track.R
            inverse = np.linalg.inv(covariance)
            for column, measurement in enumerate(measurements):
                innovation = np.asarray(measurement["position"], dtype=float) - track.x[:3]
                d2 = float(innovation @ inverse @ innovation)
                if d2 <= self._gate:
                    cost[row, column] = d2
        assignment = hungarian_assignment(cost)
        return {
            measurement_index: track_ids[track_index]
            for measurement_index, track_index in assignment.pairs.items()
        }

    def scan(self, targets: Iterable[Mapping], timestamp_s: float | None = None) -> list[dict]:
        """Advance all tracks and return confirmed, sensor-derived tracks.

        The returned list is deterministic for identical target states, call
        order, and seed.  It contains no source target IDs.
        """
        self._scan_index += 1
        timestamp = (
            float(timestamp_s)
            if timestamp_s is not None
            else (self._scan_index - 1) * self._dt
        )
        for state in self._tracks.values():
            state.tracker.predict()
            state.misses += 1

        measurements = self._measure(targets)
        matched = self._associate(measurements)
        for measurement_index, track_id in matched.items():
            state = self._tracks[track_id]
            state.tracker.update(measurements[measurement_index]["position"])
            state.hits += 1
            state.misses = 0
            state.last_measurement_time_s = timestamp

        for measurement_index, measurement in enumerate(measurements):
            if measurement_index in matched:
                continue
            track_id = f"radar-{self._next_track_number:04d}"
            self._next_track_number += 1
            self._tracks[track_id] = _Track(
                tracker=KalmanTracker(
                    measurement["position"], self._noise_std,
                    dt=self._dt, process_noise=self._process_noise,
                ),
                hits=1,
                misses=0,
                last_measurement_time_s=timestamp,
            )

        self._tracks = {
            track_id: state for track_id, state in self._tracks.items()
            if state.misses <= self._max_misses
        }
        results: list[dict] = []
        for track_id in sorted(self._tracks):
            state = self._tracks[track_id]
            if state.hits < self._confirmation_hits:
                continue
            age = max(0.0, timestamp - state.last_measurement_time_s)
            results.append({
                "id": track_id,
                "detected": state.misses == 0,
                "confirmed": True,
                "coasted": state.misses > 0,
                "position_estimate": state.tracker.pos,
                "velocity": state.tracker.vel,
                "acceleration": state.tracker.acc,
                "position_variance_m2": state.tracker.position_variance_m2,
                "measurement_time_s": state.last_measurement_time_s,
                "track_age_s": age,
                "hits": state.hits,
                "misses": state.misses,
            })
        return results

    def reset(self) -> None:
        """Discard all tracks while preserving the configured sensor model."""
        self._tracks.clear()
        self._next_track_number = 1
        self._scan_index = 0
