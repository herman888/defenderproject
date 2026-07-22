"""Tests for the aegis.swarm-coordination.v1 telemetry packet."""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from swarm.telemetry import (
    SCHEMA,
    build_swarm_packet,
    encode_swarm_packet,
    validate_swarm_packet,
)


def _packet(sequence=0):
    body = build_swarm_packet(
        mission_time_s=1.5,
        coordinator={
            "id": "coordinator-01",
            "position_enu_m": [0.0, -110.0, 150.0],
            "velocity_enu_mps": [0.0, 0.0, 0.0],
        },
        interceptors=[{
            "id": "int-1",
            "position_enu_m": [10.0, -20.0, 30.0],
            "velocity_enu_mps": [5.0, 40.0, 1.0],
            "assigned_threat_id": "thr-1",
            "state": "ASSIGNED",
            "link_margin_db": 22.0,
            "energy_remaining_fraction": 0.9,
        }],
        threats=[{
            "id": "thr-1",
            "type": "shahed136",
            "threat_level": "HIGH",
            "position_enu_m": [200.0, 300.0, 120.0],
            "velocity_enu_mps": [-20.0, -30.0, 0.0],
            "status": "ACTIVE",
        }],
        assignment={"thr-1": "int-1"},
        link_health={"packets_delivered": 5, "packets_dropped": 0, "delivery_ratio": 1.0},
    )
    return {"schema": SCHEMA, "sequence": sequence, **body}


def test_valid_packet_passes_and_encodes():
    packet = _packet()
    validate_swarm_packet(packet)          # no raise
    payload = encode_swarm_packet(packet)
    assert isinstance(payload, bytes) and payload


def test_null_assigned_threat_is_allowed():
    packet = _packet()
    packet["interceptors"][0]["assigned_threat_id"] = None
    packet["interceptors"][0]["state"] = "RESERVE"
    validate_swarm_packet(packet)


@pytest.mark.parametrize("mutate", [
    lambda p: p.update(schema="wrong"),
    lambda p: p.pop("coordinator"),
    lambda p: p["interceptors"][0].update(state="BOGUS"),
    lambda p: p["threats"][0].update(status="BOGUS"),
    lambda p: p["coordinator"].update(position_enu_m=[0.0, 1.0]),
    lambda p: p.update(sequence=-1),
])
def test_invalid_packets_are_rejected(mutate):
    packet = _packet()
    mutate(packet)
    with pytest.raises(ValueError):
        validate_swarm_packet(packet)
