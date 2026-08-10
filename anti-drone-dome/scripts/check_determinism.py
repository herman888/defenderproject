"""Verify a sensor-in-loop swarm scenario is reproducible from its seed.

The check hashes the complete result twice in one fresh process.  It is a
release guard for accidental use of wall-clock time, global RNG state, or
unordered identifiers in the simulation path; it does not claim that the
synthetic model is calibrated to field hardware.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from swarm.runner import run_scenario
from swarm.scenario import get_swarm_scenario


def _digest(value: dict) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def check_scenario(scenario_id: str, seed: int | None = None) -> dict:
    scenario = get_swarm_scenario(scenario_id)
    effective_seed = scenario.seed if seed is None else int(seed)
    first = run_scenario(scenario, seed=effective_seed).to_dict()
    second = run_scenario(scenario, seed=effective_seed).to_dict()
    first_hash, second_hash = _digest(first), _digest(second)
    report = {
        "schema": "aegis.determinism-check.v1",
        "scenario_id": scenario_id,
        "seed": effective_seed,
        "first_sha256": first_hash,
        "second_sha256": second_hash,
        "deterministic": first_hash == second_hash,
    }
    if not report["deterministic"]:
        raise RuntimeError(
            "same seeded scenario produced different result hashes: "
            f"{first_hash} != {second_hash}"
        )
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scenario", default="saturation_6v4")
    parser.add_argument("--seed", type=int)
    parser.add_argument("--output", help="Optional JSON report path")
    args = parser.parse_args()
    report = check_scenario(args.scenario, args.seed)
    if args.output:
        output = os.path.abspath(args.output)
        os.makedirs(os.path.dirname(output), exist_ok=True)
        with open(output, "w", encoding="utf-8") as handle:
            json.dump(report, handle, indent=2)
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
