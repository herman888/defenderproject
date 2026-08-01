"""Micro-rocket effector model for counter-swarm area thinning.

Models a boost-sustain solid-propellant interceptor used to thin a saturation
raid before terminal quadcopter engagement. Flight phases:

1. BOOST    - constant thrust for ``burn_time``, accelerating to ~Mach 1.6
2. SUSTAIN  - unpowered coast, decelerating under drag and gravity
3. TERMINAL - true proportional navigation onto the collision triangle

Evidence status: ``design-placeholder``. Mass, thrust, burn time, drag
coefficient, and lateral authority are representative values chosen for a
plausible 80 mm airframe. None are measured. They must be replaced with
motor-test and wind-tunnel (or CFD) data before any claim rests on this model.
See ``docs-internal/PROGRAM_PLAN.md`` section 3.2.
"""

from __future__ import annotations

import math

import numpy as np

# --- Atmosphere (ISA troposphere) -------------------------------------------
_RHO_SL = 1.225             # kg/m^3, sea-level density
_T_SL = 288.15              # K, sea-level temperature
_LAPSE = 0.0065             # K/m, tropospheric lapse rate
_GAMMA_R = 401.87           # gamma * R for dry air, J/(kg K)

# --- Drag ---------------------------------------------------------------
# Piecewise Mach factor applied to the subsonic Cd0. This is an engineering
# approximation of transonic wave drag for a fin-stabilised body, not a
# measured curve: drag rises through the transonic region, peaks near M=1.2,
# then decays. Replace with measured data before quoting terminal velocity.
_MACH_DIVERGENCE = 0.8
_MACH_PEAK = 1.2
_CD_PEAK_FACTOR = 3.5       # Cd(M=1.2) / Cd(subsonic)
_CD_SUPERSONIC_DECAY = 1.2  # per unit Mach above the peak
_CD_SUPERSONIC_FLOOR = 1.8  # Cd never falls below this multiple of Cd0

_GRAVITY_ENU = np.array([0.0, 0.0, -9.81])


def air_density(altitude_m: float) -> float:
    """ISA tropospheric density. Clamped to the troposphere (0-11 km)."""
    h = min(max(float(altitude_m), 0.0), 11000.0)
    return _RHO_SL * (1.0 - _LAPSE * h / _T_SL) ** 4.2559


def speed_of_sound(altitude_m: float) -> float:
    """ISA tropospheric speed of sound."""
    h = min(max(float(altitude_m), 0.0), 11000.0)
    return math.sqrt(_GAMMA_R * (_T_SL - _LAPSE * h))


def drag_coefficient(cd0: float, mach: float) -> float:
    """Mach-corrected drag coefficient (see module docstring for provenance)."""
    if mach < _MACH_DIVERGENCE:
        return cd0
    if mach < _MACH_PEAK:
        ramp = (mach - _MACH_DIVERGENCE) / (_MACH_PEAK - _MACH_DIVERGENCE)
        return cd0 * (1.0 + (_CD_PEAK_FACTOR - 1.0) * ramp)
    decayed = _CD_PEAK_FACTOR - _CD_SUPERSONIC_DECAY * (mach - _MACH_PEAK)
    return cd0 * max(decayed, _CD_SUPERSONIC_FLOOR)


def closest_approach(rel_start: np.ndarray, rel_end: np.ndarray):
    """Minimum separation over a step, assuming linear relative motion.

    Returns ``(distance_m, fraction)`` where ``fraction`` in [0, 1] locates the
    closest approach within the step. Endpoint-only distance checks miss a fast
    interceptor entirely: at 550 m/s and dt=0.01 s the body advances 5.5 m per
    step, further than a 4 m lethal radius, so it can tunnel through the target
    without ever registering a hit.
    """
    delta = rel_end - rel_start
    denom = float(delta @ delta)
    if denom <= 1e-12:
        return float(np.linalg.norm(rel_start)), 0.0
    s = -float(rel_start @ delta) / denom
    s = min(max(s, 0.0), 1.0)
    return float(np.linalg.norm(rel_start + s * delta)), s


