"""Replay a recorded ``aegis.swarm-coordination.v1`` JSONL stream over UDP."""

from __future__ import annotations

import argparse
import json
import os
import socket
import sys
import time
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from integration.tactical_stream import UdpEndpoint  # noqa: E402
from swarm.telemetry import validate_swarm_packet  # noqa: E402


def _load(path: Path) -> list[dict]:
    packets: list[dict] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            packet = json.loads(line)
            validate_swarm_packet(packet)
        except (json.JSONDecodeError, ValueError) as exc:
            raise ValueError(f"invalid swarm recording at line {line_number}: {exc}") from exc
        packets.append(packet)
    if not packets:
        raise ValueError("swarm recording contains no packets")
    return packets


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True)
    parser.add_argument("--udp", default="127.0.0.1:8787")
    parser.add_argument("--rate", type=float, default=0.5)
    parser.add_argument("--loop", type=int, default=0, metavar="N")
    parser.add_argument("--loop-gap", type=float, default=2.0)
    args = parser.parse_args()
    if args.rate <= 0.0 or args.loop < 0:
        parser.error("--rate must be positive and --loop must be zero or positive")

    try:
        packets = _load(Path(args.input))
        endpoint = UdpEndpoint.parse(args.udp)
    except (OSError, ValueError) as exc:
        parser.error(str(exc))

    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as udp:
        pass_count = 0
        while args.loop == 0 or pass_count < args.loop:
            previous_time = float(packets[0]["mission_time_s"])
            for packet in packets:
                mission_time = float(packet["mission_time_s"])
                time.sleep(max(0.0, mission_time - previous_time) / args.rate)
                udp.sendto(
                    json.dumps(packet, separators=(",", ":"), allow_nan=False).encode("utf-8"),
                    (endpoint.host, endpoint.port),
                )
                previous_time = mission_time
            pass_count += 1
            if args.loop == 0 or pass_count < args.loop:
                time.sleep(max(0.0, args.loop_gap))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
