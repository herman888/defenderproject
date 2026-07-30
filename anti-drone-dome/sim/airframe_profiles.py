"""Validated, versioned airframe profiles for simulation and calibration."""

from __future__ import annotations

import json
import math
import os
from copy import deepcopy


SCHEMA = "aegis.airframe-profiles.v1"
_CATALOG_PATH = os.path.join(
    os.path.dirname(__file__),
    "..",
    "scenario_data",
    "airframe_profiles_v1.json",
)
_EVIDENCE_STATUSES = {
    "design-placeholder",
    "representative-unvalidated",
    "bench-validated",
    "flight-validated",
}


def _positive(value, label: str, *, allow_zero: bool = False) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be numeric")
    value = float(value)
    if not math.isfinite(value):
        raise ValueError(f"{label} must be finite")
    if value < 0.0 or (value == 0.0 and not allow_zero):
        qualifier = "non-negative" if allow_zero else "positive"
        raise ValueError(f"{label} must be {qualifier}")
    return value


def validate_airframe_profile(profile: dict) -> None:
    for key in (
        "profile_id",
        "vehicle_role",
        "vehicle_type",
        "dynamics_model",
        "geometry",
        "rigid_body",
        "propulsion",
        "aerodynamics",
        "disturbance",
        "flight_envelope",
        "evidence",
    ):
        if key not in profile:
            raise ValueError(f"airframe profile missing {key}")
    for key in ("profile_id", "vehicle_role", "vehicle_type"):
        if not isinstance(profile[key], str) or not profile[key]:
            raise ValueError(f"{key} must be a non-empty string")
    if profile["dynamics_model"] not in {"legacy", "fidelity_v1"}:
        raise ValueError("dynamics_model must be legacy or fidelity_v1")

    geometry = profile["geometry"]
    for key in ("length_m", "wingspan_m", "height_m", "visual_scale"):
        _positive(geometry.get(key), f"geometry.{key}")

    rigid_body = profile["rigid_body"]
    _positive(rigid_body.get("mass_kg"), "rigid_body.mass_kg")
    inertia = rigid_body.get("inertia_kg_m2")
    if not isinstance(inertia, list) or len(inertia) != 3:
        raise ValueError("rigid_body.inertia_kg_m2 must contain three values")
    for value in inertia:
        _positive(value, "rigid_body.inertia_kg_m2")

    propulsion = profile["propulsion"]
    for key in (
        "max_speed_mps",
        "max_horizontal_force_n",
        "vertical_force_max_n",
        "actuator_time_constant_s",
        "force_slew_rate_nps",
        "energy_capacity_wh",
        "minimum_voltage_fraction",
    ):
        _positive(propulsion.get(key), f"propulsion.{key}")
    minimum_force = propulsion.get("vertical_force_min_n")
    if (
        isinstance(minimum_force, bool)
        or not isinstance(minimum_force, (int, float))
        or not math.isfinite(float(minimum_force))
    ):
        raise ValueError("propulsion.vertical_force_min_n must be finite")
    if float(minimum_force) > float(propulsion["vertical_force_max_n"]):
        raise ValueError(
            "vertical_force_min_n cannot exceed vertical_force_max_n"
        )
    voltage = float(propulsion["minimum_voltage_fraction"])
    if not 0.0 < voltage <= 1.0:
        raise ValueError("minimum_voltage_fraction must be in (0, 1]")

    aerodynamics = profile["aerodynamics"]
    for key in (
        "drag_coefficient",
        "drag_area_m2",
        "lift_coefficient",
        "wing_area_m2",
        "stall_speed_mps",
        "stall_angle_deg",
    ):
        _positive(
            aerodynamics.get(key),
            f"aerodynamics.{key}",
            allow_zero=key in {"lift_coefficient", "stall_speed_mps"},
        )
    disturbance = profile["disturbance"]
    _positive(
        disturbance.get("turbulence_force_std_n"),
        "disturbance.turbulence_force_std_n",
        allow_zero=True,
    )
    if not isinstance(disturbance.get("seed"), int):
        raise ValueError("disturbance.seed must be an integer")
    envelope = profile["flight_envelope"]
    for key in ("max_lateral_accel_g", "max_climb_rate_mps", "max_descent_rate_mps"):
        _positive(envelope.get(key), f"flight_envelope.{key}")
    for key in (
        "attitude_response_time_s",
        "yaw_response_time_s",
        "max_tilt_deg",
    ):
        if key in envelope:
            _positive(envelope[key], f"flight_envelope.{key}")
    if float(envelope.get("max_tilt_deg", 40.0)) >= 90.0:
        raise ValueError("flight_envelope.max_tilt_deg must be below 90")
    _positive(
        envelope.get("min_airspeed_mps"),
        "flight_envelope.min_airspeed_mps",
        allow_zero=True,
    )
    if not isinstance(envelope.get("fixed_wing"), bool):
        raise ValueError("flight_envelope.fixed_wing must be a boolean")
    evidence = profile["evidence"]
    if evidence.get("status") not in _EVIDENCE_STATUSES:
        raise ValueError("unsupported evidence.status")
    for key in ("source", "notes"):
        if not isinstance(evidence.get(key), str) or not evidence[key]:
            raise ValueError(f"evidence.{key} must be a non-empty string")


def load_airframe_catalog(path: str = _CATALOG_PATH) -> dict[str, dict]:
    with open(path, encoding="utf-8") as handle:
        data = json.load(handle)
    if data.get("schema") != SCHEMA:
        raise ValueError(f"airframe catalog schema must be {SCHEMA}")
    profiles = data.get("profiles")
    if not isinstance(profiles, list) or not profiles:
        raise ValueError("airframe catalog requires profiles")
    catalog = {}
    for profile in profiles:
        validate_airframe_profile(profile)
        profile_id = profile["profile_id"]
        if profile_id in catalog:
            raise ValueError(f"duplicate airframe profile_id: {profile_id}")
        catalog[profile_id] = profile
    return catalog


_CATALOG = load_airframe_catalog()


def get_airframe_profile(profile_id: str) -> dict:
    if profile_id not in _CATALOG:
        raise KeyError(f"unknown airframe profile: {profile_id}")
    return deepcopy(_CATALOG[profile_id])
