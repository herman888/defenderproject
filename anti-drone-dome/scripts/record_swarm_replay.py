"""Record a deterministic swarm-coordination run for the Unreal display adapter.

The recording preserves the native ``aegis.swarm-coordination.v1`` packets.
It is a coordination-simulation visualisation, not a multi-target sensor
validation or a claim of real-world swarm effectiveness.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from swarm.runner import run_scenario  # noqa: E402
from swarm.scenario import get_swarm_scenario  # noqa: E402
from swarm.telemetry import SCHEMA, validate_swarm_packet  # noqa: E402


class _JsonlRecorder:
    def __init__(self, output: Path) -> None:
        self._output = output
        self._sequence = 0
        self._handle = output.open("w", encoding="utf-8")

    def publish(self, body: dict) -> dict:
        packet = {"schema": SCHEMA, "sequence": self._sequence, **body}
        validate_swarm_packet(packet)
        self._handle.write(json.dumps(packet, separators=(",", ":"), allow_nan=False))
        self._handle.write("\n")
        self._sequence += 1
        return packet

    def close(self) -> None:
        self._handle.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scenario", default="saturation_6v4")
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument("--output", required=True, help="Output JSONL path")
    args = parser.parse_args()

    output = Path(args.output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    recorder = _JsonlRecorder(output)
    try:
        scenario = get_swarm_scenario(args.scenario)
        result = run_scenario(scenario, seed=args.seed, telemetry=recorder)
    finally:
        recorder.close()
    print(
        f"Recorded {recorder._sequence} native swarm packets to {output} "
        f"({result.scenario_id}; simulation visualisation only)."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
