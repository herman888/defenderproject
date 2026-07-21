"""Versioned named stress scenarios for repeatable regression campaigns."""

from __future__ import annotations

import json
import math
import os
from dataclasses import dataclass

import numpy as np

from ml.scenario_curriculum import EngagementScenario


SCHEMA = "aegis.regression-campaign.v1"
_PROFILES = {"direct", "crossing", "nap_earth", "spiral", "pop_up", "offset"}
_INTRUDERS = {"consumer_quad", "fpv_attack", "shahed136"}


@dataclass(frozen=True)
class StressCase:
    case_id: str
    label: str
    tags: tuple[str, ...]
    scenario: EngagementScenario
    gates: dict


def _waypoints(case: dict) -> tuple[tuple[float, float, float], ...]:
    bearing = math.radians(float(case["bearing_deg"]))
    spawn_range = float(case["spawn_range_m"])
    start_altitude = float(case["start_altitude_m"])
    profile = case["profile"]
    radial = np.asarray([math.sin(bearing), math.cos(bearing)], dtype=float)
    cross = np.asarray([radial[1], -radial[0]], dtype=float)
    fractions = (1.0, 0.72, 0.48, 0.28, 0.12, 0.0)
    result = []
    for index, fraction in enumerate(fractions):
        lateral = 0.0
        altitude = 35.0 + (start_altitude - 35.0) * fraction
        if profile == "crossing":
            lateral = spawn_range * (0.38 - 0.12 * index)
        elif profile == "spiral":
            lateral = spawn_range * 0.34 * math.sin(index * 1.35)
        elif profile == "offset":
            lateral = 180.0 * fraction
        elif profile == "pop_up":
            altitude += 120.0 * math.sin(math.pi * (1.0 - fraction))
        elif profile == "nap_earth":
            altitude = 15.0 + 15.0 * fraction
        horizontal = radial * spawn_range * fraction + cross * lateral
        result.append((float(horizontal[0]), float(horizontal[1]), float(altitude)))
    return tuple(result)


def load_campaign(path: str) -> dict:
    with open(os.path.abspath(path), encoding="utf-8") as handle:
        data = json.load(handle)
    if data.get("schema") != SCHEMA:
        raise ValueError(f"campaign schema must be {SCHEMA}")
    defaults = data.get("defaults")
    scenarios = data.get("scenarios")
    if not isinstance(defaults, dict) or not isinstance(scenarios, list) or not scenarios:
        raise ValueError("campaign requires defaults and at least one scenario")
    seen = set()
    cases = []
    for item in scenarios:
        case_id = item.get("id")
        if not isinstance(case_id, str) or not case_id or case_id in seen:
            raise ValueError("scenario IDs must be non-empty and unique")
        seen.add(case_id)
        if item.get("profile") not in _PROFILES:
            raise ValueError(f"{case_id}: unsupported profile")
        if item.get("intruder_type") not in _INTRUDERS:
            raise ValueError(f"{case_id}: unsupported intruder type")
        dropout = float(item["sensor_dropout_probability"])
        if not 0.0 <= dropout <= 1.0:
            raise ValueError(f"{case_id}: dropout probability must be in [0, 1]")
        gates = {
            key: item.get(key, value)
            for key, value in defaults.items()
        }
        scenario = EngagementScenario(
            scenario_id=case_id,
            intruder_type=item["intruder_type"],
            profile=item["profile"],
            waypoints=_waypoints(item),
            interceptor_start=tuple(float(v) for v in item["interceptor_start_m"]),
            wind_mps=tuple(float(v) for v in item["wind_mps"]),
            sensor_latency_s=float(item["sensor_latency_s"]),
            sensor_dropout_probability=dropout,
            radar_noise_std_m=float(item["radar_noise_std_m"]),
            evasion_mps=float(item["evasion_mps"]),
            difficulty=float(item["difficulty"]),
        )
        cases.append(StressCase(
            case_id=case_id,
            label=str(item["label"]),
            tags=tuple(str(tag) for tag in item.get("tags", [])),
            scenario=scenario,
            gates=gates,
        ))
    return {
        "schema": data["schema"],
        "campaign_id": data["campaign_id"],
        "description": data.get("description", ""),
        "cases": tuple(cases),
    }
