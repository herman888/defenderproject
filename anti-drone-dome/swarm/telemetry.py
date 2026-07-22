"""Versioned swarm coordination telemetry (``aegis.swarm-coordination.v1``).

A multi-track presentation feed for the swarm: one coordinator, N interceptors, M
threats, plus the live assignment map and RF link health. Reuses the validation and
transport primitives from ``integration/tactical_stream.py``.
"""

from __future__ import annotations

import json
import os
import socket
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from integration.tactical_stream import (  # noqa: E402
    MAX_UDP_PAYLOAD,
    UdpEndpoint,
    _require_number,
    _require_vector,
)

SCHEMA = "aegis.swarm-coordination.v1"

_COORDINATE_FRAME = {
    "type": "local-tangent-plane",
    "axes": "ENU",
    "position_unit": "m",
    "velocity_unit": "m/s",
    "orientation": "xyzw",
}
_INTERCEPTOR_STATES = {"ASSIGNED", "COASTING", "AUTONOMOUS_LOCAL", "RESERVE", "EXPENDED"}
_THREAT_STATUSES = {"ACTIVE", "NEUTRALIZED", "BREACHED", "LEAKER"}


def _require_str(value, label: str) -> None:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{label} must be a non-empty string")


def validate_swarm_packet(packet: dict) -> None:
    if not isinstance(packet, dict):
        raise ValueError("swarm packet must be an object")
    if packet.get("schema") != SCHEMA:
        raise ValueError(f"swarm packet schema must be {SCHEMA}")
    sequence = packet.get("sequence")
    if isinstance(sequence, bool) or not isinstance(sequence, int) or sequence < 0:
        raise ValueError("sequence must be a non-negative integer")
    _require_number(packet.get("mission_time_s"), "mission_time_s", minimum=0.0)
    if packet.get("timestamp_clock") != "simulation-relative":
        raise ValueError("timestamp_clock must be simulation-relative")
    if packet.get("coordinate_frame") != _COORDINATE_FRAME:
        raise ValueError("coordinate_frame must declare local ENU metres and xyzw")

    coordinator = packet.get("coordinator")
    if not isinstance(coordinator, dict):
        raise ValueError("coordinator must be an object")
    _require_str(coordinator.get("id"), "coordinator.id")
    _require_vector(coordinator.get("position_enu_m"), "coordinator.position_enu_m", 3)
    _require_vector(
        coordinator.get("velocity_enu_mps"), "coordinator.velocity_enu_mps", 3
    )

    interceptors = packet.get("interceptors")
    if not isinstance(interceptors, list):
        raise ValueError("interceptors must be a list")
    for idx, interceptor in enumerate(interceptors):
        label = f"interceptors[{idx}]"
        _require_str(interceptor.get("id"), f"{label}.id")
        _require_vector(interceptor.get("position_enu_m"), f"{label}.position_enu_m", 3)
        _require_vector(
            interceptor.get("velocity_enu_mps"), f"{label}.velocity_enu_mps", 3
        )
        if interceptor.get("state") not in _INTERCEPTOR_STATES:
            raise ValueError(f"{label}.state must be one of {sorted(_INTERCEPTOR_STATES)}")
        assigned = interceptor.get("assigned_threat_id")
        if assigned is not None and not (isinstance(assigned, str) and assigned):
            raise ValueError(f"{label}.assigned_threat_id must be a string or null")

    threats = packet.get("threats")
    if not isinstance(threats, list):
        raise ValueError("threats must be a list")
    for idx, threat in enumerate(threats):
        label = f"threats[{idx}]"
        _require_str(threat.get("id"), f"{label}.id")
        _require_str(threat.get("type"), f"{label}.type")
        _require_vector(threat.get("position_enu_m"), f"{label}.position_enu_m", 3)
        _require_vector(threat.get("velocity_enu_mps"), f"{label}.velocity_enu_mps", 3)
        if threat.get("status") not in _THREAT_STATUSES:
            raise ValueError(f"{label}.status must be one of {sorted(_THREAT_STATUSES)}")

    if not isinstance(packet.get("assignment"), dict):
        raise ValueError("assignment must be an object")
    if not isinstance(packet.get("link_health"), dict):
        raise ValueError("link_health must be an object")


def build_swarm_packet(
    *,
    mission_time_s: float,
    coordinator: dict,
    interceptors: list,
    threats: list,
    assignment: dict,
    link_health: dict,
) -> dict:
    """Assemble a schema-shaped packet body (sequence is added by the publisher)."""
    return {
        "mission_time_s": float(mission_time_s),
        "timestamp_clock": "simulation-relative",
        "coordinate_frame": dict(_COORDINATE_FRAME),
        "coordinator": coordinator,
        "interceptors": interceptors,
        "threats": threats,
        "assignment": assignment,
        "link_health": link_health,
    }


def encode_swarm_packet(packet: dict) -> bytes:
    validate_swarm_packet(packet)
    payload = json.dumps(packet, separators=(",", ":"), allow_nan=False).encode("utf-8")
    if len(payload) > MAX_UDP_PAYLOAD:
        raise ValueError(f"swarm packet exceeds UDP payload limit: {len(payload)} bytes")
    return payload


class SwarmTelemetryPublisher:
    """Publishes ``aegis.swarm-coordination.v1`` snapshots over UDP."""

    def __init__(self, endpoint: UdpEndpoint):
        self.endpoint = endpoint
        self._sequence = 0
        self._socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    @classmethod
    def from_endpoint(cls, value: str) -> "SwarmTelemetryPublisher":
        return cls(UdpEndpoint.parse(value))

    def publish(self, body: dict) -> dict:
        packet = {"schema": SCHEMA, "sequence": self._sequence, **body}
        payload = encode_swarm_packet(packet)
        self._socket.sendto(payload, (self.endpoint.host, self.endpoint.port))
        self._sequence += 1
        return packet

    def close(self) -> None:
        self._socket.close()
