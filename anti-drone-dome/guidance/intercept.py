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

_V_INT             = 68.0    # m/s — nominal intercept speed (below 70 m/s hard cap)
_K_LON             = 4.0     # nominal longitudinal gain
_N_PRIME_DEFAULT   = 4.0     # nominal APN navigation gain
_R_TAPER           = 25.0    # m — nominal APN/terminal blend start
_R_TERM            = 15.0    # m — nominal pure-terminal distance
_TERM_THRUST_ACCEL = 130.0   # m/s² nominal terminal acceleration


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

    def __init__(
        self,
        N_prime: float = _N_PRIME_DEFAULT,
        design_speed_mps: float = _V_INT,
        adaptive: bool = True,
    ):
        self._N_prime = float(N_prime)
        self._design_speed_mps = float(design_speed_mps)
        self._adaptive = bool(adaptive)
        self.last_diagnostics = {
            "mode": "WAITING",
            "navigation_gain": self._N_prime,
            "command_speed_mps": 0.0,
            "closing_speed_mps": 0.0,
            "los_rate_dps": 0.0,
            "track_confidence": 0.0,
            "target_maneuver_mps2": 0.0,
            "terminal_blend": 0.0,
            "lead_time_s": 0.0,
            "lead_angle_deg": 0.0,
        }

    # ------------------------------------------------------------------
    def _compute_guidance_fixed(self, interceptor_state: dict,
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
    @staticmethod
    def _confidence(target_track: dict) -> float:
        value = target_track.get(
            "confidence",
            target_track.get("track_confidence", 1.0),
        )
        try:
            return float(np.clip(float(value), 0.0, 1.0))
        except (TypeError, ValueError):
            return 0.0

    @staticmethod
    def _constant_velocity_intercept_time(
        relative_position: np.ndarray,
        target_velocity: np.ndarray,
        interceptor_speed: float,
    ) -> float | None:
        """Return the earliest positive constant-speed intercept solution."""
        speed = max(float(interceptor_speed), 1e-6)
        a = float(np.dot(target_velocity, target_velocity) - speed**2)
        b = 2.0 * float(np.dot(relative_position, target_velocity))
        c = float(np.dot(relative_position, relative_position))
        roots = []
        if abs(a) < 1e-9:
            if abs(b) > 1e-9:
                roots.append(-c / b)
        else:
            discriminant = b * b - 4.0 * a * c
            if discriminant >= 0.0:
                root = math.sqrt(discriminant)
                roots.extend((
                    (-b - root) / (2.0 * a),
                    (-b + root) / (2.0 * a),
                ))
        positive = [value for value in roots if value > 0.0]
        return min(positive) if positive else None

    def _lead_solution(
        self,
        interceptor_position: np.ndarray,
        target_position: np.ndarray,
        target_velocity: np.ndarray,
        target_acceleration: np.ndarray,
        command_speed: float,
        track_confidence: float,
    ) -> tuple[np.ndarray, float]:
        """Compute a bounded acceleration-aware future aim point.

        The constant-velocity quadratic supplies a stable initial solution.
        Two fixed-point refinements then account for a short, confidence-scaled
        target maneuver horizon without extrapolating noisy acceleration across
        an entire long-range engagement.
        """
        relative_position = target_position - interceptor_position
        intercept_time = self._constant_velocity_intercept_time(
            relative_position,
            target_velocity,
            command_speed,
        )
        if intercept_time is None:
            intercept_time = (
                np.linalg.norm(relative_position)
                / max(command_speed, 1.0)
            )
        intercept_time = float(np.clip(intercept_time, 0.0, 20.0))

        acceleration = np.asarray(target_acceleration, dtype=float)
        acceleration_magnitude = float(np.linalg.norm(acceleration))
        if acceleration_magnitude > 20.0:
            acceleration *= 20.0 / acceleration_magnitude
        acceleration *= float(np.clip(track_confidence, 0.0, 1.0))

        lead_point = target_position.copy()
        for _ in range(2):
            maneuver_horizon = min(intercept_time, 1.5)
            lead_point = (
                target_position
                + target_velocity * intercept_time
                + 0.5 * acceleration * maneuver_horizon**2
            )
            intercept_time = float(np.clip(
                np.linalg.norm(lead_point - interceptor_position)
                / max(command_speed, 1.0),
                0.0,
                20.0,
            ))
        return lead_point, intercept_time

    def _adaptive_parameters(
        self,
        *,
        rng: float,
        closing_speed: float,
        los_rate_rad_s: float,
        target_speed: float,
        target_maneuver: float,
        track_confidence: float,
        energy_fraction: float,
    ) -> tuple[float, float, float, float, float]:
        """Select bounded guidance parameters from the live engagement state."""
        if not self._adaptive:
            return (
                self._N_prime,
                self._design_speed_mps,
                _K_LON,
                _R_TERM,
                _R_TAPER,
            )

        maneuver_ratio = float(np.clip(target_maneuver / 14.0, 0.0, 1.0))
        crossing_ratio = float(np.clip(
            los_rate_rad_s * rng / max(closing_speed, 8.0),
            0.0,
            1.0,
        ))
        closing_deficit = float(np.clip(
            (18.0 - closing_speed) / 18.0,
            0.0,
            1.0,
        ))
        navigation_gain = float(np.clip(
            self._N_prime
            + 1.15 * maneuver_ratio
            + 0.85 * crossing_ratio
            + 0.35 * closing_deficit,
            3.0,
            6.2,
        ))

        closure_margin = float(np.clip(10.0 + rng / 18.0, 14.0, 31.0))
        command_speed = float(np.clip(
            target_speed + closure_margin,
            42.0,
            self._design_speed_mps,
        ))
        if closing_speed <= 0.0:
            command_speed = self._design_speed_mps
        if track_confidence < 0.45 and rng > 80.0:
            command_speed *= 0.88 + 0.12 * track_confidence / 0.45
        if energy_fraction < 0.25:
            command_speed *= 0.82 + 0.72 * energy_fraction
        command_speed = float(np.clip(
            command_speed,
            min(36.0, self._design_speed_mps),
            self._design_speed_mps,
        ))

        longitudinal_gain = float(np.clip(
            2.8 + rng / 180.0 + 0.9 * closing_deficit,
            2.8,
            5.4,
        ))
        terminal_range = float(np.clip(
            10.0 + max(closing_speed, 0.0) * 0.08,
            12.0,
            _R_TERM,
        ))
        taper_range = float(np.clip(
            terminal_range + 8.0 + max(closing_speed, 0.0) * 0.04,
            terminal_range + 8.0,
            _R_TAPER + 4.0,
        ))
        return (
            navigation_gain,
            command_speed,
            longitudinal_gain,
            terminal_range,
            taper_range,
        )

    def compute_guidance(
        self,
        interceptor_state: dict,
        target_track: dict,
    ) -> GuidanceSetpoint:
        """Adaptive APN with confidence gating and dynamic terminal behavior."""
        if not target_track.get("detected"):
            self.last_diagnostics["mode"] = "WAITING"
            return GuidanceSetpoint()

        i_pos = np.asarray(interceptor_state["position"], dtype=float)
        i_vel = np.asarray(interceptor_state["velocity"], dtype=float)
        t_pos = np.asarray(target_track["position_estimate"], dtype=float)
        t_vel = np.asarray(target_track.get("velocity", [0, 0, 0]), dtype=float)
        a_est = np.asarray(
            target_track.get("acceleration", [0, 0, 0]),
            dtype=float,
        )

        r_vec = t_pos - i_pos
        rng = float(np.linalg.norm(r_vec))
        if rng < 0.3:
            self.last_diagnostics["mode"] = "CONTACT"
            return GuidanceSetpoint()
        r_hat = r_vec / rng
        v_rel = t_vel - i_vel
        signed_closing = float(-np.dot(r_hat, v_rel))
        closing_for_pn = max(signed_closing, 0.0)
        omega_los = np.cross(r_vec, v_rel) / (rng * rng)
        lambda_dot_vec = np.cross(omega_los, r_hat)
        los_rate = float(np.linalg.norm(omega_los))
        a_t_perp = a_est - float(np.dot(a_est, r_hat)) * r_hat
        target_maneuver = float(np.linalg.norm(a_t_perp))
        track_confidence = self._confidence(target_track)
        energy_fraction = float(np.clip(
            interceptor_state.get("energy_remaining_fraction", 1.0),
            0.0,
            1.0,
        ))
        (
            navigation_gain,
            command_speed,
            longitudinal_gain,
            terminal_range,
            taper_range,
        ) = self._adaptive_parameters(
            rng=rng,
            closing_speed=signed_closing,
            los_rate_rad_s=los_rate,
            target_speed=float(np.linalg.norm(t_vel)),
            target_maneuver=target_maneuver,
            track_confidence=track_confidence,
            energy_fraction=energy_fraction,
        )
        lead_point, lead_time = self._lead_solution(
            i_pos,
            t_pos,
            t_vel,
            a_est,
            command_speed,
            track_confidence,
        )
        lead_vector = lead_point - i_pos
        lead_range = float(np.linalg.norm(lead_vector))
        lead_hat = (
            lead_vector / lead_range
            if lead_range > 1e-6
            else r_hat
        )
        lead_angle = math.degrees(math.acos(float(np.clip(
            np.dot(r_hat, lead_hat),
            -1.0,
            1.0,
        ))))

        a_pn = navigation_gain * closing_for_pn * lambda_dot_vec
        a_aug = (
            navigation_gain
            / 2.0
            * track_confidence
            * a_t_perp
        )
        v_parallel = float(np.dot(i_vel, lead_hat))
        a_longitudinal = (
            longitudinal_gain * (command_speed - v_parallel) * lead_hat
        )
        a_apn = a_pn + a_aug + a_longitudinal
        terminal_accel = float(np.clip(
            82.0 + max(signed_closing, 0.0) * 1.35,
            90.0,
            min(_TERM_THRUST_ACCEL, MAX_ACCEL),
        ))
        a_terminal = r_hat * terminal_accel

        if rng >= taper_range:
            blend = 0.0
        elif rng <= terminal_range:
            blend = 1.0
        else:
            linear = (taper_range - rng) / (taper_range - terminal_range)
            blend = linear * linear * (3.0 - 2.0 * linear)
        a_cmd_enu = _cap_accel(
            (1.0 - blend) * a_apn + blend * a_terminal
        )

        self.last_diagnostics = {
            "mode": (
                "TERMINAL"
                if blend >= 1.0
                else "BLEND"
                if blend > 0.0
                else "ADAPTIVE_APN"
            ),
            "navigation_gain": navigation_gain,
            "command_speed_mps": command_speed,
            "closing_speed_mps": signed_closing,
            "los_rate_dps": math.degrees(los_rate),
            "track_confidence": track_confidence,
            "target_maneuver_mps2": target_maneuver,
            "terminal_blend": blend,
            "lead_time_s": lead_time,
            "lead_angle_deg": lead_angle,
        }

        if blend >= 1.0:
            return GuidanceSetpoint(
                frame="LOCAL_NED",
                accel=enu_to_ned(tuple(a_cmd_enu)),
            )

        return GuidanceSetpoint(
            frame="LOCAL_NED",
            velocity=enu_to_ned(tuple(lead_hat * command_speed)),
            accel=enu_to_ned(tuple(a_cmd_enu)),
            yaw=los_yaw_ned(tuple(i_pos), tuple(lead_point)),
        )

    def lead_angle_deg(self, interceptor_state: dict, target_track: dict) -> float:
        if not target_track.get("detected"):
            return 0.0
        i_pos = np.asarray(interceptor_state["position"], dtype=float)
        t_pos = np.asarray(target_track["position_estimate"], dtype=float)
        t_vel = np.asarray(
            target_track.get("velocity", (0.0, 0.0, 0.0)),
            dtype=float,
        )
        t_acc = np.asarray(
            target_track.get("acceleration", (0.0, 0.0, 0.0)),
            dtype=float,
        )
        r_vec = t_pos - i_pos
        rng = float(np.linalg.norm(r_vec))
        if rng < 0.01:
            return 0.0
        command_speed = float(self.last_diagnostics.get(
            "command_speed_mps",
            self._design_speed_mps,
        ))
        if command_speed <= 1.0:
            command_speed = self._design_speed_mps
        lead_point, _ = self._lead_solution(
            i_pos,
            t_pos,
            t_vel,
            t_acc,
            command_speed,
            self._confidence(target_track),
        )
        lead_vector = lead_point - i_pos
        lead_range = float(np.linalg.norm(lead_vector))
        if lead_range < 0.01:
            return 0.0
        cos_a = float(np.clip(
            np.dot(r_vec / rng, lead_vector / lead_range),
            -1.0,
            1.0,
        ))
        return math.degrees(math.acos(cos_a))

    def time_to_intercept(self, interceptor_state: dict, target_track: dict) -> float:
        if not target_track.get("detected"):
            return float("inf")
        i_pos = np.array(interceptor_state["position"], dtype=float)
        t_pos = np.asarray(target_track["position_estimate"], dtype=float)
        t_vel = np.asarray(
            target_track.get("velocity", (0.0, 0.0, 0.0)),
            dtype=float,
        )
        t_acc = np.asarray(
            target_track.get("acceleration", (0.0, 0.0, 0.0)),
            dtype=float,
        )
        command_speed = float(self.last_diagnostics.get(
            "command_speed_mps",
            self._design_speed_mps,
        ))
        if command_speed <= 1.0:
            command_speed = self._design_speed_mps
        _, intercept_time = self._lead_solution(
            i_pos,
            t_pos,
            t_vel,
            t_acc,
            command_speed,
            self._confidence(target_track),
        )
        return intercept_time

    def predicted_intercept_point(
        self,
        interceptor_state: dict,
        target_track: dict,
    ) -> tuple[float, float, float] | None:
        """Acceleration-aware lead point at the current bounded command speed."""
        if not target_track.get("detected"):
            return None
        i_pos = np.asarray(interceptor_state["position"], dtype=float)
        t_pos = np.asarray(target_track["position_estimate"], dtype=float)
        t_vel = np.asarray(target_track.get("velocity", [0, 0, 0]), dtype=float)
        t_acc = np.asarray(
            target_track.get("acceleration", [0, 0, 0]),
            dtype=float,
        )

        diagnostic_speed = float(self.last_diagnostics.get(
            "command_speed_mps",
            self._design_speed_mps,
        ))
        if diagnostic_speed <= 1.0:
            diagnostic_speed = self._design_speed_mps
        intercept_speed = float(np.clip(
            diagnostic_speed,
            1.0,
            self._design_speed_mps,
        ))
        lead_point, _ = self._lead_solution(
            i_pos,
            t_pos,
            t_vel,
            t_acc,
            intercept_speed,
            self._confidence(target_track),
        )
        return tuple(lead_point)


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