class MicroRocketEffector:
    """High-acceleration solid-propellant micro-rocket interceptor.

    Guidance is **true** proportional navigation: ``a = N * Vc * (Omega x u_los)``
    where ``Vc`` is closing speed and ``Omega`` the line-of-sight rate. This
    matches the convention in ``guidance/intercept.py`` so the two effectors are
    directly comparable. Commanded lateral acceleration is clamped to
    ``max_lateral_g``, since a fin-stabilised body cannot pull unlimited g.
    """

    def __init__(
        self,
        start_pos,
        target_pos,
        rocket_id: int = 0,
        *,
        mass_kg: float = 2.2,
        max_thrust_n: float = 1500.0,
        burn_time_s: float = 0.8,
        drag_coeff: float = 0.25,
        cross_section_m2: float = 0.005,   # 80 mm diameter body
        nav_constant: float = 4.0,
        max_lateral_g: float = 30.0,
        detonation_radius_m: float = 4.0,
        min_guidance_speed_mps: float = 10.0,
        unit_cost_usd: float = 1800.0,
    ):
        self.rocket_id = int(rocket_id)
        self.pos = np.array(start_pos, dtype=float)
        self.vel = np.zeros(3, dtype=float)
        self.target_pos = np.array(target_pos, dtype=float)

        self.mass = float(mass_kg)
        self.max_thrust = float(max_thrust_n)
        self.burn_time = float(burn_time_s)
        self.drag_coeff = float(drag_coeff)
        self.cross_section = float(cross_section_m2)
        self.nav_constant = float(nav_constant)
        self.max_lateral_accel = float(max_lateral_g) * 9.81
        self.detonation_radius = float(detonation_radius_m)
        self.min_guidance_speed = float(min_guidance_speed_mps)
        self.cost_dollars = float(unit_cost_usd)

        self.time_elapsed = 0.0
        self.is_active = True
        self.intercepted = False
        self.miss_distance_m = float("inf")

        direction = self.target_pos - self.pos
        norm = float(np.linalg.norm(direction))
        self.unit_dir = (
            direction / norm if norm > 1e-9 else np.array([0.0, 0.0, 1.0])
        )

    # -- guidance ---------------------------------------------------------
    def _pn_acceleration(self, r_vec, distance, target_vel, speed):
        """True PN command, clamped to the airframe's lateral authority."""
        if distance <= 0.0 or speed < self.min_guidance_speed:
            return np.zeros(3)

        v_rel = np.asarray(target_vel, dtype=float) - self.vel
        u_los = r_vec / distance
        closing_speed = -float(v_rel @ u_los)
        if closing_speed <= 0.0:
            # Opening range: PN has no solution, hold the current heading.
            return np.zeros(3)

        los_rate = np.cross(r_vec, v_rel) / (distance * distance)
        accel = self.nav_constant * closing_speed * np.cross(los_rate, u_los)

        magnitude = float(np.linalg.norm(accel))
        if magnitude > self.max_lateral_accel:
            accel *= self.max_lateral_accel / magnitude
        return accel

    # -- integration -------------------------------------------------------
    def step(self, dt, current_target_pos, target_vel=None):
        """Advance physics and guidance by ``dt`` seconds.

        Returns ``(position, intercepted)``.
        """
        if not self.is_active:
            return self.pos, self.intercepted

        dt = float(dt)
        target_vel = (
            np.zeros(3) if target_vel is None
            else np.asarray(target_vel, dtype=float)
        )
        target_start = np.asarray(current_target_pos, dtype=float)

        self.time_elapsed += dt
        self.target_pos = target_start

        speed = float(np.linalg.norm(self.vel))
        altitude = float(self.pos[2])

        thrust_force = (
            self.unit_dir * self.max_thrust
            if self.time_elapsed <= self.burn_time
            else np.zeros(3)
        )

        if speed > 0.0:
            mach = speed / speed_of_sound(altitude)
            cd = drag_coefficient(self.drag_coeff, mach)
            drag_magnitude = (
                0.5 * air_density(altitude) * speed * speed
                * cd * self.cross_section
            )
            drag_force = -drag_magnitude * (self.vel / speed)
        else:
            drag_force = np.zeros(3)

        r_vec = target_start - self.pos
        distance = float(np.linalg.norm(r_vec))
        accel_pn = self._pn_acceleration(r_vec, distance, target_vel, speed)

        total_accel = (
            (thrust_force + drag_force) / self.mass + _GRAVITY_ENU + accel_pn
        )

        # Semi-implicit Euler, then a swept-volume hit test over the step.
        pos_start = self.pos.copy()
        self.vel = self.vel + total_accel * dt
        self.pos = self.pos + self.vel * dt

        rel_start = target_start - pos_start
        rel_end = (target_start + target_vel * dt) - self.pos
        separation, _ = closest_approach(rel_start, rel_end)
        self.miss_distance_m = min(self.miss_distance_m, separation)

        if separation < self.detonation_radius:
            self.intercepted = True
            self.is_active = False
            return self.pos, self.intercepted

        new_speed = float(np.linalg.norm(self.vel))
        if new_speed > 1.0:
            self.unit_dir = self.vel / new_speed

        return self.pos, self.intercepted

    def get_state(self) -> dict:
        """Rocket state telemetry."""
        speed = float(np.linalg.norm(self.vel))
        return {
            "id": self.rocket_id,
            "pos": self.pos.tolist(),
            "vel": self.vel.tolist(),
            "speed": speed,
            "mach": speed / speed_of_sound(float(self.pos[2])),
            "time_s": self.time_elapsed,
            "active": self.is_active,
            "intercepted": self.intercepted,
            "miss_distance_m": self.miss_distance_m,
            "cost_usd": self.cost_dollars,
        }
