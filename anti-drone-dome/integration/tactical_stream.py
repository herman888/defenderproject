"""Validated tactical telemetry for Unreal, Cesium, ROS, or custom clients."""

from __future__ import annotations

import json
import math
import os
import socket
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator


SCHEMA = "aegis.tactical.v1"
MAX_UDP_PAYLOAD = 65_507


def _require_number(value, label: str, *, minimum: float | None = None) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be a finite number")
    value = float(value)
    if not math.isfinite(value):
        raise ValueError(f"{label} must be a finite number")
    if minimum is not None and value < minimum:
        raise ValueError(f"{label} must be at least {minimum}")
    return value


def _require_vector(value, label: str, length: int) -> None:
    if not isinstance(value, list) or len(value) != length:
        raise ValueError(f"{label} must contain {length} numbers")
    for index, component in enumerate(value):
        _require_number(component, f"{label}[{index}]")


def _validate_track(track: dict | None, label: str) -> None:
    if track is None:
        return
    if not isinstance(track, dict):
        raise ValueError(f"{label} must be an object or null")
    for key in ("id", "role", "asset_id", "type"):
        if not isinstance(track.get(key), str) or not track[key]:
            raise ValueError(f"{label}.{key} must be a non-empty string")
    _require_vector(track.get("position_enu_m"), f"{label}.position_enu_m", 3)
    _require_vector(track.get("velocity_enu_mps"), f"{label}.velocity_enu_mps", 3)
    orientation = track.get("orientation_xyzw")
    _require_vector(orientation, f"{label}.orientation_xyzw", 4)
    magnitude = math.sqrt(sum(float(component) ** 2 for component in orientation))
    if magnitude < 1e-6:
        raise ValueError(f"{label}.orientation_xyzw cannot be a zero quaternion")


def validate_tactical_packet(packet: dict) -> None:
    """Validate fields required by external presentation clients."""
    if not isinstance(packet, dict):
        raise ValueError("tactical packet must be an object")
    if packet.get("schema") != SCHEMA:
        raise ValueError(f"tactical packet schema must be {SCHEMA}")
    sequence = packet.get("sequence")
    if not isinstance(sequence, int) or isinstance(sequence, bool) or sequence < 0:
        raise ValueError("sequence must be a non-negative integer")
    _require_number(packet.get("mission_time_s"), "mission_time_s", minimum=0.0)
    if packet.get("timestamp_clock") != "simulation-relative":
        raise ValueError("timestamp_clock must be simulation-relative")
    for key in ("status", "site", "guidance"):
        if not isinstance(packet.get(key), str) or not packet[key]:
            raise ValueError(f"{key} must be a non-empty string")

    frame = packet.get("coordinate_frame")
    expected_frame = {
        "type": "local-tangent-plane",
        "axes": "ENU",
        "position_unit": "m",
        "velocity_unit": "m/s",
        "orientation": "xyzw",
    }
    if frame != expected_frame:
        raise ValueError("coordinate_frame must declare local ENU metres and xyzw")

    georeference = packet.get("georeference")
    if not isinstance(georeference, dict):
        raise ValueError("georeference must be an object")
    origin = georeference.get("origin")
    if not isinstance(origin, dict):
        raise ValueError("georeference.origin must be an object")
    latitude = _require_number(origin.get("latitude"), "origin.latitude")
    longitude = _require_number(origin.get("longitude"), "origin.longitude")
    _require_number(origin.get("altitude_m"), "origin.altitude_m")
    if not -90.0 <= latitude <= 90.0:
        raise ValueError("origin.latitude must be in [-90, 90]")
    if not -180.0 <= longitude <= 180.0:
        raise ValueError("origin.longitude must be in [-180, 180]")
    if georeference.get("status") not in {"placeholder", "approved"}:
        raise ValueError("georeference.status must be placeholder or approved")

    terrain = packet.get("terrain")
    if not isinstance(terrain, dict):
        raise ValueError("terrain must be an object")
    if not isinstance(terrain.get("source"), str) or not terrain["source"]:
        raise ValueError("terrain.source must be a non-empty string")
    if terrain.get("collision_authoritative") is not True:
        raise ValueError("terrain.collision_authoritative must be true")

    tracks = packet.get("tracks")
    if not isinstance(tracks, dict):
        raise ValueError("tracks must be an object")
    if "intruder" not in tracks or "interceptor" not in tracks:
        raise ValueError("tracks must contain intruder and interceptor")
    _validate_track(tracks["intruder"], "tracks.intruder")
    _validate_track(tracks["interceptor"], "tracks.interceptor")
    if tracks["intruder"] is None:
        raise ValueError("tracks.intruder cannot be null")


