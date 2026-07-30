"""Loopback-only controls for the software-in-loop demonstration.

This protocol deliberately accepts only local UDP and only changes the Python
simulation's presentation/runtime state. It has no hardware, MAVLink, or
actuation path.
"""

from __future__ import annotations

import json
import socket
from dataclasses import dataclass


SCHEMA = "aegis.local-sim-control.v1"
ALLOWED_SPEEDS = frozenset({1.0, 2.0, 4.0, 8.0})
ALLOWED_FAILURES = frozenset({"radar", "eo", "actuator"})
MAX_DATAGRAM_BYTES = 4096
_LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost"})


def validate_command(packet: object) -> dict:
    """Return a normalized, safe local simulation command or raise ValueError."""
    if not isinstance(packet, dict) or packet.get("schema") != SCHEMA:
        raise ValueError("unsupported local simulation command")
    action = packet.get("action")
    if action in {"pause_toggle", "restart", "next_preset", "clear_failures"}:
        return {"action": action}
    if action == "toggle_failure":
        failure = packet.get("failure")
        if failure not in ALLOWED_FAILURES:
            raise ValueError("failure is not an allowed training injection")
        return {"action": action, "failure": failure}
    if action == "set_speed":
        speed = packet.get("speed")
        if isinstance(speed, bool) or not isinstance(speed, (int, float)):
            raise ValueError("speed must be numeric")
        speed = float(speed)
        if speed not in ALLOWED_SPEEDS:
            raise ValueError("speed is not an allowed presentation rate")
        return {"action": action, "speed": speed}
    raise ValueError("unsupported local simulation action")


@dataclass
class LocalSimulationControlReceiver:
    """Non-blocking loopback UDP receiver for the packaged training viewer."""

    host: str
    port: int
    socket_handle: socket.socket | None = None

    def __post_init__(self) -> None:
        if self.host not in _LOOPBACK_HOSTS:
            raise ValueError("simulation controls must bind to loopback only")
        if not isinstance(self.port, int) or not 1 <= self.port <= 65535:
            raise ValueError("simulation control port must be in [1, 65535]")

    def bind(self) -> None:
        handle = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        handle.bind(("127.0.0.1", self.port))
        handle.setblocking(False)
        self.socket_handle = handle

    def drain(self, limit: int = 32) -> list[dict]:
        if self.socket_handle is None:
            return []
        commands: list[dict] = []
        for _ in range(limit):
            try:
                payload, address = self.socket_handle.recvfrom(MAX_DATAGRAM_BYTES + 1)
            except BlockingIOError:
                break
            if address[0] != "127.0.0.1" or len(payload) > MAX_DATAGRAM_BYTES:
                continue
            try:
                commands.append(validate_command(json.loads(payload.decode("utf-8"))))
            except (UnicodeDecodeError, json.JSONDecodeError, ValueError):
                continue
        return commands

    def close(self) -> None:
        if self.socket_handle is not None:
            self.socket_handle.close()
            self.socket_handle = None
