"""Simulated ground radar with Gaussian noise, probabilistic detection, and track history."""

import math
import time
import numpy as np
from collections import deque

_MAX_HISTORY = 50


class RadarNode:
    def __init__(self, protected_center=(0.0, 0.0, 0.0), max_range: float = 20.0, noise_std: float = 0.3):
        self._center = np.array(protected_center, dtype=float)
        self._max_range = max_range
        self._noise_std = noise_std
        self._min_range = 2.0
        self.track_history: deque = deque(maxlen=_MAX_HISTORY)
        self._last_detection_time: float = None

    def scan(self, drone_position: tuple) -> dict:
        true_pos = np.array(drone_position, dtype=float)
        diff = true_pos - self._center
        true_range = float(np.linalg.norm(diff))

        if true_range > self._max_range:
            return {"detected": False}

        # Detection probability
        if true_range <= self._min_range:
            detected = True
        elif true_range <= 15.0:
            detected = np.random.random() < 0.95
        else:
            p = 0.95 - (true_range - 15.0) / (self._max_range - 15.0) * 0.35
            detected = np.random.random() < p

        if not detected:
            return {"detected": False}

        # Add noise to position estimate
        noise = np.random.normal(0.0, self._noise_std, size=3)
        est_pos = true_pos + noise

        # Bearing and elevation from center
        horiz = math.sqrt(diff[0] ** 2 + diff[1] ** 2)
        bearing_deg = math.degrees(math.atan2(diff[1], diff[0]))
        elevation_deg = math.degrees(math.atan2(diff[2], horiz))

        noisy_range = true_range + np.random.normal(0.0, self._noise_std)
        snr = 30.0 - (true_range / self._max_range) * 20.0 + np.random.normal(0.0, 1.5)

        ts = time.time()
        result = {
            "detected": True,
            "range": float(noisy_range),
            "bearing_deg": float(bearing_deg),
            "elevation_deg": float(elevation_deg),
            "position_estimate": tuple(est_pos),
            "snr": float(snr),
            "timestamp": ts,
        }

        if not self.track_history or self._last_detection_time is None:
            print(f"RADAR: Track acquired at range {true_range:.1f}m, bearing {bearing_deg:.1f}°")

        self._last_detection_time = ts
        self.track_history.append(result)
        return result

    def get_track_history(self) -> list:
        return list(self.track_history)

    def get_track_velocity(self) -> tuple:
        if len(self.track_history) < 2:
            return (0.0, 0.0, 0.0)
        r1 = self.track_history[-2]
        r2 = self.track_history[-1]
        dt = r2["timestamp"] - r1["timestamp"]
        if dt <= 0:
            return (0.0, 0.0, 0.0)
        p1 = np.array(r1["position_estimate"])
        p2 = np.array(r2["position_estimate"])
        vel = (p2 - p1) / dt
        return tuple(vel)

    def track_confidence(self) -> float:
        if len(self.track_history) == 0:
            return 0.0
        return min(1.0, len(self.track_history) / 20.0)

    @property
    def last_detection_time(self):
        return self._last_detection_time
