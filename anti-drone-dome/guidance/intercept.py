"""
Guidance laws for the anti-drone interceptor.

PRIMARY: Augmented Proportional Navigation (APN)
─────────────────────────────────────────────────
    a_cmd = N' · Vc · λ̇   +   (N'/2) · a_t,⊥

    Term 1 — N'·Vc·λ̇      drives line-of-sight rotation rate to zero
                          (classical PN, the geometric homing core).
    Term 2 — (N'/2)·a_t,⊥ compensates for the target's *measured* lateral
                          acceleration — the augmentation that lifts APN
                          above PN against maneuvering targets such as the
                          SPIRAL evasive attack pattern.

Numerical recipes (3-D vector form):
    r_vec      = t_pos - i_pos                       LOS vector
    r_hat      = r_vec / |r_vec|                     LOS unit vector
    v_rel      = t_vel - i_vel                       relative velocity
    Vc         = -dot(r_hat, v_rel)                  closing velocity (>0 = closing)
    ω_LOS      = cross(r_vec, v_rel) / |r_vec|²      LOS angular-rate vector
    λ̇_vec      = cross(ω_LOS, r_hat)                 LOS rate, in engagement plane
    a_t,⊥      = a_est - dot(a_est, r_hat)·r_hat     target accel ⊥ to LOS

Target acceleration a_est is the LP-filtered estimate already produced by
sensors/radar.py (KalmanTracker.acc).

Terminal phase (rng < ~25 m): smoothly taper the APN command out and blend
into a flat LOS-aligned thrust over a 10 m window.

LEGACY: the original direct intercept-point guidance is retained as
_LegacyGuidance for A/B comparison testing only (see
tests/test_apn_comparison.py). Not exported via guidance/__init__.

Output contract (Stage A)
─────────────────────────
compute_guidance() returns a guidance.setpoint.GuidanceSetpoint in
LOCAL_NED frame — NOT a force vector. Mass, gravity compensation, and
force saturation now live in the flight controller (placeholder FC
inside sim/drone.py for Stage A; ArduPilot over MAVLink in Stage B).

  Mid-course (and blend region):  velocity + accel feed-forward + yaw-to-LOS
  Terminal   (rng <= _R_TERM):    pure accel, free yaw
"""

import math
import numpy as np

from config import MAX_ACCEL
from guidance.setpoint import GuidanceSetpoint, enu_to_ned, los_yaw_ned

_V_INT             = 65.0    # m/s — design intercept speed (below 70 m/s hard cap)
_K_LON             = 4.0     # longitudinal gain — drives v_parallel toward _V_INT
_N_PRIME_DEFAULT   = 4.0     # APN navigation gain (textbook range: 3–5)
_R_TAPER           = 25.0    # m — APN starts blending out at this range
_R_TERM            = 15.0    # m — pure LOS thrust below this range
_TERM_THRUST_ACCEL = 130.0   # m/s² along LOS in pure terminal phase


def _cap_accel(a_enu: np.ndarray) -> np.ndarray:
    """Saturate an acceleration vector to the guidance MAX_ACCEL envelope."""
    mag = float(np.linalg.norm(a_enu))
    if mag > MAX_ACCEL:
        return a_enu * (MAX_ACCEL / mag)
    return a_enu


