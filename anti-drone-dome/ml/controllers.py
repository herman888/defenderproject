"""Controller adapters for repeatable simulator evaluation."""

import numpy as np

from guidance.intercept import PurePursuitGuidance
from guidance.setpoint import ned_to_enu


class APNController:
    def __init__(self, terminal_law: str = "pd"):
        self.guidance = PurePursuitGuidance(terminal_law=terminal_law)

    def predict(self, observation, env):
        state = env.controller_state()
        setpoint = self.guidance.compute_guidance(
            state["interceptor"], state["track"]
        )
        if setpoint.accel is None:
            return np.zeros(3, dtype=np.float32)
        acceleration = np.asarray(ned_to_enu(setpoint.accel), dtype=np.float32)
        return np.clip(
            acceleration / np.asarray([90.0, 90.0, 60.0], dtype=np.float32),
            -1.0,
            1.0,
        )


class RandomController:
    def __init__(self, seed=0):
        self.rng = np.random.default_rng(seed)

    def predict(self, observation, env):
        return self.rng.uniform(-1.0, 1.0, 3).astype(np.float32)


class PPOController:
    def __init__(self, model_path, residual_apn=False):
        from stable_baselines3 import PPO

        self.model = PPO.load(model_path)
        self.residual_apn = residual_apn
        observation_size = int(self.model.observation_space.shape[0])
        self.observation_version = "v2" if observation_size == 21 else "v1"

    def predict(self, observation, env):
        action, _ = self.model.predict(observation, deterministic=True)
        return np.asarray(action, dtype=np.float32)
