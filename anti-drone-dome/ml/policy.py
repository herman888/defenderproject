"""Stable-Baselines3 policy adapter for the live simulator."""

from guidance.setpoint import GuidanceSetpoint, enu_to_ned
from guidance.intercept import PurePursuitGuidance
from guidance.setpoint import ned_to_enu
from ml.observation import encode_observation, encode_observation_v2


class LivePolicy:
    def __init__(self, model_path, residual_apn=True, device="auto"):
        try:
            from stable_baselines3 import PPO
        except ImportError as exc:
            raise RuntimeError(
                "stable-baselines3 is required to load an ML policy"
            ) from exc
        self.model = PPO.load(model_path, device=device)
        self.device = str(self.model.device)
        self.observation_size = int(self.model.observation_space.shape[0])
        if self.observation_size not in (16, 21):
            raise ValueError(
                f"Unsupported policy observation size: {self.observation_size}"
            )
        self.residual_apn = residual_apn
        self.guidance = PurePursuitGuidance()

    def compute_setpoint(
        self, interceptor_state, target_track, track_confidence, wind, elapsed_fraction
    ):
        encoder_args = (
            interceptor_state["position"],
            interceptor_state["velocity"],
            target_track["position_estimate"],
            target_track.get("velocity", (0.0, 0.0, 0.0)),
            track_confidence,
            wind,
            elapsed_fraction,
        )
        observation = (
            encode_observation_v2(*encoder_args, 1.0, 0.0)
            if self.observation_size == 21
            else encode_observation(*encoder_args)
        )
        action, _ = self.model.predict(observation, deterministic=True)
        action_scale = (90.0, 90.0, 60.0)
        if self.residual_apn:
            base_setpoint = self.guidance.compute_guidance(
                interceptor_state, target_track
            )
            base_accel = (
                ned_to_enu(base_setpoint.accel)
                if base_setpoint.accel is not None
                else (0.0, 0.0, 0.0)
            )
            accel_enu = tuple(
                float(base_accel[index]) + 0.25 * float(action[index]) * action_scale[index]
                for index in range(3)
            )
        else:
            accel_enu = tuple(
                float(action[index]) * action_scale[index] for index in range(3)
            )
        return GuidanceSetpoint(frame="LOCAL_NED", accel=enu_to_ned(accel_enu))