class PurePursuitGuidance:
    """Augmented Proportional Navigation guidance.

    Class name retained for import compatibility with main.py and
    guidance/__init__.py; the underlying law is now APN.
    """

    def __init__(self, N_prime: float = _N_PRIME_DEFAULT):
        self._N_prime = float(N_prime)

    # ------------------------------------------------------------------
    def compute_guidance(self, interceptor_state: dict,
                         target_track: dict) -> GuidanceSetpoint:
        if not target_track.get("detected"):
            return GuidanceSetpoint()

        i_pos = np.array(interceptor_state["position"], dtype=float)
        i_vel = np.array(interceptor_state["velocity"], dtype=float)
        t_pos = np.array(target_track["position_estimate"],            dtype=float)
        t_vel = np.array(target_track.get("velocity",     [0, 0, 0]), dtype=float)
        a_est = np.array(target_track.get("acceleration", [0, 0, 0]), dtype=float)

        r_vec = t_pos - i_pos
        rng   = float(np.linalg.norm(r_vec))
        if rng < 0.3:
            return GuidanceSetpoint()
        r_hat = r_vec / rng

        # ── Pure-terminal LOS acceleration (computed unconditionally for blending) ──
        # Gravity comp is the FC's job now — guidance speaks pure m/s².
        a_term = r_hat * _TERM_THRUST_ACCEL

        # ── Augmented Proportional Navigation core ─────────────────────────
        v_rel = t_vel - i_vel

        # Vc: closing velocity = -d|r|/dt. Clamped to ≥0 — if the target is
        # opening, the λ̇ term would otherwise reverse sign and steer outward.
        V_c = max(float(-np.dot(r_hat, v_rel)), 0.0)

        # ω_LOS = (r × v_rel) / |r|²;  λ̇_vec = ω_LOS × r_hat (engagement plane).
        omega_LOS      = np.cross(r_vec, v_rel) / (rng * rng)
        lambda_dot_vec = np.cross(omega_LOS, r_hat)

        # Term 1 — N'·Vc·λ̇  (classical PN)
        a_pn = self._N_prime * V_c * lambda_dot_vec

        # Term 2 — (N'/2)·a_target,⊥  (APN augmentation)
        a_t_perp = a_est - float(np.dot(a_est, r_hat)) * r_hat
        a_aug    = (self._N_prime / 2.0) * a_t_perp

        # Longitudinal closure — interceptor launches from rest; without an
        # axial term it would never accelerate toward the target.
        v_para = float(np.dot(i_vel, r_hat))
        a_lon  = _K_LON * (_V_INT - v_para) * r_hat

        a_apn = a_pn + a_aug + a_lon

        # ── Smooth terminal blend ──────────────────────────────────────────
        # w = 0 at rng >= _R_TAPER  → pure APN
        # w = 1 at rng <= _R_TERM   → pure LOS thrust
        if rng >= _R_TAPER:
            w = 0.0
        elif rng <= _R_TERM:
            w = 1.0
        else:
            w = (_R_TAPER - rng) / (_R_TAPER - _R_TERM)

        a_cmd_enu = _cap_accel((1.0 - w) * a_apn + w * a_term)

        # ── Pack as setpoint ───────────────────────────────────────────────
        if w >= 1.0:
            # Pure terminal — accel only, free yaw.
            return GuidanceSetpoint(
                frame = "LOCAL_NED",
                accel = enu_to_ned(tuple(a_cmd_enu)),
            )

        # Mid-course / blend — velocity setpoint at design speed along LOS,
        # accel feed-forward carries the APN math, yaw points at target.
        v_des_enu = r_hat * _V_INT
        return GuidanceSetpoint(
            frame    = "LOCAL_NED",
            velocity = enu_to_ned(tuple(v_des_enu)),
            accel    = enu_to_ned(tuple(a_cmd_enu)),
            yaw      = los_yaw_ned(tuple(i_pos), tuple(t_pos)),
        )

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


# ──────────────────────────────────────────────────────────────────────────
# Legacy guidance — direct intercept-point pursuit (pre-APN)
# ──────────────────────────────────────────────────────────────────────────
# Retained verbatim for A/B comparison testing only.  Not exported via
# guidance/__init__.py.  Behaviour: predict intercept time T via quadratic,
# decompose interceptor velocity along/perpendicular to the predicted
# intercept point, kill the perpendicular component, drive parallel to
# design speed.  Hard 25 m switch to flat LOS thrust at terminal range —
# this is the discontinuity the new code replaces with a smooth taper.

class _LegacyGuidance:
    """Original direct intercept-point guidance. For testing only."""

    _K_LAT    = 9.0    # lateral gain — kills perpendicular velocity
    _K_LON    = 4.0    # longitudinal gain — drives to design speed toward P
    _R_SWITCH = 25.0   # m — hard switch into pure terminal LOS thrust

    def _intercept_time(self, r_vec: np.ndarray, t_vel: np.ndarray) -> float:
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

        rng = math.sqrt(max(r_sq, 1e-6))
        return float(max(0.3, rng / max(_V_INT, 1.0)))

    def compute_guidance(self, interceptor_state: dict,
                         target_track: dict) -> GuidanceSetpoint:
        if not target_track.get("detected"):
            return GuidanceSetpoint()

        i_pos = np.array(interceptor_state["position"], dtype=float)
        i_vel = np.array(interceptor_state["velocity"],  dtype=float)
        t_pos = np.array(target_track["position_estimate"],        dtype=float)
        t_vel = np.array(target_track.get("velocity", [0, 0, 0]), dtype=float)

        r_vec = t_pos - i_pos
        rng   = float(np.linalg.norm(r_vec))
        if rng < 0.3:
            return GuidanceSetpoint()
        r_hat = r_vec / rng

        # Terminal — pure accel along LOS, free yaw.
        if rng < self._R_SWITCH:
            a_cmd_enu = _cap_accel(r_hat * 130.0)
            return GuidanceSetpoint(
                frame = "LOCAL_NED",
                accel = enu_to_ned(tuple(a_cmd_enu)),
            )

        # Mid-course — predict intercept point, decompose velocity, command
        # along the predicted-intercept direction.
        T     = self._intercept_time(r_vec, t_vel)
        p_int = t_pos + t_vel * T
        to_ip = p_int - i_pos
        d_ip  = float(np.linalg.norm(to_ip))
        d_hat = to_ip / d_ip if d_ip > 0.1 else r_hat

        v_para_s = float(np.dot(i_vel, d_hat))
        v_perp   = i_vel - v_para_s * d_hat

        a_lat = -self._K_LAT * v_perp
        a_lon = self._K_LON * (_V_INT - v_para_s) * d_hat
        a_cmd_enu = _cap_accel(a_lat + a_lon)

        v_des_enu = d_hat * _V_INT
        return GuidanceSetpoint(
            frame    = "LOCAL_NED",
            velocity = enu_to_ned(tuple(v_des_enu)),
            accel    = enu_to_ned(tuple(a_cmd_enu)),
            yaw      = los_yaw_ned(tuple(i_pos), tuple(p_int)),
        )
