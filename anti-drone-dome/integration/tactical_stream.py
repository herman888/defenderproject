"""Versioned UDP telemetry stream for Unreal, Cesium, ROS, or custom clients."""

from __future__ import annotations

import json
import socket
from dataclasses import dataclass


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

    def __init__(self, endpoint: UdpEndpoint):
        self.endpoint = endpoint
        self._sequence = 0
        self._socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    @classmethod
    def from_endpoint(cls, value: str) -> "TacticalUdpPublisher":
        return cls(UdpEndpoint.parse(value))

    def publish(self, state: dict) -> None:
        packet = {
            "schema": "aegis.tactical.v1",
            "sequence": self._sequence,
            **state,
        }
        payload = json.dumps(
            packet,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
        self._socket.sendto(payload, (self.endpoint.host, self.endpoint.port))
        self._sequence += 1

    def close(self) -> None:
        self._socket.close()
