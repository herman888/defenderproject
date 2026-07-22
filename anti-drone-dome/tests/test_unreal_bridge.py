"""Unit tests for the Unreal/Cesium telemetry bridge."""

import json
import math
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from integration.tactical_stream import encode_tactical_packet
from integration.unreal_bridge import (
    BRIDGE_SCHEMA,
    UnrealTelemetryBridge,
    UdpEndpoint,
    _geodetic_to_ecef,
    enrich_packet,
    geodetic_from_enu,
)
from sim.geospatial import geodetic_to_enu


_ORIGIN = {"latitude": 43.25, "longitude": -79.87, "altitude_m": 100.0}


def _enu_from_geodetic(origin, latitude, longitude, altitude):
    """Independent inverse (ENU from geodetic) for round-trip verification."""
    x0, y0, z0 = _geodetic_to_ecef(
        origin["latitude"], origin["longitude"], origin["altitude_m"]
    )
    x, y, z = _geodetic_to_ecef(latitude, longitude, altitude)
    dx, dy, dz = x - x0, y - y0, z - z0
    lat0 = math.radians(origin["latitude"])
    lon0 = math.radians(origin["longitude"])
    east = -math.sin(lon0) * dx + math.cos(lon0) * dy
    north = (
        -math.sin(lat0) * math.cos(lon0) * dx
        - math.sin(lat0) * math.sin(lon0) * dy
        + math.cos(lat0) * dz
    )
    up = (
        math.cos(lat0) * math.cos(lon0) * dx
        + math.cos(lat0) * math.sin(lon0) * dy
        + math.sin(lat0) * dz
    )
    return east, north, up


def _valid_packet(sequence=0, mission_time_s=0.0, interceptor=True):
    packet = {
        "schema": "aegis.tactical.v1",
        "sequence": sequence,
        "mission_time_s": mission_time_s,
        "timestamp_clock": "simulation-relative",
        "status": "ENGAGING",
        "site": "Test Range",
        "guidance": "apn",
        "coordinate_frame": {
            "type": "local-tangent-plane",
            "axes": "ENU",
            "position_unit": "m",
            "velocity_unit": "m/s",
            "orientation": "xyzw",
        },
        "georeference": {"origin": dict(_ORIGIN), "status": "placeholder"},
        "terrain": {"source": "procedural", "collision_authoritative": True},
        "tracks": {
            "intruder": {
                "id": "TRK-001",
                "role": "intruder",
                "asset_id": "intruder/shahed136",
                "type": "shahed136",
                "position_enu_m": [1200.0, -800.0, 300.0],
                "velocity_enu_mps": [30.0, 0.0, 0.0],
                "orientation_xyzw": [0.0, 0.0, 0.0, 1.0],
            },
            "interceptor": (
                {
                    "id": "INT-01",
                    "role": "interceptor",
                    "asset_id": "interceptor/default",
                    "type": "interceptor",
                    "position_enu_m": [0.0, 0.0, 50.0],
                    "velocity_enu_mps": [0.0, 40.0, 5.0],
                    "orientation_xyzw": [0.0, 0.0, 0.0, 1.0],
                }
                if interceptor
                else None
            ),
        },
        "predicted_intercept_enu_m": [600.0, -400.0, 175.0],
    }
    return packet


def test_geodetic_from_enu_zero_offset_returns_origin():
    latitude, longitude, altitude = geodetic_from_enu(_ORIGIN, 0.0, 0.0, 0.0)
    assert latitude == pytest.approx(_ORIGIN["latitude"], abs=1e-9)
    assert longitude == pytest.approx(_ORIGIN["longitude"], abs=1e-9)
    assert altitude == pytest.approx(_ORIGIN["altitude_m"], abs=1e-6)


@pytest.mark.parametrize(
    "east,north,up",
    [(1000.0, 0.0, 0.0), (0.0, 1500.0, 0.0), (1200.0, -800.0, 300.0)],
)
def test_geodetic_from_enu_round_trips(east, north, up):
    latitude, longitude, altitude = geodetic_from_enu(_ORIGIN, east, north, up)
    back = _enu_from_geodetic(_ORIGIN, latitude, longitude, altitude)
    assert back[0] == pytest.approx(east, abs=1e-4)
    assert back[1] == pytest.approx(north, abs=1e-4)
    assert back[2] == pytest.approx(up, abs=1e-4)