def encode_tactical_packet(packet: dict) -> bytes:
    validate_tactical_packet(packet)
    payload = json.dumps(
        packet,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    if len(payload) > MAX_UDP_PAYLOAD:
        raise ValueError(
            f"tactical packet exceeds UDP payload limit: {len(payload)} bytes"
        )
    return payload


def _open_unique_recording(path: Path):
    for index in range(10_000):
        candidate = (
            path
            if index == 0
            else path.with_name(f"{path.stem}.{index:03d}{path.suffix}")
        )
        try:
            return candidate, candidate.open("xb")
        except FileExistsError:
            continue
    raise FileExistsError(f"no unused tactical recording path available for {path}")


class TacticalSequenceTracker:
    """Reject duplicate/out-of-order packets and report sequence gaps."""

    def __init__(self):
        self.last_sequence: int | None = None
        self.last_mission_time_s: float | None = None

    def accept(self, packet: dict) -> int:
        validate_tactical_packet(packet)
        sequence = packet["sequence"]
        mission_time_s = float(packet["mission_time_s"])
        if self.last_sequence is not None and sequence <= self.last_sequence:
            raise ValueError(
                f"stale tactical sequence {sequence}; last was {self.last_sequence}"
            )
        if (
            self.last_mission_time_s is not None
            and mission_time_s < self.last_mission_time_s
        ):
            raise ValueError("mission_time_s moved backwards")
        dropped = (
            max(0, sequence - self.last_sequence - 1)
            if self.last_sequence is not None else 0
        )
        self.last_sequence = sequence
        self.last_mission_time_s = mission_time_s
        return dropped


@dataclass(frozen=True)
class UdpEndpoint:
    host: str
    port: int

    @classmethod
    def parse(cls, value: str) -> "UdpEndpoint":
        host, separator, port_text = value.rpartition(":")
        if not separator or not host:
            raise ValueError("UDP endpoint must use HOST:PORT format")
        port = int(port_text)
        if not 1 <= port <= 65535:
            raise ValueError("UDP port must be between 1 and 65535")
        return cls(host, port)


class TacticalUdpPublisher:
    """Publishes compact, engine-agnostic mission snapshots over UDP."""

    def __init__(
        self,
        endpoint: UdpEndpoint,
        *,
        recording_path: str | os.PathLike | None = None,
    ):
        self.endpoint = endpoint
        self._sequence = 0
        self._recording = None
        self.recording_path: Path | None = None
        if recording_path is not None:
            path = Path(recording_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            self.recording_path, self._recording = _open_unique_recording(path)
        try:
            self._socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        except OSError:
            if self._recording is not None:
                self._recording.close()
                self._recording = None
            raise

    @classmethod
    def from_endpoint(
        cls,
        value: str,
        *,
        recording_path: str | os.PathLike | None = None,
    ) -> "TacticalUdpPublisher":
        return cls(UdpEndpoint.parse(value), recording_path=recording_path)

    def publish(self, state: dict) -> dict:
        packet = {
            "schema": SCHEMA,
            "sequence": self._sequence,
            **state,
        }
        payload = encode_tactical_packet(packet)
        self._socket.sendto(payload, (self.endpoint.host, self.endpoint.port))
        if self._recording is not None:
            self._recording.write(payload + b"\n")
            self._recording.flush()
        self._sequence += 1
        return packet

    def close(self) -> None:
        self._socket.close()
        if self._recording is not None:
            self._recording.close()
            self._recording = None


def iter_tactical_recording(path: str | os.PathLike) -> Iterator[dict]:
    """Yield validated, strictly ordered packets from JSONL."""
    tracker = TacticalSequenceTracker()
    with Path(path).open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                packet = json.loads(line)
                tracker.accept(packet)
            except (json.JSONDecodeError, ValueError) as exc:
                raise ValueError(
                    f"invalid tactical recording at line {line_number}: {exc}"
                ) from exc
            yield packet


def replay_tactical_recording(
    path: str | os.PathLike,
    endpoint: UdpEndpoint,
    *,
    rate: float = 1.0,
    wait: bool = True,
) -> int:
    """Replay exact recorded packets while preserving sequence and mission time."""
    rate = _require_number(rate, "rate", minimum=1e-9)
    packets = iter_tactical_recording(path)
    sent = 0
    previous_time: float | None = None
    udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        for packet in packets:
            mission_time = float(packet["mission_time_s"])
            if wait and previous_time is not None:
                time.sleep(max(0.0, mission_time - previous_time) / rate)
            udp_socket.sendto(
                encode_tactical_packet(packet),
                (endpoint.host, endpoint.port),
            )
            previous_time = mission_time
            sent += 1
    finally:
        udp_socket.close()
    if sent == 0:
        raise ValueError("tactical recording contains no packets")
    return sent
