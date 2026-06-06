"""
Direct intercept-point guidance.

Replaces APN with a two-step approach that produces a near-straight-line
trajectory:

  1. Solve the quadratic intercept equation to find the exact time T at which
     both vehicles meet if the interceptor flies at design speed V_INT:

         (V_INT² − v_t²)·T² − 2·(r·v_t)·T − |r|² = 0

     This gives the earliest positive T (optimal intercept time).

  2. Fly toward the predicted intercept point  P = t_pos + t_vel·T  by
     decomposing the interceptor's current velocity into:
       • parallel component  (toward P) — accelerate to V_INT
       • perpendicular component         — kill it completely

     Killing the perpendicular velocity is what prevents the pivot / swing
     that the old APN + close_accel combination produced: those two terms
     aimed at different points (lead vs. current) and fought each other.

  3. Terminal phase (rng < 25 m): ignore velocity state, slam maximum force
     along the LOS — ensures first-pass kill regardless of geometry at knife-range.
"""

import math
import numpy as np

_MASS      = 1.5     # interceptor mass (kg), matches URDF
_MAX_FORCE = 260.0   # N — ~17 G at 1.5 kg
_V_INT     = 65.0    # m/s — design intercept speed (below 70 m/s hard cap)
_K_LAT     = 9.0     # lateral gain: kills perpendicular velocity
_K_LON     = 4.0     # longitudinal gain: drives to design speed toward P


class PurePursuitGuidance:
    """Direct intercept-point guidance (class name kept for import compatibility)."""

    # ------------------------------------------------------------------
    def _intercept_time(self, r_vec: np.ndarray, t_vel: np.ndarray) -> float:
        """
        Minimum positive T such that the interceptor (at speed _V_INT) can
        reach the target's predicted position.

        Equation:  (V_INT² - v_t²)·T² - 2·(r·v_t)·T - |r|² = 0
        """
        v_t_sq  = float(np.dot(t_vel, t_vel))
        r_dot_v = float(np.dot(r_vec, t_vel))
        r_sq    = float(np.dot(r_vec, r_vec))

        a = _V_INT ** 2 - v_t_sq
        b = -2.0 * r_dot_v
        c = -r_sq

        if abs(a) > 0.1:
            disc = b * b - 4.0 * a * c
            if disc >= 0.0:
                sq = math.sqrt(disc)
                t1 = (-b + sq) / (2.0 * a)
                t2 = (-b - sq) / (2.0 * a)
                pos = [t for t in (t1, t2) if t > 0.05]
                if pos:
                    return float(min(max(0.3, min(pos)), 30.0))

        # Fallback when speeds are similar or no real solution
        rng = math.sqrt(max(r_sq, 1e-6))
        return float(max(0.3, rng / max(_V_INT, 1.0)))

    # ------------------------------------------------------------------
    def compute_guidance(self, interceptor_state: dict, target_track: dict) -> tuple:
        if not target_track.get("detected"):
            return (0.0, 0.0, 0.0)

        i_pos = np.array(interceptor_state["position"], dtype=float)
        i_vel = np.array(interceptor_state["velocity"],  dtype=float)
        t_pos = np.array(target_track["position_estimate"],        dtype=float)
        t_vel = np.array(target_track.get("velocity", [0, 0, 0]), dtype=float)

        r_vec = t_pos - i_pos
        rng   = float(np.linalg.norm(r_vec))
        if rng < 0.3:
            return (0.0, 0.0, 0.0)
        r_hat = r_vec / rng

        # ── Terminal phase ──────────────────────────────────────────────
        # Within 25 m: ignore velocity state and slam full force along LOS.
        # APN lateral corrections at this range can swing the interceptor
        # past the target — direct thrust is more reliable.
        if rng < 25.0:
            a_cmd    = r_hat * 130.0
            a_cmd[2] += 9.81
            force    = a_cmd * _MASS
            mag      = float(np.linalg.norm(force))
            if mag > _MAX_FORCE:
                force = force / mag * _MAX_FORCE
            return tuple(force)

        # ── Intercept point prediction ──────────────────────────────────
        T     = self._intercept_time(r_vec, t_vel)
        p_int = t_pos + t_vel * T          # where the target will be at time T

        to_ip = p_int - i_pos
        d_ip  = float(np.linalg.norm(to_ip))
        d_hat = to_ip / d_ip if d_ip > 0.1 else r_hat

        # ── Velocity decomposition ──────────────────────────────────────
        # Parallel  (toward intercept point) — drive to design speed
        # Perpendicular                       — kill it: this is what stopped
        #                                       the interceptor from pivoting
        v_para_s = float(np.dot(i_vel, d_hat))
        v_perp   = i_vel - v_para_s * d_hat

        a_lat    = -_K_LAT * v_perp                         # kill perp velocity
        a_lon    = _K_LON * (_V_INT - v_para_s) * d_hat    # match design speed

        a_cmd    = a_lat + a_lon
        a_cmd[2] += 9.81   # gravity compensation

        force = a_cmd * _MASS
        mag   = float(np.linalg.norm(force))
        if mag > _MAX_FORCE:
            force = force / mag * _MAX_FORCE

        return tuple(force)

    # ------------------------------------------------------------------
    def lead_angle_deg(self, interceptor_state: dict, target_track: dict) -> float:
        if not target_track.get("detected"):
            return 0.0
        i_pos = np.array(interceptor_state["position"], dtype=float)
        i_vel = np.array(interceptor_state["velocity"],  dtype=float)
        t_pos = np.array(target_track["position_estimate"], dtype=float)
        r_vec = t_pos - i_pos
        rng   = float(np.linalg.norm(r_vec))
        i_spd = float(np.linalg.norm(i_vel))
        if rng < 0.01 or i_spd < 0.01:
            return 0.0
        cos_a = float(np.clip(np.dot(r_vec / rng, i_vel / i_spd), -1.0, 1.0))
        return math.degrees(math.acos(cos_a))

    def time_to_intercept(self, interceptor_state: dict, target_track: dict) -> float:
        if not target_track.get("detected"):
            return float("inf")
        i_pos = np.array(interceptor_state["position"], dtype=float)
        i_vel = np.array(interceptor_state["velocity"],  dtype=float)
        t_pos = np.array(target_track["position_estimate"],        dtype=float)
        t_vel = np.array(target_track.get("velocity", [0, 0, 0]), dtype=float)
        r_vec = t_pos - i_pos
        rng   = float(np.linalg.norm(r_vec))
        if rng < 0.1:
            return 0.0
        r_hat = r_vec / rng
        v_c   = float(-np.dot(r_hat, t_vel - i_vel))
        return rng / v_c if v_c > 0.1 else float("inf")
