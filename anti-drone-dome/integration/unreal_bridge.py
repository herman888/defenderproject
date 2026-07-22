"""Bridge validated aegis.tactical.v1 UDP telemetry to Unreal Engine / Cesium.

The simulator publishes compact, engine-agnostic tactical packets in a local
ENU tangent plane (see ``integration.tactical_stream``). Unreal clients want two
things this module adds without altering the authoritative feed:

* **Geodetic coordinates** (WGS84 latitude/longitude/altitude) so a Cesium for
  Unreal ``CesiumGeoreference`` can place tracks directly on the globe.
* **Heading and speed** so actors can be oriented without client-side math.

The original ENU vectors are preserved, so a flat local-level Unreal map can
keep using them unchanged. The bridge validates every datagram, enforces
sequence ordering, tolerates duplicate/out-of-order UDP, and re-emits an
enriched ``aegis.unreal-bridge.v1`` packet over UDP.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import socket
import sys
from dataclasses import dataclass

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from integration.tactical_stream import (  # noqa: E402
    MAX_UDP_PAYLOAD,
    TacticalSequenceTracker,
    UdpEndpoint,
    validate_tactical_packet,
)

BRIDGE_SCHEMA = "aegis.unreal-bridge.v1"

# WGS84 ellipsoid constants.
_WGS84_A = 6378137.0
_WGS84_F = 1.0 / 298.257223563
_WGS84_B = _WGS84_A * (1.0 - _WGS84_F)
_WGS84_E2 = _WGS84_F * (2.0 - _WGS84_F)
_WGS84_EP2 = (_WGS84_A ** 2 - _WGS84_B ** 2) / (_WGS84_B ** 2)


def _geodetic_to_ecef(lat_deg: float, lon_deg: float, height_m: float):
    lat = math.radians(lat_deg)
    lon = math.radians(lon_deg)
    sin_lat = math.sin(lat)
    cos_lat = math.cos(lat)
    prime_vertical = _WGS84_A / math.sqrt(1.0 - _WGS84_E2 * sin_lat * sin_lat)
    x = (prime_vertical + height_m) * cos_lat * math.cos(lon)
    y = (prime_vertical + height_m) * cos_lat * math.sin(lon)
    z = (prime_vertical * (1.0 - _WGS84_E2) + height_m) * sin_lat
    return x, y, z


def _ecef_to_geodetic(x: float, y: float, z: float):
    """Closed-form Bowring conversion from ECEF to WGS84 geodetic."""
    lon = math.atan2(y, x)
    p = math.hypot(x, y)
    theta = math.atan2(z * _WGS84_A, p * _WGS84_B)
    sin_theta = math.sin(theta)
    cos_theta = math.cos(theta)
    lat = math.atan2(
        z + _WGS84_EP2 * _WGS84_B * sin_theta ** 3,
        p - _WGS84_E2 * _WGS84_A * cos_theta ** 3,
    )
    sin_lat = math.sin(lat)
    prime_vertical = _WGS84_A / math.sqrt(1.0 - _WGS84_E2 * sin_lat * sin_lat)
    cos_lat = math.cos(lat)
    if abs(cos_lat) < 1e-12:
        height = abs(z) - _WGS84_B
    else:
        height = p / cos_lat - prime_vertical
    return math.degrees(lat), math.degrees(lon), height


def geodetic_from_enu(origin: dict, east: float, north: float, up: float):
    """Convert a local ENU offset (metres) about ``origin`` to WGS84 lat/lon/alt."""
    lat0 = float(origin["latitude"])
    lon0 = float(origin["longitude"])
    height0 = float(origin["altitude_m"])
    x0, y0, z0 = _geodetic_to_ecef(lat0, lon0, height0)

    lat = math.radians(lat0)
    lon = math.radians(lon0)
    sin_lat = math.sin(lat)
    cos_lat = math.cos(lat)
    sin_lon = math.sin(lon)
    cos_lon = math.cos(lon)

    dx = -sin_lon * east - sin_lat * cos_lon * north + cos_lat * cos_lon * up
    dy = cos_lon * east - sin_lat * sin_lon * north + cos_lat * sin_lon * up
    dz = cos_lat * north + sin_lat * up
    return _ecef_to_geodetic(x0 + dx, y0 + dy, z0 + dz)


def _heading_and_speed(velocity_enu):
    east, north, up = (float(component) for component in velocity_enu)
    ground_speed = math.hypot(east, north)
    speed = math.sqrt(east * east + north * north + up * up)
    # Compass heading: 0 deg = North, increasing clockwise toward East.
    heading = math.degrees(math.atan2(east, north)) % 360.0
    return heading, ground_speed, speed


def _enrich_track(track: dict | None, origin: dict) -> dict | None:
    if track is None:
        return None
    east, north, up = track["position_enu_m"]
    latitude, longitude, altitude = geodetic_from_enu(origin, east, north, up)
    heading, ground_speed, speed = _heading_and_speed(track["velocity_enu_mps"])
    enriched = dict(track)
    enriched["geodetic"] = {
        "latitude": latitude,
        "longitude": longitude,
        "altitude_m": altitude,
    }
    enriched["heading_deg"] = heading
    enriched["ground_speed_mps"] = ground_speed
    enriched["speed_mps"] = speed
    return enriched


def enrich_packet(packet: dict) -> dict:
    """Return a geodetic-augmented copy of a validated tactical packet.

    The ENU fields and every original key are preserved; new geodetic data is
    added alongside them under ``aegis.unreal-bridge.v1``.
    """
    validate_tactical_packet(packet)
    origin = packet["georeference"]["origin"]
    enriched = dict(packet)
    enriched["bridge_schema"] = BRIDGE_SCHEMA
    tracks = packet["tracks"]
    enriched["tracks"] = {
        "intruder": _enrich_track(tracks["intruder"], origin),
        "interceptor": _enrich_track(tracks.get("interceptor"), origin),
    }
    predicted = packet.get("predicted_intercept_enu_m")
    if isinstance(predicted, list) and len(predicted) == 3:
        latitude, longitude, altitude = geodetic_from_enu(origin, *predicted)
        enriched["predicted_intercept_geodetic"] = {
            "latitude": latitude,
            "longitude": longitude,
            "altitude_m": altitude,
        }
    return enriched


def encode_bridge_packet(enriched: dict) -> bytes:
    payload = json.dumps(
        enriched,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    if len(payload) > MAX_UDP_PAYLOAD:
        raise ValueError(
            f"enriched packet exceeds UDP payload limit: {len(payload)} bytes"
        )
    return payload


@dataclass
class BridgeStats:
    received: int = 0
    forwarded: int = 0
    dropped_upstream: int = 0
    rejected: int = 0

    def as_dict(self) -> dict:
        return {
            "received": self.received,
            "forwarded": self.forwarded,
            "dropped_upstream": self.dropped_upstream,
            "rejected": self.rejected,
        }


class UnrealTelemetryBridge:
    """Receive tactical UDP, enrich to geodetic, and forward to Unreal."""

    def __init__(self, listen: UdpEndpoint, unreal: UdpEndpoint):
        self.listen = listen
        self.unreal = unreal
        self.stats = BridgeStats()
        self._tracker = TacticalSequenceTracker()
        self._rx: socket.socket | None = None
        self._tx: socket.socket | None = None

    def bind(self) -> None:
        """Open the receive and transmit sockets (call before serving)."""
        self._rx = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._rx.bind((self.listen.host, self.listen.port))
        self._tx = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    def process_datagram(self, data: bytes) -> dict | None:
        """Validate + enrich one datagram. Returns None if it is rejected.

        Rejection covers malformed JSON, schema violations, and stale or
        out-of-order sequences (expected on a lossy UDP transport); the bridge
        counts these and keeps running rather than raising.
        """
        self.stats.received += 1
        try:
            packet = json.loads(data.decode("utf-8"))
            dropped = self._tracker.accept(packet)
        except (ValueError, UnicodeDecodeError):
            self.stats.rejected += 1
            return None
        self.stats.dropped_upstream += dropped
        return enrich_packet(packet)

    def forward(self, enriched: dict) -> None:
        if self._tx is None:
            raise RuntimeError("bridge is not bound; call bind() first")
        self._tx.sendto(
            encode_bridge_packet(enriched),
            (self.unreal.host, self.unreal.port),
        )
        self.stats.forwarded += 1

    def serve_forever(self, *, stats_interval: int = 0, echo: bool = False) -> None:
        if self._rx is None:
            self.bind()
        assert self._rx is not None
        print(
            f"[unreal-bridge] listening on {self.listen.host}:{self.listen.port}"
            f" -> forwarding to {self.unreal.host}:{self.unreal.port}"
        )
        try:
            while True:
                data, _sender = self._rx.recvfrom(MAX_UDP_PAYLOAD)
                enriched = self.process_datagram(data)
                if enriched is None:
                    continue
                self.forward(enriched)
                if echo:
                    intruder = enriched["tracks"]["intruder"]["geodetic"]
                    print(
                        f"[unreal-bridge] seq={enriched['sequence']} "
                        f"intruder=({intruder['latitude']:.6f}, "
                        f"{intruder['longitude']:.6f}, {intruder['altitude_m']:.1f})"
                    )
                if stats_interval and self.stats.forwarded % stats_interval == 0:
                    print(f"[unreal-bridge] stats {self.stats.as_dict()}")
        except KeyboardInterrupt:
            print(f"[unreal-bridge] stopping; stats {self.stats.as_dict()}")
        finally:
            self.close()

    def close(self) -> None:
        if self._rx is not None:
            self._rx.close()
            self._rx = None
        if self._tx is not None:
            self._tx.close()
            self._tx = None


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--listen",
        default="127.0.0.1:8787",
        help="HOST:PORT to receive tactical packets on (match --telemetry-udp)",
    )
    parser.add_argument(
        "--unreal",
        default="127.0.0.1:8788",
        help="HOST:PORT of the Unreal/Cesium client to forward enriched packets to",
    )
    parser.add_argument(
        "--stats-interval",
        type=int,
        default=0,
        help="Print bridge stats every N forwarded packets (0 disables)",
    )
    parser.add_argument(
        "--echo",
        action="store_true",
        help="Print a per-packet geodetic summary of the intruder track",
    )
    args = parser.parse_args(argv)
    try:
        listen = UdpEndpoint.parse(args.listen)
        unreal = UdpEndpoint.parse(args.unreal)
    except ValueError as exc:
        parser.error(str(exc))
    bridge = UnrealTelemetryBridge(listen, unreal)
    bridge.serve_forever(stats_interval=args.stats_interval, echo=args.echo)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
