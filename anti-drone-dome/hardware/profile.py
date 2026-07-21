"""Validated hardware-profile loading for SIL, HIL, and read-only lab use."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass


_MODES = {"sil", "sitl", "hil", "hardware_readonly"}
_PROTOCOLS = {"internal", "mavlink", "msp", "ros2", "udp"}


@dataclass(frozen=True)
class HardwareProfile:
    path: str
    data: dict

    @property
    def profile_id(self) -> str:
        return self.data["profile_id"]

    @property
    def label(self) -> str:
        return self.data["label"]

    @property
    def mode(self) -> str:
        return self.data["mode"]

    @property
    def protocol(self) -> str:
        return self.data["autopilot"]["protocol"]

    @property
    def actuation_enabled(self) -> bool:
        return bool(self.data["safety"]["actuation_enabled"])

    def summary(self) -> dict:
        return {
            "profile_id": self.profile_id,
            "label": self.label,
            "mode": self.mode,
            "autopilot_protocol": self.protocol,
            "actuation_enabled": self.actuation_enabled,
            "vehicle": self.data["vehicle"],
            "sensors": self.data["sensors"],
            "validation_gates": self.data["validation_gates"],
        }


def _require_number(mapping: dict, key: str, minimum: float = 0.0) -> float:
    value = mapping.get(key)
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise ValueError(f"{key} must be numeric")
    value = float(value)
    if value < minimum:
        raise ValueError(f"{key} must be >= {minimum}")
    return value


def validate_hardware_profile(data: dict) -> None:
    if data.get("schema") != "aegis.hardware-profile.v1":
        raise ValueError("hardware profile schema must be aegis.hardware-profile.v1")
    for key in ("profile_id", "label", "mode", "autopilot", "vehicle", "sensors",
                "links", "safety", "validation_gates"):
        if key not in data:
            raise ValueError(f"hardware profile missing {key}")
    if data["mode"] not in _MODES:
        raise ValueError(f"unsupported hardware mode: {data['mode']}")
    protocol = data["autopilot"].get("protocol")
    if protocol not in _PROTOCOLS:
        raise ValueError(f"unsupported autopilot protocol: {protocol}")

    vehicle = data["vehicle"]
    _require_number(vehicle, "mass_kg", 0.01)
    _require_number(vehicle, "max_speed_mps", 0.1)
    _require_number(vehicle, "max_accel_mps2", 0.1)
    _require_number(vehicle, "battery_capacity_wh", 0.1)

    safety = data["safety"]
    if not isinstance(safety.get("actuation_enabled"), bool):
        raise ValueError("safety.actuation_enabled must be boolean")
    if data["mode"] == "hardware_readonly" and safety["actuation_enabled"]:
        raise ValueError("hardware_readonly profiles cannot enable actuation")
    if data["mode"] in {"hil", "hardware_readonly"} and safety["actuation_enabled"]:
        if not safety.get("requires_explicit_arm_ack", False):
            raise ValueError(
                "hardware actuation requires safety.requires_explicit_arm_ack"
            )
        if not safety.get("requires_props_removed_ack", False):
            raise ValueError(
                "hardware actuation requires safety.requires_props_removed_ack"
            )

    gates = data["validation_gates"]
    for key in (
        "minimum_intercept_rate",
        "maximum_duration_p95_s",
        "maximum_energy_p95",
        "maximum_action_saturation_fraction",
        "maximum_trajectory_rmse_m",
        "maximum_timing_offset_s",
    ):
        _require_number(gates, key, 0.0)
    if gates["minimum_intercept_rate"] > 1.0:
        raise ValueError("minimum_intercept_rate must be <= 1")
    if gates["maximum_action_saturation_fraction"] > 1.0:
        raise ValueError("maximum_action_saturation_fraction must be <= 1")


def load_hardware_profile(path: str) -> HardwareProfile:
    absolute_path = os.path.abspath(path)
    with open(absolute_path, encoding="utf-8") as handle:
        data = json.load(handle)
    validate_hardware_profile(data)
    return HardwareProfile(path=absolute_path, data=data)
