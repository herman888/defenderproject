"""Gymnasium environment for training interceptor guidance policies."""

import math
from collections import deque

import gymnasium as gym
import numpy as np
from gymnasium import spaces

from config import INTERCEPT_CONTACT_RADIUS_M
from guidance.intercept import PurePursuitGuidance
from guidance.setpoint import ned_to_enu
from ml.observation import encode_observation, encode_observation_v2
from ml.scenario_curriculum import sample_scenario
from scenarios import (
    ATTACK_PATTERNS,
    INTRUDER_TYPES,
    get_environment_for_pattern,
    get_waypoints_for_path,
)


class InterceptionEnv(gym.Env):
    metadata = {"render_modes": []}

    def __init__(
        self,
        pattern=None,
        intruder_type=None,
        domain_randomization=True,
        residual_apn=False,
        procedural_scenarios=False,
        curriculum_level=1.0,
        observation_version="v1",
        fixed_scenario=None,
    ):
        super().__init__()
        self.pattern_name = pattern
        self.intruder_type_name = intruder_type
        self.domain_randomization = domain_randomization
        self.residual_apn = residual_apn
        self.procedural_scenarios = procedural_scenarios
        self.curriculum_level = float(np.clip(curriculum_level, 0.0, 1.0))
        self.fixed_scenario = fixed_scenario
        if observation_version not in ("v1", "v2"):
            raise ValueError("observation_version must be 'v1' or 'v2'")
        self.observation_version = observation_version
        self._apn = PurePursuitGuidance()
        self.dt = 0.05
        self.max_steps = 2400
        self.action_space = spaces.Box(-1.0, 1.0, shape=(3,), dtype=np.float32)
        observation_size = 21 if observation_version == "v2" else 16
        self.observation_space = spaces.Box(
            -10.0, 10.0, shape=(observation_size,), dtype=np.float32
        )

    def set_curriculum_level(self, level):
        self.curriculum_level = float(np.clip(level, 0.0, 1.0))

    def reset(self, seed=None, options=None):
        super().reset(seed=seed)
        self.scenario = None
        if self.procedural_scenarios or self.fixed_scenario is not None:
            self.scenario = (
                self.fixed_scenario
                if self.fixed_scenario is not None
                else sample_scenario(self.np_random, self.curriculum_level)
            )
            pattern_name = self.scenario.profile
            intruder_name = self.scenario.intruder_type
            self.pattern = {
                "label": pattern_name.upper(),
                "path": pattern_name,
            }
            self.environment = dict(get_environment_for_pattern("direct"))
            self.environment["sensor_dropout_probability"] = (
                self.scenario.sensor_dropout_probability
            )
            self.environment["radar_noise_std_m"] = self.scenario.radar_noise_std_m
            self.waypoints = list(self.scenario.waypoints)
            interceptor_start = self.scenario.interceptor_start
            self.sensor_latency_s = self.scenario.sensor_latency_s
            self.evasion_mps = self.scenario.evasion_mps
        else:
            pattern_name = self.pattern_name or self.np_random.choice(
                list(ATTACK_PATTERNS)
            )
            intruder_name = self.intruder_type_name or self.np_random.choice(
                list(INTRUDER_TYPES)
            )
            self.pattern = ATTACK_PATTERNS[pattern_name]
            self.environment = get_environment_for_pattern(pattern_name)
            self.waypoints = get_waypoints_for_path(self.pattern["path"])
            interceptor_start = (0.0, 0.0, 5.0)
            self.sensor_latency_s = 0.0
            self.evasion_mps = 0.0
        self.intruder = INTRUDER_TYPES[intruder_name]
        self.pattern_name_active = pattern_name
        self.intruder_type_active = intruder_name
        self.waypoint_index = 1
        self.intruder_position = np.asarray(self.waypoints[0], dtype=np.float32)
        self.intruder_velocity = np.zeros(3, dtype=np.float32)
        self.interceptor_position = np.asarray(interceptor_start, dtype=np.float32)
        self.interceptor_velocity = np.zeros(3, dtype=np.float32)
        if self.scenario is not None:
            self.wind = np.asarray(self.scenario.wind_mps, dtype=np.float32)
        else:
            mean = np.asarray(self.environment["wind_mean_mps"], dtype=np.float32)
            gust = (
                self.environment["wind_gust_mps"]
                if self.domain_randomization else 0.0
            )
            self.wind = mean + self.np_random.uniform(-gust, gust, 3).astype(
                np.float32
            )
        self.wind[2] = 0.0
        randomization_scale = (
            self.curriculum_level if self.procedural_scenarios else 1.0
        )
        self.mass_factor = float(
            self.np_random.uniform(
                1.0 - 0.18 * randomization_scale,
                1.0 + 0.25 * randomization_scale,
            )
            if self.domain_randomization else 1.0
        )
        self.actuator_time_constant_s = float(
            self.np_random.uniform(
                0.08,
                0.12 + 0.22 * randomization_scale,
            )
            if self.domain_randomization else 0.12
        )
        self.applied_acceleration = np.zeros(3, dtype=np.float32)
        self.battery_fraction = 1.0
        self.energy_used = 0.0
        self.track_confidence = 0.0
        self.sensed_intruder_position = self.intruder_position.copy()
        self._last_sensed_position = self.intruder_position.copy()
        self._sensor_history = deque(
            [self.intruder_position.copy()],
            maxlen=max(4, int(1.0 / self.dt) + 2),
        )
        self.sensor_age_s = 0.0
        self._evasion_phase = float(self.np_random.uniform(0.0, 2.0 * math.pi))
        self.steps = 0
        self.previous_separation = self._separation()
        return self._observation(), self._info()

    def step(self, action):
        action = np.clip(np.asarray(action, dtype=np.float32), -1.0, 1.0)
        residual_action = action.copy()
        if self.residual_apn:
            action = np.clip(
                self._apn_action() + 0.25 * residual_action, -1.0, 1.0
            )
        battery_thrust = 0.72 + 0.28 * self.battery_fraction
        commanded_acceleration = (
            action
            * np.asarray([90.0, 90.0, 60.0], dtype=np.float32)
            * battery_thrust
            / self.mass_factor
        )
        actuator_alpha = min(1.0, self.dt / self.actuator_time_constant_s)
        self.applied_acceleration += actuator_alpha * (
            commanded_acceleration - self.applied_acceleration
        )
        self.interceptor_velocity += self.applied_acceleration * self.dt
        speed = float(np.linalg.norm(self.interceptor_velocity))
        if speed > 70.0:
            self.interceptor_velocity *= 70.0 / speed
        self.interceptor_position += self.interceptor_velocity * self.dt

        target = np.asarray(self.waypoints[self.waypoint_index], dtype=np.float32)
        delta = target - self.intruder_position
        distance = float(np.linalg.norm(delta))
        if distance < 8.0 and self.waypoint_index < len(self.waypoints) - 1:
            self.waypoint_index += 1
            target = np.asarray(self.waypoints[self.waypoint_index], dtype=np.float32)
            delta = target - self.intruder_position
            distance = float(np.linalg.norm(delta))
        desired = delta / max(distance, 1e-6) * self.intruder["max_speed"]
        if self.evasion_mps > 0.0:
            perpendicular = np.asarray(
                [-desired[1], desired[0], 0.0], dtype=np.float32
            )
            perpendicular /= max(float(np.linalg.norm(perpendicular)), 1e-6)
            desired += (
                perpendicular
                * self.evasion_mps
                * math.sin(self.steps * self.dt * 1.7 + self._evasion_phase)
            )
        self.intruder_velocity += (desired - self.intruder_velocity) * min(1.0, 2.0 * self.dt)
        self.intruder_position += (self.intruder_velocity + self.wind) * self.dt
        self._sensor_history.append(self.intruder_position.copy())

        self.steps += 1
        power = 0.15 + 0.85 * float(np.linalg.norm(action)) / math.sqrt(3.0)
        energy_step = power * self.dt
        self.energy_used += energy_step
        self.battery_fraction = max(0.0, self.battery_fraction - energy_step / 105.0)
        separation = self._separation()
        progress = self.previous_separation - separation
        reward = progress * 0.1 - 0.01 - 0.003 * power
        if self.residual_apn:
            reward -= 0.002 * float(np.dot(residual_action, residual_action))
        intercepted = separation <= INTERCEPT_CONTACT_RADIUS_M
        breached = math.hypot(*self.intruder_position[:2]) <= 2.0
        if intercepted:
            reward += 100.0
        elif breached:
            reward -= 100.0
        self.previous_separation = separation
        terminated = intercepted or breached
        truncated = self.steps >= self.max_steps
        return self._observation(), reward, terminated, truncated, self._info()

    def _separation(self):
        return float(np.linalg.norm(self.intruder_position - self.interceptor_position))

    def _observation(self):
        base_confidence = max(
            0.0, 1.0 - np.linalg.norm(self.intruder_position) / 1500.0
        )
        dropped = (
            self.np_random.random()
            < self.environment.get("sensor_dropout_probability", 0.0)
        )
        if dropped:
            self.track_confidence = 0.0
            self.sensed_intruder_position = self._last_sensed_position.copy()
            self.sensor_age_s = min(self.sensor_age_s + self.dt, 0.5)
        else:
            self.track_confidence = base_confidence
            latency_steps = min(
                len(self._sensor_history) - 1,
                int(round(self.sensor_latency_s / self.dt)),
            )
            delayed_position = self._sensor_history[-(latency_steps + 1)]
            self.sensor_age_s = latency_steps * self.dt
            self.sensed_intruder_position = (
                delayed_position
                + self.np_random.normal(
                    0.0, self.environment["radar_noise_std_m"], 3
                )
            ).astype(np.float32)
            self._last_sensed_position = self.sensed_intruder_position.copy()
        encoder_args = (
            self.interceptor_position,
            self.interceptor_velocity,
            self.sensed_intruder_position,
            self.intruder_velocity,
            self.track_confidence,
            self.wind,
            self.steps / self.max_steps,
        )
        if self.observation_version == "v2":
            return encode_observation_v2(
                *encoder_args,
                self.battery_fraction,
                min(self.sensor_age_s / 0.5, 1.0),
            )
        return encode_observation(*encoder_args)

    def controller_state(self):
        return {
            "interceptor": {
                "position": tuple(self.interceptor_position),
                "velocity": tuple(self.interceptor_velocity),
            },
            "track": {
                "detected": self.track_confidence > 0.0,
                "position_estimate": tuple(self.sensed_intruder_position),
                "velocity": tuple(self.intruder_velocity),
                "acceleration": (0.0, 0.0, 0.0),
            },
        }

    def _apn_action(self):
        state = self.controller_state()
        setpoint = self._apn.compute_guidance(
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

    def _info(self):
        return {
            "separation_m": self._separation(),
            "intercepted": self._separation() <= INTERCEPT_CONTACT_RADIUS_M,
            "wind_mps": self.wind.copy(),
            "battery_fraction": self.battery_fraction,
            "energy_used": self.energy_used,
            "track_confidence": self.track_confidence,
            "scenario_id": (
                self.scenario.scenario_id if self.scenario else self.pattern_name_active
            ),
            "scenario_profile": self.pattern_name_active,
            "intruder_type": self.intruder_type_active,
            "airframe_profile_id": self.intruder.get("airframe_profile_id"),
            "dynamics_model": "ml-point-mass-v2",
            "curriculum_level": self.curriculum_level,
            "configured_sensor_latency_s": self.sensor_latency_s,
            "sensor_dropout_probability": self.environment.get(
                "sensor_dropout_probability", 0.0
            ),
            "radar_noise_std_m": self.environment["radar_noise_std_m"],
            "evasion_mps": self.evasion_mps,
            "mass_factor": self.mass_factor,
            "actuator_time_constant_s": self.actuator_time_constant_s,
            "sensor_age_s": self.sensor_age_s,
            "interceptor_start_m": (
                self.scenario.interceptor_start
                if self.scenario else (0.0, 0.0, 5.0)
            ),
        }
