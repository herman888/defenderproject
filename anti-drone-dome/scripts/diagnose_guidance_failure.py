"""Diagnose why the interceptor fails to converge on hard campaign scenarios.

The 800-episode campaign at a 1.0 m contact radius shows three scenarios
(`spiral-noisy`, `crosswind-crossing`, `compound-edge`) failing at 9-33% with a
p95 duration pinned to the 120 s ceiling and **timeout**, not breach, as the
dominant outcome. That pattern says the interceptor never converges on the
collision triangle at all - which is a guidance question, not a terminal
accuracy question.

This script runs single seeded episodes and dumps the APN internals per step so
the failure can be attributed rather than guessed at:

    venv312\\Scripts\\python.exe scripts\\diagnose_guidance_failure.py
    venv312\\Scripts\\python.exe scripts\\diagnose_guidance_failure.py --case crosswind-crossing --seeds 5 --trace

Reported per episode: outcome, closing speed statistics, LOS-rate statistics,
commanded versus achieved speed, action saturation, and the fraction of the
episode spent with non-positive closing speed - the single most diagnostic
number, since APN has no solution while the range is opening.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from pathlib import Path

import numpy as np

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from ml.controllers import APNController  # noqa: E402
from ml.environment import InterceptionEnv  # noqa: E402
from ml.stress_scenarios import load_campaign  # noqa: E402

CAMPAIGN = "scenario_data/regression_campaign_v1.json"


def _percentile(values, q):
    if not values:
        return float("nan")
    return float(np.percentile(np.asarray(values, dtype=float), q))


def diagnose(case, seed: int, trace: bool = False) -> dict:
    env = InterceptionEnv(
        pattern=case.scenario.profile,
        intruder_type=case.scenario.intruder_type,
        domain_randomization=True,
        residual_apn=False,
        observation_version="v2",
        procedural_scenarios=False,
        curriculum_level=1.0,
        fixed_scenario=case.scenario,
    )
    controller = APNController()
    observation, info = env.reset(seed=seed)

    closing = []
    los_rate = []
    ranges = []
    cmd_speed = []
    own_speed = []
    saturation = []
    modes = {}
    confidences = []
    steps = 0
    terminated = truncated = False

    while not (terminated or truncated):
        action = controller.predict(observation, env)
        observation, _reward, terminated, truncated, info = env.step(action)
        steps += 1

        # Read the controller's own guidance object, not env._apn. The env
        # keeps an internal PurePursuitGuidance for the residual-APN path, but
        # when a controller supplies the action that instance is never invoked
        # and reports WAITING for every step.
        diag = controller.guidance.last_diagnostics
        closing.append(float(diag.get("closing_speed_mps", 0.0)))
        los_rate.append(abs(float(diag.get("los_rate_dps", 0.0))))
        cmd_speed.append(float(diag.get("command_speed_mps", 0.0)))
        modes[diag.get("mode", "?")] = modes.get(diag.get("mode", "?"), 0) + 1
        ranges.append(float(info["separation_m"]))
        confidences.append(float(info.get("track_confidence", 0.0)))
        own_speed.append(float(np.linalg.norm(np.asarray(action, dtype=float))))
        saturation.append(min(1.0, float(np.max(np.abs(action)))))

        if trace and steps % 40 == 0:
            print(
                f"    t={steps * env.dt:6.1f}s  R={ranges[-1]:8.1f}m"
                f"  Vc={closing[-1]:+7.1f}  LOSrate={los_rate[-1]:6.2f}deg/s"
                f"  cmd={cmd_speed[-1]:5.1f}  sat={saturation[-1]:.2f}"
                f"  {diag.get('mode')}"
            )

    opening = sum(1 for c in closing if c <= 0.0)
    return {
        "seed": seed,
        "outcome": (
            "intercepted" if info.get("intercepted")
            else "breach" if info.get("breached")
            else "timeout"
        ),
        "steps": steps,
        "duration_s": steps * env.dt,
        "min_separation_m": round(min(ranges), 2),
        "final_separation_m": round(ranges[-1], 2),
        "opening_fraction": round(opening / max(steps, 1), 3),
        "closing_median": round(statistics.median(closing), 2),
        "closing_p10": round(_percentile(closing, 10), 2),
        "los_rate_median_dps": round(statistics.median(los_rate), 3),
        "los_rate_p90_dps": round(_percentile(los_rate, 90), 3),
        "cmd_speed_median": round(statistics.median(cmd_speed), 2),
        "saturation_mean": round(sum(saturation) / max(len(saturation), 1), 3),
        "confidence_mean": round(sum(confidences) / max(len(confidences), 1), 3),
        "modes": modes,
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--case", nargs="+",
        default=["baseline-direct", "crosswind-crossing", "compound-edge"],
        help="Scenario ids from the campaign file.",
    )
    parser.add_argument("--seeds", type=int, default=3)
    parser.add_argument("--seed-start", type=int, default=1000)
    parser.add_argument("--trace", action="store_true")
    args = parser.parse_args(argv)

    campaign = load_campaign(CAMPAIGN)
    by_id = {c.case_id: c for c in campaign["cases"]}

    summary = {}
    for case_id in args.case:
        case = by_id.get(case_id)
        if case is None:
            print(f"unknown case: {case_id}")
            continue
        print(f"\n=== {case_id} ===")
        rows = []
        for index in range(args.seeds):
            row = diagnose(case, args.seed_start + index, trace=args.trace)
            rows.append(row)
            print(
                f"  seed {row['seed']}  {row['outcome']:<12}"
                f" dur {row['duration_s']:6.1f}s"
                f" minR {row['min_separation_m']:8.1f}m"
                f" opening {row['opening_fraction']:.2f}"
                f" Vc_med {row['closing_median']:+7.1f}"
                f" LOS_med {row['los_rate_median_dps']:6.2f}"
                f" sat {row['saturation_mean']:.2f}"
                f" conf {row['confidence_mean']:.2f}"
            )
        summary[case_id] = rows
        opening = sum(r["opening_fraction"] for r in rows) / len(rows)
        sat = sum(r["saturation_mean"] for r in rows) / len(rows)
        print(f"  -> mean opening fraction {opening:.2f}, mean saturation {sat:.2f}")

    print("\n" + json.dumps({k: v[0]["modes"] for k, v in summary.items()}, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
