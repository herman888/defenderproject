"""
Augmented Proportional Navigation (APN) guidance law.

BEFORE: Pure pursuit — steered toward target's *current* position.
        Predicted intercept by projecting forward with noisy velocity.
        Result: tail-chase geometry, wildly unstable predicted points,
        MAX_FORCE 25 N.

AFTER:  Augmented Proportional Navigation with N=4.
        Command acceleration:
            a_cmd = N * Vc * (omega_LOS x r_hat) + (N/2) * a_target

        where:
            N         = 4  (navigation constant — standard for intercept)
            Vc        = closing speed (m/s), positive when closing
            omega_LOS = LOS angular velocity vector (rad/s)
            r_hat     = unit LOS vector
            a_target  = Kalman-derived target acceleration (from radar)

        The PN term steers to null the LOS rotation rate, producing a
        collision-course (lead-pursuit) geometry — interceptor flies
        perpendicular to the intruder's path, not tail-chasing it.
        The APN augmentation feedforwards target acceleration so the
        guidance anticipates manoeuvres without lagging.

        Gravity compensated in vertical channel.
        MAX_FORCE 60 N (vs 25 N before).
"""

import numpy as np

_N         = 4.0    # navigation constant
_MASS      = 1.5    # interceptor mass (kg), matches URDF
_MAX_FORCE = 60.0   # N  (was 25 N)
_ACC_CLAMP = 5.0    # clamp on target accel input to suppress Kalman spikes


class PurePursuitGuidance:
    """Augmented Proportional Navigation interceptor guidance (name kept for import compatibility)."""

    def compute_guidance(self, interceptor_state: dict, target_track: dict) -> tuple:
        if not target_track.get("detected"):
            return (0.0, 0.0, 0.0)

        i_pos = np.array(interceptor_state["position"], dtype=float)
        i_vel = np.array(interceptor_state["velocity"],  dtype=float)
        t_pos = np.array(target_track["position_estimate"],           dtype=float)
        t_vel = np.array(target_track.get("velocity",     [0,0,0]),   dtype=float)
        t_acc = np.array(target_track.get("acceleration", [0,0,0]),   dtype=float)

        # LOS geometry
        r_vec = t_pos - i_pos
        rng   = float(np.linalg.norm(r_vec))
        if rng < 0.5:
            return (0.0, 0.0, 0.0)
        r_hat = r_vec / rng

        # Relative velocity (target w.r.t. interceptor)
        v_rel = t_vel - i_vel

        # Closing speed: positive = closing in
        v_c = float(-np.dot(r_hat, v_rel))

        # LOS angular velocity: omega = (r x v_rel) / r^2
        omega = np.cross(r_vec, v_rel) / (rng**2)

        # PN term: lateral steering — nulls LOS rotation rate (collision course)
        a_pn = _N * v_c * np.cross(omega, r_hat)

        # APN augmentation: target acceleration feedforward
        acc_mag = float(np.linalg.norm(t_acc))
        if acc_mag > _ACC_CLAMP:
            t_acc = t_acc / acc_mag * _ACC_CLAMP
        a_aug = (_N / 2.0) * t_acc

        # Closing acceleration along LOS — PN only steers laterally; without
        # this term the interceptor corrects angle but barely drives range down.
        # Proportional to range (full thrust far out, eases off at close range).
        close_accel = float(np.clip(rng * 3.0, 0.0, 25.0))
        a_close = r_hat * close_accel

        # Total commanded acceleration
        a_cmd    = a_pn + a_aug + a_close
        a_cmd[2] += 9.81   # gravity compensation (vertical channel)

        force = a_cmd * _MASS
        mag   = float(np.linalg.norm(force))
        if mag > _MAX_FORCE:
            force = force / mag * _MAX_FORCE

        return tuple(force)

    def time_to_intercept(self, interceptor_state: dict, target_track: dict) -> float:
        if not target_track.get("detected"):
            return float("inf")
        i_pos = np.array(interceptor_state["position"], dtype=float)
        i_vel = np.array(interceptor_state["velocity"],  dtype=float)
        t_pos = np.array(target_track["position_estimate"],         dtype=float)
        t_vel = np.array(target_track.get("velocity", [0,0,0]),     dtype=float)
        r_vec = t_pos - i_pos
        rng   = float(np.linalg.norm(r_vec))
        if rng < 0.1:
            return 0.0
        r_hat = r_vec / rng
        v_c   = float(-np.dot(r_hat, t_vel - i_vel))
        return rng / v_c if v_c > 0.1 else float("inf")
