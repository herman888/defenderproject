"""Train and evaluate a PPO interceptor policy."""

import argparse
import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from ml.controllers import APNController
from ml.environment import InterceptionEnv


def pretrain_from_apn(
    model,
    sample_count,
    epochs,
    seed,
    observation_version,
    procedural_scenarios,
):
    if sample_count <= 0 or epochs <= 0:
        return
    import torch

    env = InterceptionEnv(
        domain_randomization=True,
        procedural_scenarios=procedural_scenarios,
        curriculum_level=0.35,
        observation_version=observation_version,
    )
    controller = APNController()
    observation, _ = env.reset(seed=seed)
    observations = []
    actions = []
    for _ in range(sample_count):
        action = controller.predict(observation, env)
        observations.append(observation.copy())
        actions.append(action.copy())
        observation, _, terminated, truncated, _ = env.step(action)
        if terminated or truncated:
            observation, _ = env.reset()

    observation_tensor = torch.as_tensor(
        np.asarray(observations), dtype=torch.float32, device=model.device
    )
    action_tensor = torch.as_tensor(
        np.asarray(actions), dtype=torch.float32, device=model.device
    )
    optimizer = torch.optim.Adam(model.policy.parameters(), lr=1e-3)
    batch_size = 512
    rng = np.random.default_rng(seed)
    for epoch in range(epochs):
        losses = []
        permutation = rng.permutation(sample_count)
        for start in range(0, sample_count, batch_size):
            indices = permutation[start:start + batch_size]
            distribution = model.policy.get_distribution(observation_tensor[indices])
            predicted = distribution.distribution.mean
            loss = torch.nn.functional.mse_loss(predicted, action_tensor[indices])
            optimizer.zero_grad()
            loss.backward()
            optimizer.step()
            losses.append(float(loss.detach().cpu()))
        print(f"APN imitation epoch {epoch + 1}/{epochs}: loss={np.mean(losses):.6f}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--steps", type=int, default=500000)
    parser.add_argument("--output", default="models/interceptor_ppo")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--envs", type=int, default=4)
    parser.add_argument("--eval-episodes", type=int, default=12)
    parser.add_argument("--checkpoint-every", type=int, default=100000)
    parser.add_argument("--apn-pretrain-samples", type=int, default=20000)
    parser.add_argument("--apn-pretrain-epochs", type=int, default=6)
    parser.add_argument("--absolute-actions", action="store_true",
                        help="Train absolute acceleration instead of safer APN residuals")
    parser.add_argument(
        "--observation-version",
        choices=("v1", "v2"),
        default="v2",
        help="v2 uses translation-invariant relative geometry",
    )
    parser.add_argument(
        "--static-scenarios",
        action="store_true",
        help="Disable procedural spawn geometry and curriculum",
    )
    parser.add_argument("--curriculum-start", type=float, default=0.15)
    parser.add_argument(
        "--device",
        choices=("auto", "cpu", "cuda"),
        default="auto",
        help="PyTorch training device; cuda requires a CUDA-enabled torch build",
    )
    args = parser.parse_args()

    from stable_baselines3 import PPO
    from stable_baselines3.common.callbacks import (
        BaseCallback,
        CheckpointCallback,
        EvalCallback,
    )
    from stable_baselines3.common.env_checker import check_env
    from stable_baselines3.common.env_util import make_vec_env
    from stable_baselines3.common.vec_env import SubprocVecEnv

    residual_apn = not args.absolute_actions
    procedural_scenarios = not args.static_scenarios

    class CurriculumCallback(BaseCallback):
        def __init__(self, start_level, update_every=5000):
            super().__init__()
            self.start_level = float(np.clip(start_level, 0.0, 1.0))
            self.update_every = update_every
            self._last_update = -update_every

        def _on_step(self):
            if self.num_timesteps - self._last_update < self.update_every:
                return True
            progress = min(
                1.0,
                self.num_timesteps / max(float(self.model._total_timesteps), 1.0),
            )
            level = self.start_level + (1.0 - self.start_level) * progress
            self.training_env.env_method("set_curriculum_level", level)
            self._last_update = self.num_timesteps
            self.logger.record("curriculum/difficulty", level)
            return True

    env = InterceptionEnv(
        domain_randomization=True,
        residual_apn=residual_apn,
        procedural_scenarios=procedural_scenarios,
        curriculum_level=args.curriculum_start,
        observation_version=args.observation_version,
    )
    check_env(env)
    output_dir = os.path.dirname(args.output) or "."
    os.makedirs(output_dir, exist_ok=True)
    artifact_dir = args.output + "_artifacts"
    os.makedirs(artifact_dir, exist_ok=True)
    train_env = make_vec_env(
        InterceptionEnv,
        n_envs=args.envs,
        seed=args.seed,
        env_kwargs={
            "domain_randomization": True,
            "residual_apn": residual_apn,
            "procedural_scenarios": procedural_scenarios,
            "curriculum_level": args.curriculum_start,
            "observation_version": args.observation_version,
        },
        vec_env_cls=SubprocVecEnv if args.envs > 1 else None,
    )
    eval_env = make_vec_env(
        InterceptionEnv,
        n_envs=1,
        seed=args.seed + 10000,
        env_kwargs={
            "domain_randomization": True,
            "residual_apn": residual_apn,
            "procedural_scenarios": procedural_scenarios,
            "curriculum_level": 1.0,
            "observation_version": args.observation_version,
        },
        vec_env_cls=SubprocVecEnv if args.envs > 1 else None,
    )
    checkpoint = CheckpointCallback(
        save_freq=max(args.checkpoint_every // max(args.envs, 1), 1),
        save_path=os.path.join(artifact_dir, "checkpoints"),
        name_prefix="interceptor",
    )
    evaluation = EvalCallback(
        eval_env,
        best_model_save_path=os.path.join(artifact_dir, "best"),
        log_path=os.path.join(artifact_dir, "evaluation"),
        eval_freq=max(args.checkpoint_every // max(args.envs, 1), 1),
        n_eval_episodes=args.eval_episodes,
        deterministic=True,
    )
    model = PPO(
        "MlpPolicy",
        train_env,
        verbose=1,
        seed=args.seed,
        tensorboard_log="runs/rl",
        batch_size=256,
        device=args.device,
    )
    if residual_apn:
        model.policy.log_std.data.fill_(-1.5)
    else:
        pretrain_from_apn(
            model,
            args.apn_pretrain_samples,
            args.apn_pretrain_epochs,
            args.seed,
            args.observation_version,
            procedural_scenarios,
        )
    callbacks = [checkpoint, evaluation]
    if procedural_scenarios:
        callbacks.append(CurriculumCallback(args.curriculum_start))
    model.learn(
        total_timesteps=args.steps,
        callback=callbacks,
        progress_bar=True,
    )
    model.save(args.output)
    with open(args.output + ".manifest.json", "w", encoding="utf-8") as handle:
        json.dump({
            "schema": "aegis.policy.v2",
            "observation_version": args.observation_version,
            "observation_size": int(env.observation_space.shape[0]),
            "action_mode": "absolute" if args.absolute_actions else "residual_apn",
            "procedural_scenarios": procedural_scenarios,
            "curriculum_start": args.curriculum_start,
            "curriculum_end": 1.0 if procedural_scenarios else None,
            "seed": args.seed,
            "timesteps": args.steps,
            "training_device": str(model.device),
            "validation_required": [
                "held_out_simulation",
                "software_in_the_loop",
                "hardware_in_the_loop",
                "approved_real_sensor_replay",
                "range_safety_review",
            ],
        }, handle, indent=2)
    train_env.close()
    eval_env.close()
    print(f"Saved policy to {args.output}.zip")


if __name__ == "__main__":
    main()
