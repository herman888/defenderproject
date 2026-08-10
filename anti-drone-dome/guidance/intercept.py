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

from config import INTERCEPT_CONTACT_RADIUS_M, MAX_ACCEL
from guidance.setpoint import GuidanceSetpoint, enu_to_ned, los_yaw_ned

_CONTACT_RADIUS_M = INTERCEPT_CONTACT_RADIUS_M

_V_INT             = 68.0    # m/s — nominal intercept speed (below 70 m/s hard cap)
_K_LON             = 4.0     # nominal longitudinal gain
_N_PRIME_DEFAULT   = 4.0     # nominal APN navigation gain
_R_TAPER           = 25.0    # m — nominal APN/terminal blend start
_R_TERM            = 15.0    # m — nominal pure-terminal distance
_TERM_THRUST_ACCEL = 130.0   # m/s² nominal terminal acceleration

# Endgame navigation-ratio boost. PN leaves a residual line-of-sight rate that
# becomes miss distance; raise the ratio as time-to-go shrinks.
_ENDGAME_HORIZON_S = 3.0   # s - time-to-go at which the boost begins
_ENDGAME_GAIN      = 1.6   # added to N' at zero time-to-go

# Zero-effort-miss terminal law.
_ZEM_GAIN     = 3.0    # N in a = N * ZEM / t_go^2; 3 is the PN-equivalent value
_ZEM_MIN_TGO  = 0.06   # s — floor on t_go, since the command diverges as t_go->0
_ZEM_MAX_TGO  = 6.0    # s — cap, so a barely-closing geometry cannot dilute ZEM


def zero_effort_miss(r_vec, v_rel, a_target, t_go: float) -> np.ndarray:
    """Predicted relative position at intercept if neither body manoeuvres.

    ``ZEM = r + v_rel * t_go + 0.5 * a_target * t_go^2``

    Nulling this vector *is* nulling the miss distance, which is the property
    proportional navigation loses in a slow, high-line-of-sight-rate geometry.
    """
    return (
        np.asarray(r_vec, dtype=float)
        + np.asarray(v_rel, dtype=float) * t_go
        + 0.5 * np.asarray(a_target, dtype=float) * t_go * t_go
    )


def time_to_go(rng: float, closing_speed: float, command_speed: float) -> float:
    """Estimated time to intercept, clamped away from both singularities.

    When the range is opening, ``rng / closing_speed`` is negative or undefined,
    so fall back to the commanded closing capability - the interceptor is about
    to reverse the geometry, not coast forever.
    """
    if closing_speed > 0.1:
        t_go = rng / closing_speed
    else:
        t_go = rng / max(command_speed, 1.0)
    return float(min(max(t_go, _ZEM_MIN_TGO), _ZEM_MAX_TGO))


