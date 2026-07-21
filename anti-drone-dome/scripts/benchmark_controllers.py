"""Benchmark APN, random, and trained PPO controllers across all scenarios."""

import argparse
import csv
import json
import math
import os
import statistics
import sys

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from ml.controllers import APNController, PPOController, RandomController
from ml.environment import InterceptionEnv
from scenarios import ATTACK_PATTERNS, INTRUDER_TYPES


def run_episode(
    controller,
    pattern,
    intruder_type,
    seed,
    residual_apn=False,
    observation_version="v1",
    procedural=False,
    fixed_scenario=None,
):
    env = InterceptionEnv(
        pattern=pattern,
        intruder_type=intruder_type,
        domain_randomization=True,
        residual_apn=residual_apn,
        observation_version=observation_version,
        procedural_scenarios=procedural,
        curriculum_level=1.0,
        fixed_scenario=fixed_scenario,
    )
    observation, info = env.reset(seed=seed)
    total_reward = 0.0
    minimum_separation = info["separation_m"]
    action_norms = []
    saturated_action_steps = 0
    acceleration_norms = []
    sensor_ages = [float(info["sensor_age_s"])]
    track_confidences = [float(info["track_confidence"])]
    terminated = truncated = False
    while not (terminated or truncated):
        action = controller.predict(observation, env)
        action_norms.append(float(np.linalg.norm(action)))
        saturated_action_steps += int(bool(np.any(np.abs(action) >= 0.999)))
        observation, reward, terminated, truncated, info = env.step(action)
        acceleration_norms.append(float(np.linalg.norm(env.applied_acceleration)))
        sensor_ages.append(float(info["sensor_age_s"]))
        track_confidences.append(float(info["track_confidence"]))
        total_reward += reward
        minimum_separation = min(minimum_separation, info["separation_m"])
    final_intruder_radius = float(np.linalg.norm(env.intruder_position[:2]))
    outcome = (
        "intercepted"
        if info["intercepted"]
        else "breach"
        if final_intruder_radius <= 2.0
        else "timeout"
    )
    return {
        "pattern": pattern,
        "intruder_type": intruder_type,
        "seed": seed,
        "intercepted": bool(info["intercepted"]),
        "outcome": outcome,
        "duration_s": env.steps * env.dt,
        "minimum_separation_m": minimum_separation,
        "energy_used": info["energy_used"],
        "battery_remaining": info["battery_fraction"],
        "reward": total_reward,
        "scenario_id": info["scenario_id"],
        "sensor_latency_s": info["configured_sensor_latency_s"],
        "sensor_dropout_probability": info["sensor_dropout_probability"],
        "radar_noise_std_m": info["radar_noise_std_m"],
        "evasion_mps": info["evasion_mps"],
        "wind_speed_mps": float(np.linalg.norm(info["wind_mps"])),
        "mass_factor": info["mass_factor"],
        "actuator_time_constant_s": info["actuator_time_constant_s"],
        "maximum_sensor_age_s": max(sensor_ages),
        "mean_track_confidence": statistics.fmean(track_confidences),
        "final_intruder_radius_m": final_intruder_radius,
        "mean_controller_action_norm": statistics.fmean(action_norms),
        "action_saturation_fraction": saturated_action_steps / len(action_norms),
        "mean_applied_acceleration_mps2": statistics.fmean(acceleration_norms),
    }


def _bootstrap_mean_ci(values, seed=0, samples=10000):
    values = np.asarray(values, dtype=float)
    if values.size == 0:
        return [float("nan"), float("nan")]
    rng = np.random.default_rng(seed)
    means = np.mean(
        rng.choice(values, size=(samples, values.size), replace=True),
        axis=1,
    )
    return [float(value) for value in np.percentile(means, [2.5, 97.5])]


def _wilson_interval(successes, episodes, z=1.959963984540054):
    if episodes <= 0:
        return [0.0, 0.0]
    proportion = successes / episodes
    denominator = 1.0 + z * z / episodes
    center = (proportion + z * z / (2.0 * episodes)) / denominator
    margin = (
        z
        * math.sqrt(
            proportion * (1.0 - proportion) / episodes
            + z * z / (4.0 * episodes * episodes)
        )
        / denominator
    )
    return [max(0.0, center - margin), min(1.0, center + margin)]


def summarize(name, episodes):
    successes = [episode for episode in episodes if episode["intercepted"]]
    durations = [episode["duration_s"] for episode in episodes]
    energy = [episode["energy_used"] for episode in episodes]
    return {
        "controller": name,
        "episodes": len(episodes),
        "intercepts": len(successes),
        "intercept_rate": len(successes) / max(len(episodes), 1),
        "intercept_rate_wilson_95": _wilson_interval(
            len(successes), len(episodes)
        ),
        "mean_minimum_separation_m": statistics.fmean(
            episode["minimum_separation_m"] for episode in episodes
        ),
        "mean_duration_s": statistics.fmean(
            durations
        ),
        "duration_s_p95": float(np.percentile(durations, 95)),
        "mean_energy_used": statistics.fmean(
            energy
        ),
        "energy_used_p95": float(np.percentile(energy, 95)),
        "mean_controller_action_norm": statistics.fmean(
            episode["mean_controller_action_norm"] for episode in episodes
        ),
        "mean_action_saturation_fraction": statistics.fmean(
            episode["action_saturation_fraction"] for episode in episodes
        ),
        "mean_applied_acceleration_mps2": statistics.fmean(
            episode["mean_applied_acceleration_mps2"] for episode in episodes
        ),
        "mean_reward": statistics.fmean(episode["reward"] for episode in episodes),
    }


