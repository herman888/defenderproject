"""Measure the per-subsystem performance baseline of the simulator.

This is the "before" artifact for the Workstream A refactor described in
``docs-internal/PROGRAM_PLAN.md``. It microbenchmarks the four call sites that
profiling identified as the scaling blockers, plus the NumPy primitives that
explain *why* they are slow, and writes a machine-readable report.

Run it before and after each refactor stage so every performance claim has a
documented baseline on the same host:

    venv312\\Scripts\\python.exe scripts\\measure_perf_baseline.py
    venv312\\Scripts\\python.exe scripts\\measure_perf_baseline.py --output reports/perf/after_a1.json

Numbers are host-relative. ``host_normalization_us`` records a fixed NumPy
microbenchmark so results from different machines can be scaled for comparison.
"""

from __future__ import annotations

import argparse
import json
import platform
import sys
import timeit
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

SCHEMA = "aegis.perf-baseline.v1"


def _time_us(stmt, number: int) -> float:
    """Return microseconds per call, taking the best of 5 repeats."""
    best = min(timeit.repeat(stmt, repeat=5, number=number))
    return (best / number) * 1e6


def _numpy_primitives() -> dict:
    """The interpreter-overhead costs that explain the subsystem numbers."""
    a3 = np.array([1.0, 2.0, 3.0])
    b3 = np.array([4.0, 5.0, 6.0])
    a1k = np.random.default_rng(0).random((1000, 3))
    b1k = np.random.default_rng(1).random((1000, 3))
    import math

    return {
        "np_clip_scalar": _time_us(lambda: float(np.clip(0.7, 0.0, 1.0)), 20000),
        "python_clamp_scalar": _time_us(lambda: min(1.0, max(0.0, 0.7)), 200000),
        "np_cross_3vec": _time_us(lambda: np.cross(a3, b3), 20000),
        "np_cross_1000x3": _time_us(lambda: np.cross(a1k, b1k), 2000),
        "np_norm_3vec": _time_us(lambda: float(np.linalg.norm(a3)), 20000),
        "math_norm_3vec": _time_us(lambda: math.sqrt(1.0 + 4.0 + 9.0), 200000),
        "np_norm_1000rows": _time_us(
            lambda: np.linalg.norm(a1k - b1k, axis=1), 2000
        ),
    }


def _guidance() -> dict:
    from guidance.intercept import PurePursuitGuidance

    guidance = PurePursuitGuidance()
    interceptor = {
        "position": (0.0, 0.0, 50.0),
        "velocity": (30.0, 0.0, 5.0),
        "energy_remaining_fraction": 0.8,
    }
    track = {
        "detected": True,
        "position_estimate": (400.0, 120.0, 90.0),
        "velocity": (-40.0, -10.0, -2.0),
        "acceleration": (0.5, 0.2, 0.0),
        "track_confidence": 0.9,
    }
    return {
        "compute_guidance": _time_us(
            lambda: guidance.compute_guidance(interceptor, track), 2000
        ),
        "time_to_intercept": _time_us(
            lambda: guidance.time_to_intercept(interceptor, track), 5000
        ),
    }


def _kalman() -> dict:
    from sensors.radar import KalmanTracker

    rng = np.random.default_rng(7)
    tracker = KalmanTracker(np.array([100.0, 50.0, 80.0]), meas_std=3.0)
    meas = np.array([101.0, 50.5, 80.2])
    coast = KalmanTracker(np.array([100.0, 50.0, 80.0]), meas_std=3.0)
    del rng
    return {
        "kalman_step_update": _time_us(lambda: tracker.step(meas), 5000),
        "kalman_step_coast": _time_us(lambda: coast.step(None), 20000),
    }


def _assignment(n_interceptors: int, n_threats: int) -> dict:
    from guidance.intercept import PurePursuitGuidance
    from swarm.assignment import (
        build_cost_matrix,
        greedy_priority_assignment,
        hungarian_assignment,
        threat_priority,
    )

    rng = np.random.default_rng(11)
    guidance = PurePursuitGuidance()
    interceptors = [
        {
            "position": tuple(rng.uniform(-200, 200, 3) + (0, 0, 120)),
            "velocity": tuple(rng.uniform(-30, 30, 3)),
            "energy_remaining_fraction": 0.9,
        }
        for _ in range(n_interceptors)
    ]
    threats = [
        {
            "position_estimate": tuple(rng.uniform(-2000, 2000, 3) + (0, 0, 300)),
            "velocity": tuple(rng.uniform(-50, 50, 3)),
            "threat_level": "high",
        }
        for _ in range(n_threats)
    ]

    cost = build_cost_matrix(interceptors, threats, guidance)
    priorities = np.array([threat_priority(t) for t in threats], dtype=float)

    return {
        "shape": [n_interceptors, n_threats],
        "build_cost_matrix": _time_us(
            lambda: build_cost_matrix(interceptors, threats, guidance), 3
        ),
        "hungarian_assignment": _time_us(lambda: hungarian_assignment(cost), 3),
        "greedy_priority_assignment": _time_us(
            lambda: greedy_priority_assignment(cost, priorities), 20
        ),
        "threat_priority_per_call": _time_us(
            lambda: threat_priority(threats[0]), 20000
        ),
    }


