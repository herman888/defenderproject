"""Pure pursuit guidance law with proportional navigation and lead angle computation."""

import math
import numpy as np


_MAX_FORCE = 25.0
_NAV_GAIN = 3.0


class PurePursuitGuidance:
    def compute_guidance(self, interceptor_state: dict, target_track: dict) -> tuple:
        i_pos = np.array(interceptor_state["position"], dtype=float)
        i_vel = np.array(interceptor_state["velocity"], dtype=float)

        if not target_track.get("detected"):
            return (0.0, 0.0, 0.0)

        t_pos = np.array(target_track["position_estimate"], dtype=float)
        t_vel = np.array(target_track.get("velocity", [0, 0, 0]), dtype=float)

        los = t_pos - i_pos
        range_val = float(np.linalg.norm(los))
        if range_val < 0.1:
            return (0.0, 0.0, 0.0)

        los_unit = los / range_val

        # Closing speed
        rel_vel = i_vel - t_vel
        closing_speed = float(np.dot(rel_vel, los_unit))
        if closing_speed <= 0.01:
            closing_speed = 0.01

        # Predict intercept point
        tti = min(range_val / closing_speed, 3.0)
        predicted_pos = t_pos + t_vel * tti

        # Steer toward predicted intercept
        steer_vec = predicted_pos - i_pos
        steer_mag = float(np.linalg.norm(steer_vec))
        if steer_mag < 0.1:
            return (0.0, 0.0, 0.0)

        steer_unit = steer_vec / steer_mag
        force_vec = steer_unit * _MAX_FORCE * _NAV_GAIN

        # Clamp to max force
        mag = float(np.linalg.norm(force_vec))
        if mag > _MAX_FORCE:
            force_vec = force_vec / mag * _MAX_FORCE

        print(f"GUIDANCE: Steering to intercept at predicted pos "
              f"({predicted_pos[0]:.1f},{predicted_pos[1]:.1f},{predicted_pos[2]:.1f}), TTI={tti:.1f}s")

        return tuple(force_vec)

    def time_to_intercept(self, interceptor_state: dict, target_track: dict) -> float:
        if not target_track.get("detected"):
            return float("inf")
        i_pos = np.array(interceptor_state["position"], dtype=float)
        i_vel = np.array(interceptor_state["velocity"], dtype=float)
        t_pos = np.array(target_track["position_estimate"], dtype=float)
        t_vel = np.array(target_track.get("velocity", [0, 0, 0]), dtype=float)
        los = t_pos - i_pos
        range_val = float(np.linalg.norm(los))
        if range_val < 0.1:
            return 0.0
        los_unit = los / range_val
        rel_vel = i_vel - t_vel
        closing_speed = float(np.dot(rel_vel, los_unit))
        if closing_speed <= 0.0:
            return float("inf")
        return range_val / closing_speed

    def intercept_possible(self, interceptor_state: dict, target_track: dict) -> bool:
        tti = self.time_to_intercept(interceptor_state, target_track)
        return tti < 60.0 and tti > 0.0

    def lead_angle_deg(self, interceptor_state: dict, target_track: dict) -> float:
        if not target_track.get("detected"):
            return 0.0
        i_pos = np.array(interceptor_state["position"], dtype=float)
        i_vel = np.array(interceptor_state["velocity"], dtype=float)
        t_pos = np.array(target_track["position_estimate"], dtype=float)
        t_vel = np.array(target_track.get("velocity", [0, 0, 0]), dtype=float)
        los = t_pos - i_pos
        range_val = float(np.linalg.norm(los))
        if range_val < 0.01:
            return 0.0
        los_unit = los / range_val
        t_vel_mag = float(np.linalg.norm(t_vel))
        if t_vel_mag < 0.01:
            return 0.0
        cross = np.cross(los_unit, t_vel / t_vel_mag)
        return float(math.degrees(math.asin(min(1.0, float(np.linalg.norm(cross))))))
