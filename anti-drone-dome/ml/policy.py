"""Stable-Baselines3 policy adapter for the live simulator."""

import numpy as np

from config import MAX_ACCEL
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
        self.last_diagnostics = {
            "mode": "MODEL_READY",
            "residual_authority": 0.0,
            "residual_mps2": 0.0,
            "bounded": True,
        }

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
        action = np.asarray(action, dtype=float).reshape(-1)
        if action.size < 3 or not np.all(np.isfinite(action[:3])):
            action = np.zeros(3, dtype=float)
            model_valid = False
        else:
            action = np.clip(action[:3], -1.0, 1.0)
            model_valid = True
        action_scale = np.asarray((90.0, 90.0, 60.0), dtype=float)
        base_setpoint = None
        if self.residual_apn:
            base_setpoint = self.guidance.compute_guidance(
                interceptor_state, target_track
            )
            base_accel = np.asarray(
                ned_to_enu(base_setpoint.accel)
                if base_setpoint.accel is not None
                else (0.0, 0.0, 0.0),
                dtype=float,
            )
            confidence = float(np.clip(track_confidence, 0.0, 1.0))
            # The learned policy is a bounded residual, never the sole flight
            # authority. Poor track quality automatically reduces its effect.
            residual_authority = 0.05 + 0.20 * confidence
            residual = residual_authority * action * action_scale
            accel_enu = base_accel + residual
        else:
            residual_authority = 1.0
            residual = action * action_scale
            accel_enu = residual.copy()

        accel_magnitude = float(np.linalg.norm(accel_enu))
        was_bounded = accel_magnitude > MAX_ACCEL
        if was_bounded:
            accel_enu *= MAX_ACCEL / accel_magnitude
        self.last_diagnostics = {
            "mode": (
                "BOUNDED_RESIDUAL_AI"
                if self.residual_apn
                else "BOUNDED_AI"
            ),
            "model_valid": model_valid,
            "residual_authority": residual_authority,
            "residual_mps2": float(np.linalg.norm(residual)),
            "bounded": was_bounded,
        }
        return GuidanceSetpoint(
            frame="LOCAL_NED",
            velocity=(
                base_setpoint.velocity
                if base_setpoint is not None else None
            ),
            accel=enu_to_ned(tuple(float(value) for value in accel_enu)),
            yaw=base_setpoint.yaw if base_setpoint is not None else None,
        )
