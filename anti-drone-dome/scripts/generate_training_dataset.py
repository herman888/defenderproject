"""Export repeatable expert trajectories from the procedural engagement curriculum."""

import argparse
import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from ml.controllers import APNController
from ml.environment import InterceptionEnv


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--episodes", type=int, default=250)
    parser.add_argument("--seed", type=int, default=2026)
    parser.add_argument("--difficulty-min", type=float, default=0.15)
    parser.add_argument("--difficulty-max", type=float, default=1.0)
    parser.add_argument("--sample-every", type=int, default=4)
    parser.add_argument("--output", default="datasets/interceptor_expert_v2")
    args = parser.parse_args()
    if args.episodes <= 0:
        parser.error("--episodes must be positive")
    if not 0.0 <= args.difficulty_min <= args.difficulty_max <= 1.0:
        parser.error("difficulty range must satisfy 0 <= min <= max <= 1")
    if args.sample_every <= 0:
        parser.error("--sample-every must be positive")

    controller = APNController()
    observations = []
    actions = []
    episode_indices = []
    scenario_ids = []
    episode_results = []

    for episode in range(args.episodes):
        fraction = episode / max(args.episodes - 1, 1)
        difficulty = (
            args.difficulty_min
            + (args.difficulty_max - args.difficulty_min) * fraction
        )
        env = InterceptionEnv(
            domain_randomization=True,
            procedural_scenarios=True,
            curriculum_level=difficulty,
            observation_version="v2",
        )
        observation, info = env.reset(seed=args.seed + episode)
        terminated = truncated = False
        step = 0
        minimum_separation = info["separation_m"]
        while not (terminated or truncated):
            action = controller.predict(observation, env)
            if step % args.sample_every == 0:
                observations.append(observation.copy())
                actions.append(action.copy())
                episode_indices.append(episode)
                scenario_ids.append(info["scenario_id"])
            observation, _, terminated, truncated, info = env.step(action)
            minimum_separation = min(minimum_separation, info["separation_m"])
            step += 1
        episode_results.append({
            "episode": episode,
            "seed": args.seed + episode,
            "scenario_id": info["scenario_id"],
            "profile": info["scenario_profile"],
            "intruder_type": info["intruder_type"],
            "difficulty": difficulty,
            "intercepted": bool(info["intercepted"]),
            "minimum_separation_m": minimum_separation,
            "duration_s": env.steps * env.dt,
            "sensor_latency_s": info["configured_sensor_latency_s"],
            "interceptor_start_m": list(info["interceptor_start_m"]),
        })
        env.close()

    output_dir = os.path.dirname(args.output) or "."
    os.makedirs(output_dir, exist_ok=True)
    np.savez_compressed(
        args.output + ".npz",
        observations=np.asarray(observations, dtype=np.float32),
        expert_actions=np.asarray(actions, dtype=np.float32),
        episode_indices=np.asarray(episode_indices, dtype=np.int32),
        scenario_ids=np.asarray(scenario_ids),
    )
    with open(args.output + ".manifest.json", "w", encoding="utf-8") as handle:
        json.dump({
            "schema": "aegis.expert-dataset.v2",
            "observation_version": "v2-relative",
            "episodes": args.episodes,
            "samples": len(observations),
            "seed": args.seed,
            "difficulty_range": [args.difficulty_min, args.difficulty_max],
            "expert": "APN",
            "coordinate_frame": "local ENU",
            "units": "SI",
            "episode_results": episode_results,
            "sim_to_real_status": "simulation-only",
            "required_before_real_flight": [
                "calibrate dynamics against flight logs",
                "replay approved radar and EO recordings",
                "software-in-the-loop validation",
                "hardware-in-the-loop validation",
                "independent safety and range review",
            ],
        }, handle, indent=2)
    print(
        f"Saved {len(observations)} samples from {args.episodes} scenarios "
        f"to {args.output}.npz"
    )


if __name__ == "__main__":
    main()