def test_geodetic_from_enu_matches_spherical_approximation():
    # The repo's spherical helper is a coarse cross-check for sign/scale.
    east, north = 900.0, -600.0
    latitude, longitude, _ = geodetic_from_enu(_ORIGIN, east, north, 0.0)
    approx_east, approx_north = geodetic_to_enu(
        latitude, longitude, _ORIGIN["latitude"], _ORIGIN["longitude"]
    )
    assert approx_east == pytest.approx(east, rel=0.01)
    assert approx_north == pytest.approx(north, rel=0.01)


def test_enrich_packet_adds_geodetic_and_preserves_enu():
    packet = _valid_packet()
    enriched = enrich_packet(packet)

    assert enriched["bridge_schema"] == BRIDGE_SCHEMA
    intruder = enriched["tracks"]["intruder"]
    # ENU is preserved untouched.
    assert intruder["position_enu_m"] == [1200.0, -800.0, 300.0]
    # Geodetic added and self-consistent with the forward transform.
    expected = geodetic_from_enu(_ORIGIN, 1200.0, -800.0, 300.0)
    assert intruder["geodetic"]["latitude"] == pytest.approx(expected[0])
    assert intruder["geodetic"]["longitude"] == pytest.approx(expected[1])
    assert intruder["geodetic"]["altitude_m"] == pytest.approx(expected[2])
    # Intruder velocity is due east -> heading 90 deg.
    assert intruder["heading_deg"] == pytest.approx(90.0)
    assert intruder["speed_mps"] == pytest.approx(30.0)
    assert "predicted_intercept_geodetic" in enriched


def test_enrich_packet_handles_null_interceptor():
    enriched = enrich_packet(_valid_packet(interceptor=False))
    assert enriched["tracks"]["interceptor"] is None


def test_enrich_packet_does_not_mutate_input():
    packet = _valid_packet()
    enrich_packet(packet)
    assert "geodetic" not in packet["tracks"]["intruder"]
    assert "bridge_schema" not in packet


def test_heading_cardinal_directions():
    packet = _valid_packet()
    packet["tracks"]["intruder"]["velocity_enu_mps"] = [0.0, 10.0, 0.0]
    assert enrich_packet(packet)["tracks"]["intruder"]["heading_deg"] == pytest.approx(0.0)
    packet["tracks"]["intruder"]["velocity_enu_mps"] = [-10.0, 0.0, 0.0]
    assert enrich_packet(packet)["tracks"]["intruder"]["heading_deg"] == pytest.approx(270.0)


def _bridge():
    return UnrealTelemetryBridge(
        UdpEndpoint("127.0.0.1", 8787), UdpEndpoint("127.0.0.1", 8788)
    )


def test_process_datagram_accepts_valid_packet():
    bridge = _bridge()
    enriched = bridge.process_datagram(encode_tactical_packet(_valid_packet()))
    assert enriched is not None
    assert enriched["bridge_schema"] == BRIDGE_SCHEMA
    assert bridge.stats.received == 1
    assert bridge.stats.rejected == 0


def test_process_datagram_rejects_malformed_json():
    bridge = _bridge()
    assert bridge.process_datagram(b"not-json{") is None
    assert bridge.stats.rejected == 1


def test_process_datagram_rejects_stale_sequence():
    bridge = _bridge()
    bridge.process_datagram(encode_tactical_packet(_valid_packet(5, 5.0)))
    # A lower sequence must be rejected, not raised.
    assert bridge.process_datagram(encode_tactical_packet(_valid_packet(3, 6.0))) is None
    assert bridge.stats.rejected == 1


def test_process_datagram_counts_upstream_gaps():
    bridge = _bridge()
    bridge.process_datagram(encode_tactical_packet(_valid_packet(0, 0.0)))
    bridge.process_datagram(encode_tactical_packet(_valid_packet(3, 1.0)))
    assert bridge.stats.dropped_upstream == 2
