"""Validated swarm scenario catalog: saturation attacks and the defending swarm."""

from __future__ import annotations

import json
import math
import os
from dataclasses import dataclass, field

from swarm.rf_link import RfLinkConfig

SCHEMA = "aegis.swarm-scenarios.v1"
_CATALOG_PATH = os.path.join(
    os.path.dirname(__file__), "..", "scenario_data", "swarm_scenarios_v1.json"
)
_THREAT_LEVELS = {"HIGH", "MEDIUM", "LOW"}


def _vec3(value, label: str):
    if not isinstance(value, list) or len(value) != 3:
        raise ValueError(f"{label} must contain three numbers")
    out = []
    for i, component in enumerate(value):
        if isinstance(component, bool) or not isinstance(component, (int, float)):
            raise ValueError(f"{label}[{i}] must be numeric")
        if not math.isfinite(float(component)):
            raise ValueError(f"{label}[{i}] must be finite")
        out.append(float(component))
    return tuple(out)


def _positive(value, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be numeric")
    value = float(value)
    if not math.isfinite(value) or value <= 0.0:
        raise ValueError(f"{label} must be a positive number")
    return value


@dataclass(frozen=True)
class ThreatSpec:
    id: str
    type: str
    threat_level: str
    start_enu_m: tuple
    max_speed_mps: float
    waypoints_enu_m: tuple = ()


@dataclass(frozen=True)
class InterceptorSpec:
    id: str
    airframe_profile_id: str
    start_enu_m: tuple
    max_speed_mps: float = 70.0


@dataclass(frozen=True)
class CoordinatorSpec:
    id: str
    start_enu_m: tuple
    rf_link: RfLinkConfig
    policy: str = "greedy"
    compute: dict = field(default_factory=dict)


@dataclass(frozen=True)
class SwarmScenario:
    scenario_id: str
    description: str
    seed: int
    protected_center_enu_m: tuple
    coordinator: CoordinatorSpec
    interceptors: tuple
    threats: tuple
    duration_limit_s: float = 90.0
    breach_radius_m: float = 12.0
    intercept_radius_m: float = 18.0


def _parse_threat(data: dict) -> ThreatSpec:
    for key in ("id", "type", "threat_level"):
        if not isinstance(data.get(key), str) or not data[key]:
            raise ValueError(f"threat.{key} must be a non-empty string")
    if data["threat_level"].upper() not in _THREAT_LEVELS:
        raise ValueError(f"threat.threat_level must be one of {sorted(_THREAT_LEVELS)}")
    waypoints = tuple(
        _vec3(wp, "threat.waypoints_enu_m[]")
        for wp in data.get("waypoints_enu_m", [])
    )
    return ThreatSpec(
        id=data["id"],
        type=data["type"],
        threat_level=data["threat_level"].upper(),
        start_enu_m=_vec3(data.get("start_enu_m"), "threat.start_enu_m"),
        max_speed_mps=_positive(data.get("max_speed_mps"), "threat.max_speed_mps"),
        waypoints_enu_m=waypoints,
    )


def _parse_interceptor(data: dict) -> InterceptorSpec:
    for key in ("id", "airframe_profile_id"):
        if not isinstance(data.get(key), str) or not data[key]:
            raise ValueError(f"interceptor.{key} must be a non-empty string")
    return InterceptorSpec(
        id=data["id"],
        airframe_profile_id=data["airframe_profile_id"],
        start_enu_m=_vec3(data.get("start_enu_m"), "interceptor.start_enu_m"),
        max_speed_mps=_positive(
            data.get("max_speed_mps", 70.0), "interceptor.max_speed_mps"
        ),
    )


def _parse_coordinator(data: dict) -> CoordinatorSpec:
    if not isinstance(data.get("id"), str) or not data["id"]:
        raise ValueError("coordinator.id must be a non-empty string")
    policy = data.get("policy", "greedy")
    if policy not in ("greedy", "hungarian"):
        raise ValueError("coordinator.policy must be 'greedy' or 'hungarian'")
    return CoordinatorSpec(
        id=data["id"],
        start_enu_m=_vec3(data.get("start_enu_m"), "coordinator.start_enu_m"),
        rf_link=RfLinkConfig.from_dict(data.get("rf_link", {})),
        policy=policy,
        compute=dict(data.get("compute", {})),
    )


def _parse_scenario(data: dict) -> SwarmScenario:
    if not isinstance(data.get("scenario_id"), str) or not data["scenario_id"]:
        raise ValueError("scenario_id must be a non-empty string")
    seed = data.get("seed")
    if isinstance(seed, bool) or not isinstance(seed, int):
        raise ValueError("scenario seed must be an integer")
    interceptors = tuple(_parse_interceptor(i) for i in data.get("interceptors", []))
    threats = tuple(_parse_threat(t) for t in data.get("threats", []))
    if not interceptors:
        raise ValueError("scenario requires at least one interceptor")
    if not threats:
        raise ValueError("scenario requires at least one threat")
    ids = [t.id for t in threats] + [i.id for i in interceptors]
    if len(ids) != len(set(ids)):
        raise ValueError("threat/interceptor ids must be unique within a scenario")
    return SwarmScenario(
        scenario_id=data["scenario_id"],
        description=str(data.get("description", "")),
        seed=seed,
        protected_center_enu_m=_vec3(
            data.get("protected_center_enu_m", [0.0, 0.0, 0.0]),
            "protected_center_enu_m",
        ),
        coordinator=_parse_coordinator(data.get("coordinator", {})),
        interceptors=interceptors,
        threats=threats,
        duration_limit_s=_positive(
            data.get("duration_limit_s", 90.0), "duration_limit_s"
        ),
        breach_radius_m=_positive(data.get("breach_radius_m", 12.0), "breach_radius_m"),
        intercept_radius_m=_positive(
            data.get("intercept_radius_m", 18.0), "intercept_radius_m"
        ),
    )


def load_swarm_catalog(path: str = _CATALOG_PATH) -> dict:
    with open(path, encoding="utf-8") as handle:
        data = json.load(handle)
    if data.get("schema") != SCHEMA:
        raise ValueError(f"swarm scenario catalog schema must be {SCHEMA}")
    scenarios = data.get("scenarios")
    if not isinstance(scenarios, list) or not scenarios:
        raise ValueError("swarm scenario catalog requires scenarios")
    catalog: dict = {}
    for entry in scenarios:
        scenario = _parse_scenario(entry)
        if scenario.scenario_id in catalog:
            raise ValueError(f"duplicate scenario_id: {scenario.scenario_id}")
        catalog[scenario.scenario_id] = scenario
    return catalog


def get_swarm_scenario(scenario_id: str, path: str = _CATALOG_PATH) -> SwarmScenario:
    catalog = load_swarm_catalog(path)
    if scenario_id not in catalog:
        raise KeyError(
            f"unknown swarm scenario: {scenario_id} (have {sorted(catalog)})"
        )
    return catalog[scenario_id]