# Terminal stall detection for the "auto" law.
#
# The PD terminal controller is robust but has a stable failure mode: it can
# settle into an orbit a few metres out and hold it for the rest of the episode
# (measured: 87% of a 120 s run inside TERMINAL, range pinned at 8-9 m). ZEM
# escapes that, but is fragile when its forecast of target motion is wrong -
# it regressed every evasive and sensor-degraded scenario in the campaign.
#
# So run PD, and escalate to ZEM only once PD is *demonstrably* stuck: the
# engagement has been in the terminal region for a while and the best range
# achieved has stopped improving. That exposes ZEM's weakness only in states
# where the alternative has already failed.
_STALL_TICKS      = 40     # guidance calls without progress before escalating
_STALL_PROGRESS_M = 0.15   # improvement in best range that counts as progress


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
        terminal_law: str = "pd",
    ):
        self._N_prime = float(N_prime)
        self._design_speed_mps = float(design_speed_mps)
        self._adaptive = bool(adaptive)
        if terminal_law not in ("zem", "pd", "auto"):
            raise ValueError("terminal_law must be 'zem', 'pd', or 'auto'")
        # Measured over the full 800-episode campaign, the two laws trade -
        # neither dominates, so the incumbent stays the default:
        #
        #   scenario              PD    ZEM   delta
        #   crosswind-crossing    19%  100%    +81
        #   baseline-direct       92%  100%     +8
        #   terrain-mask-low     100%   92%     -8
        #   degraded-track        37%   28%     -9
        #   compound-edge         11%    1%    -10
        #   remote-launch         43%   31%    -12
        #   spiral-noisy          33%   15%    -18
        #   agile-pop-up          45%   20%    -25
        #   TOTAL               47.5% 48.4%   +0.9
        #
        # ZEM decisively fixes the terminal limit cycle in a clean crossing
        # geometry, and is decisively worse wherever its forecast of target
        # motion is unreliable: every regression carries an `evasive` or
        # `sensor-degraded`/`dropout`/`latency` tag. The acceleration term
        # enters as 0.5*a_target*t_go^2, so an error in a_target is amplified
        # quadratically and then chased hard by N/t_go^2.
        #
        # +0.9 points net does not justify regressing six of eight scenarios,
        # so "pd" remains the default and "zem" is selectable. The real fix is
        # a hybrid that selects on measured track quality - see
        # docs-internal/PROGRAM_PLAN.md section 2.8.
        # "auto" resolves per engagement: fly PD, and escalate to ZEM only once
        # PD is demonstrably stuck. See _terminal_is_stalled.
        self._terminal_law = terminal_law
        self._terminal_best_range = float("inf")
        self._terminal_stall_ticks = 0
        self._terminal_escalated = False
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
        # Endgame gain.
        #
        # Proportional navigation nulls line-of-sight rate asymptotically, so
        # whatever rate is left close in converts directly into miss distance:
        # a residual 0.7 deg/s at 200 m and 118 m/s closure is ~2.4 m/s of
        # lateral error, which becomes several metres of miss over the ~1.7 s
        # remaining. That is what produced the measured overshoot - closing
        # speed going negative at 19 m - and the resulting mid-air reversal.
        #
        # None of the terms above scale with proximity, and the law was
        # commanding only ~6% of available acceleration through the approach.
        # Raise the navigation ratio as time-to-go shrinks, which is standard
        # practice and spends authority that was otherwise going unused.
        time_to_go_s = rng / max(closing_speed, 1.0)
        endgame_ratio = float(np.clip(
            (_ENDGAME_HORIZON_S - time_to_go_s) / _ENDGAME_HORIZON_S,
            0.0,
            1.0,
        ))
        navigation_gain = float(np.clip(
            self._N_prime
            + 1.15 * maneuver_ratio
            + 0.85 * crossing_ratio
            + 0.35 * closing_deficit
            + _ENDGAME_GAIN * endgame_ratio,
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
        # A one-metre contact cannot be achieved if terminal guidance starts
        # only a few frames before fly-by. Begin terminal capture according to
        # the current closing rate so it can shed excess relative velocity.
        terminal_range = float(np.clip(
            25.0 + max(closing_speed, 0.0) * 0.55,
            35.0,
            85.0,
        ))
        taper_range = float(np.clip(
            terminal_range + 18.0 + max(closing_speed, 0.0) * 0.35,
            terminal_range + 18.0,
            125.0,
        ))
        return (
            navigation_gain,
            command_speed,
            longitudinal_gain,
            terminal_range,
            taper_range,
        )

    def _resolve_terminal_law(self, rng: float, taper_range: float) -> str:
        """Which terminal law to fly this call.

        For ``"auto"``: start on PD and escalate to ZEM only once PD has stopped
        making progress inside the terminal region. Escalation latches for the
        rest of the engagement - alternating laws would just produce a different
        limit cycle - and resets when the engagement does.
        """
        if self._terminal_law != "auto":
            return self._terminal_law

        outside_terminal = rng > taper_range * 1.5
        if outside_terminal:
            # New or re-opened engagement: forget the previous stall history.
            self._terminal_best_range = float("inf")
            self._terminal_stall_ticks = 0
            self._terminal_escalated = False
            return "pd"

        if rng < self._terminal_best_range - _STALL_PROGRESS_M:
            self._terminal_best_range = rng
            self._terminal_stall_ticks = 0
        else:
            self._terminal_stall_ticks += 1

        if self._terminal_stall_ticks >= _STALL_TICKS:
            self._terminal_escalated = True
        return "zem" if self._terminal_escalated else "pd"

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
        # ── Terminal controller ────────────────────────────────────────────
        #
        # The relative-position PD retained below drove range to zero but did
        # not null the *lateral* miss, and it fought itself in a slow crossing
        # geometry: the interceptor would overshoot at high speed, then orbit
        # the target at 8-9 m for the rest of the episode, spending 87% of the
        # run in TERMINAL while commanding only 10-40% of available
        # acceleration. Proportional navigation cannot recover from that state
        # either - its command scales with closing speed, so it backs off
        # exactly when the geometry is worst.
        #
        # Zero-effort-miss inverts that. It predicts where the target will be
        # relative to the interceptor at intercept and commands
        # a = N * ZEM / t_go^2, which *grows* as t_go shrinks. That is the
        # property needed to close the last metre.
        contact_error = max(rng - _CONTACT_RADIUS_M, 0.0)
        terminal_progress = float(np.clip(
            (taper_range - rng) / max(taper_range - _CONTACT_RADIUS_M, 1.0),
            0.0,
            1.0,
        ))
        active_law = self._resolve_terminal_law(rng, taper_range)

        t_go = None
        zem_magnitude = None
        desired_closing = 0.0
        if active_law == "zem":
            t_go = time_to_go(contact_error, signed_closing, command_speed)
            zem_vec = zero_effort_miss(r_vec, v_rel, a_est, t_go)
            zem_magnitude = float(np.linalg.norm(zem_vec))
            # The predicted miss is also the closing rate the law implies.
            desired_closing = contact_error / t_go
            a_terminal = _cap_accel(
                a_est + _ZEM_GAIN * zem_vec / (t_go * t_go)
            )
        else:
            desired_closing = float(np.clip(
                contact_error * 0.65,
                0.35,
                28.0,
            ))
            desired_relative_velocity = -r_hat * desired_closing
            terminal_kp = 1.35 + 2.65 * terminal_progress
            terminal_kd = 2.0 * math.sqrt(terminal_kp)
            a_terminal = _cap_accel(
                a_est
                + terminal_kp * r_vec
                + terminal_kd * (v_rel - desired_relative_velocity)
            )

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
            "terminal_desired_closing_mps": desired_closing,
            "terminal_contact_radius_m": _CONTACT_RADIUS_M,
            "terminal_law": active_law,
            "terminal_law_mode": self._terminal_law,
            "terminal_stall_ticks": self._terminal_stall_ticks,
            "lead_time_s": lead_time,
            "lead_angle_deg": lead_angle,
        }
        # ZEM-only diagnostics. Emitted as keys rather than NaN placeholders,
        # so consumers can assert every published numeric value is finite.
        if t_go is not None:
            self.last_diagnostics["terminal_time_to_go_s"] = t_go
            self.last_diagnostics["zero_effort_miss_m"] = zem_magnitude

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
