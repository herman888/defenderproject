"""Procedural engagement curriculum for robust relative-position policies."""

from __future__ import annotations

from dataclasses import dataclass
import math

import numpy as np


@dataclass(frozen=True)
class EngagementScenario:
    scenario_id: str
    intruder_type: str
    profile: str
    waypoints: tuple[tuple[float, float, float], ...]
    interceptor_start: tuple[float, float, float]
    wind_mps: tuple[float, float, float]
    sensor_latency_s: float
    sensor_dropout_probability: float
    radar_noise_std_m: float
    evasion_mps: float
    difficulty: float


_PROFILES = ("direct", "crossing", "nap_earth", "spiral", "pop_up", "offset")
_INTRUDERS = ("consumer_quad", "fpv_attack", "shahed136")


def sample_scenario(rng: np.random.Generator, difficulty: float) -> EngagementScenario:
    difficulty = float(np.clip(difficulty, 0.0, 1.0))
    profile_count = 1 + int(round(difficulty * (len(_PROFILES) - 1)))
    intruder_count = 1 + int(round(difficulty * (len(_INTRUDERS) - 1)))
    profile = str(rng.choice(_PROFILES[:profile_count]))
    intruder_type = str(rng.choice(_INTRUDERS[:intruder_count]))
    bearing = float(rng.uniform(-math.pi, math.pi))
    spawn_range = float(rng.uniform(620.0, 800.0 + 700.0 * difficulty))
    altitude_min = 24.0 if profile == "nap_earth" else 70.0
    altitude_max = 130.0 + 230.0 * difficulty
    start_altitude = float(rng.uniform(altitude_min, altitude_max))

    radial = np.asarray([math.sin(bearing), math.cos(bearing)], dtype=np.float32)
    cross = np.asarray([radial[1], -radial[0]], dtype=np.float32)
    fractions = np.asarray([1.0, 0.72, 0.48, 0.28, 0.12, 0.0])
    waypoints = []
    lateral_sign = float(rng.choice((-1.0, 1.0)))
    for index, fraction in enumerate(fractions):
        lateral = 0.0
        altitude = 35.0 + (start_altitude - 35.0) * fraction
        if profile == "crossing":
            lateral = lateral_sign * spawn_range * (0.38 - 0.12 * index)
        elif profile == "spiral":
            lateral = lateral_sign * spawn_range * 0.34 * math.sin(index * 1.35)
        elif profile == "offset":
            lateral = lateral_sign * 180.0 * fraction
        elif profile == "pop_up":
            altitude += 120.0 * math.sin(math.pi * (1.0 - fraction))
        elif profile == "nap_earth":
            altitude = 15.0 + 15.0 * fraction
        horizontal = radial * spawn_range * fraction + cross * lateral
        waypoints.append((float(horizontal[0]), float(horizontal[1]), float(altitude)))

    interceptor_radius = float(rng.uniform(0.0, 80.0 + 520.0 * difficulty))
    interceptor_bearing = float(rng.uniform(-math.pi, math.pi))
    interceptor_start = (
        interceptor_radius * math.sin(interceptor_bearing),
        interceptor_radius * math.cos(interceptor_bearing),
        float(rng.uniform(3.0, 15.0 + 35.0 * difficulty)),
    )
    wind_limit = 1.0 + 10.0 * difficulty
    wind = (
        float(rng.uniform(-wind_limit, wind_limit)),
        float(rng.uniform(-wind_limit, wind_limit)),
        0.0,
    )
    scenario_id = (
        f"{profile}-{intruder_type}-"
        f"b{math.degrees(bearing) % 360:03.0f}-r{spawn_range:04.0f}"
    )
    return EngagementScenario(
        scenario_id=scenario_id,
        intruder_type=intruder_type,
        profile=profile,
        waypoints=tuple(waypoints),
        interceptor_start=tuple(float(value) for value in interceptor_start),
        wind_mps=wind,
        sensor_latency_s=float(rng.uniform(0.0, 0.35 * difficulty)),
        sensor_dropout_probability=float(rng.uniform(0.0, 0.18 * difficulty)),
        radar_noise_std_m=float(rng.uniform(0.2, 0.8 + 4.0 * difficulty)),
        evasion_mps=float(rng.uniform(0.0, 16.0 * difficulty)),
        difficulty=difficulty,
    )