def paired_comparison(reference_name, reference, candidate_name, candidate):
    def key(episode):
        return (
            episode["seed"],
            episode["scenario_id"],
            episode["pattern"],
            episode["intruder_type"],
        )

    reference_by_key = {key(episode): episode for episode in reference}
    candidate_by_key = {key(episode): episode for episode in candidate}
    common_keys = sorted(reference_by_key.keys() & candidate_by_key.keys())
    metrics = (
        "duration_s",
        "energy_used",
        "minimum_separation_m",
        "reward",
    )
    deltas = {}
    for metric in metrics:
        values = [
            candidate_by_key[item][metric] - reference_by_key[item][metric]
            for item in common_keys
        ]
        deltas[metric] = {
            "mean_candidate_minus_reference": statistics.fmean(values),
            "bootstrap_mean_95_ci": _bootstrap_mean_ci(values),
            "candidate_better_fraction": statistics.fmean(
                (
                    value < 0.0
                    if metric in ("duration_s", "energy_used", "minimum_separation_m")
                    else value > 0.0
                )
                for value in values
            ),
        }
    return {
        "reference": reference_name,
        "candidate": candidate_name,
        "paired_episodes": len(common_keys),
        "same_scenario_seed_pairing": True,
        "metric_deltas": deltas,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--episodes", type=int, default=10, help="Episodes per scenario")
    parser.add_argument("--seed", type=int, default=100)
    parser.add_argument("--model", help="PPO model to include in the comparison")
    parser.add_argument("--absolute-model", action="store_true",
                        help="Model emits absolute actions rather than APN residuals")
    parser.add_argument("--output", default="reports/controller_benchmark")
    parser.add_argument(
        "--procedural",
        action="store_true",
        help="Evaluate held-out maximum-difficulty procedural engagements",
    )
    parser.add_argument(
        "--include-random",
        action="store_true",
        help="Include a random-action sanity baseline",
    )
    args = parser.parse_args()

    controllers = {"apn": APNController()}
    if args.include_random:
        controllers["random"] = RandomController(args.seed)
    if args.model:
        controllers["ppo"] = PPOController(
            args.model, residual_apn=not args.absolute_model
        )

    all_results = {}
    summaries = []
    for controller_name, controller in controllers.items():
        episodes = []
        scenario_pairs = (
            [(None, None)]
            if args.procedural
            else [
                (pattern, intruder_type)
                for pattern in ATTACK_PATTERNS
                for intruder_type in INTRUDER_TYPES
            ]
        )
        for pattern, intruder_type in scenario_pairs:
            for episode_index in range(args.episodes):
                seed = args.seed + episode_index
                episodes.append(
                    run_episode(
                        controller,
                        pattern,
                        intruder_type,
                        seed,
                        residual_apn=getattr(controller, "residual_apn", False),
                        observation_version=getattr(
                            controller,
                            "observation_version",
                            "v2" if args.procedural else "v1",
                        ),
                        procedural=args.procedural,
                    )
                )
        all_results[controller_name] = episodes
        summaries.append(summarize(controller_name, episodes))

    output_dir = os.path.dirname(args.output) or "."
    os.makedirs(output_dir, exist_ok=True)
    comparisons = []
    if "apn" in all_results and "ppo" in all_results:
        comparisons.append(
            paired_comparison("apn", all_results["apn"], "ppo", all_results["ppo"])
        )
    with open(args.output + ".json", "w", encoding="utf-8") as handle:
        json.dump(
            {
                "evaluation_design": {
                    "paired_controller_seeds": True,
                    "procedural": args.procedural,
                    "curriculum_level": 1.0 if args.procedural else None,
                    "confidence_level": 0.95,
                    "bootstrap_samples": 10000,
                },
                "summary": summaries,
                "paired_comparisons": comparisons,
                "episodes": all_results,
            },
            handle,
            indent=2,
        )
    with open(args.output + ".csv", "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(summaries[0]))
        writer.writeheader()
        writer.writerows(summaries)

    for summary in summaries:
        print(
            f"{summary['controller']:>8}: "
            f"{summary['intercept_rate']:.1%} intercepts, "
            f"{summary['mean_minimum_separation_m']:.1f} m mean closest approach, "
            f"{summary['mean_energy_used']:.1f} energy"
        )
    print(f"Saved {args.output}.json and {args.output}.csv")


if __name__ == "__main__":
    main()