def _scenarios() -> dict:
    """End-to-end headless real-time factor for each swarm scenario.

    Measured without a profiler attached — cProfile inflates these by 3-5x on
    microsecond-scale NumPy calls, so a profiled RTF is not a baseline.
    """
    import time

    from swarm.runner import run_scenario
    from swarm.scenario import get_swarm_scenario, load_swarm_catalog

    results = {}
    for name in load_swarm_catalog():
        scenario = get_swarm_scenario(name)
        start = time.perf_counter()
        run = run_scenario(scenario, seed=1)
        wall_s = time.perf_counter() - start
        sim_s = float(run.sim_time_s)
        results[name] = {
            "threats": len(scenario.threats),
            "interceptors": len(scenario.interceptors),
            "wall_s": wall_s,
            "sim_s": sim_s,
            "real_time_factor": (sim_s / wall_s) if wall_s > 0 else None,
        }
    return results


def _pybullet(n_bodies: int) -> dict | None:
    try:
        import pybullet
        import pybullet_data
    except ImportError:
        return None

    cid = pybullet.connect(pybullet.DIRECT)
    try:
        pybullet.setAdditionalSearchPath(pybullet_data.getDataPath())
        pybullet.setGravity(0, 0, -9.81, physicsClientId=cid)
        col = pybullet.createCollisionShape(pybullet.GEOM_SPHERE, radius=0.2)
        bodies = [
            pybullet.createMultiBody(
                baseMass=1.0,
                baseCollisionShapeIndex=col,
                basePosition=[i * 2.0, 0, 50.0 + i],
            )
            for i in range(n_bodies)
        ]

        step_us = _time_us(lambda: pybullet.stepSimulation(physicsClientId=cid), 200)

        def _api_roundtrips():
            for b in bodies:
                pybullet.getBasePositionAndOrientation(b, physicsClientId=cid)
                pybullet.getBaseVelocity(b, physicsClientId=cid)

        api_us = _time_us(_api_roundtrips, 100)
        return {
            "bodies": n_bodies,
            "step_simulation": step_us,
            "api_2calls_per_body_total": api_us,
            "per_api_roundtrip": api_us / (n_bodies * 2),
        }
    finally:
        pybullet.disconnect(physicsClientId=cid)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        default="reports/perf/baseline_pre_refactor.json",
        help="Where to write the report, relative to the project root.",
    )
    parser.add_argument("--interceptors", type=int, default=20)
    parser.add_argument("--threats", type=int, default=50)
    parser.add_argument("--pybullet-bodies", type=int, default=70)
    parser.add_argument(
        "--label",
        default="pre-refactor",
        help="Stage label recorded in the report (e.g. 'after-a1').",
    )
    args = parser.parse_args(argv)

    print("Measuring NumPy primitives...")
    primitives = _numpy_primitives()
    print("Measuring guidance...")
    guidance = _guidance()
    print("Measuring Kalman tracker...")
    kalman = _kalman()
    print(f"Measuring assignment at {args.interceptors}x{args.threats}...")
    assignment = _assignment(args.interceptors, args.threats)
    print(f"Measuring PyBullet at {args.pybullet_bodies} bodies...")
    pybullet_result = _pybullet(args.pybullet_bodies)
    print("Measuring end-to-end scenario real-time factor...")
    scenarios = _scenarios()

    report = {
        "schema": SCHEMA,
        "label": args.label,
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "host": {
            "platform": platform.platform(),
            "processor": platform.processor(),
            "python": sys.version.split()[0],
            "numpy": np.__version__,
        },
        "host_normalization_us": primitives["np_norm_1000rows"],
        "units": "microseconds per call unless noted",
        "numpy_primitives_us": primitives,
        "guidance_us": guidance,
        "kalman_us": kalman,
        "assignment_us": assignment,
        "pybullet_us": pybullet_result,
        "scenarios": scenarios,
    }

    out = _ROOT / args.output
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print(f"\nWrote {out}\n")
    print(f"  compute_guidance          {guidance['compute_guidance']:10.1f} us")
    print(f"  time_to_intercept         {guidance['time_to_intercept']:10.1f} us")
    print(f"  kalman step (update)      {kalman['kalman_step_update']:10.1f} us")
    print(
        f"  build_cost_matrix {args.interceptors}x{args.threats}"
        f"   {assignment['build_cost_matrix'] / 1000:9.1f} ms"
    )
    print(
        f"  hungarian {args.interceptors}x{args.threats}"
        f"           {assignment['hungarian_assignment'] / 1000:9.1f} ms"
    )
    if pybullet_result:
        print(
            f"  pybullet step ({args.pybullet_bodies} bodies)"
            f"  {pybullet_result['step_simulation']:8.1f} us"
        )
        print(
            f"  pybullet api roundtrip    "
            f"{pybullet_result['per_api_roundtrip']:10.2f} us"
        )
    for name, s in scenarios.items():
        print(
            f"  {name:<18} {s['interceptors']}v{s['threats']}"
            f"  RTF {s['real_time_factor']:6.1f}x"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
