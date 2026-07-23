"""Realistic flight-envelope limits: turn-g, climb rate, and minimum airspeed.

Pure functions shared by the point-mass swarm runner (and available to the
PyBullet flight model). They convert an idealised acceleration command into one a
real airframe could actually fly:

* **Lateral (turn) acceleration** is capped to a load-factor (g) limit, which
  gives a finite turn radius ``r = v^2 / a_lat`` instead of instantaneous
  direction reversal.
* **Vertical rate** is bounded by climb/descent limits.
* **Fixed-wing** vehicles cannot decelerate below their minimum airspeed — they
  bank to turn; they do not stop, hover, or reverse in place.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

_G = 9.80665


@dataclass(frozen=True)
class FlightEnvelope:
    max_lateral_accel_g: float = 6.0
    max_climb_rate_mps: float = 10.0
    max_descent_rate_mps: float = 10.0
    min_airspeed_mps: float = 0.0
    fixed_wing: bool = False

    @property
    def max_lateral_accel_mps2(self) -> float:
        return self.max_lateral_accel_g * _G

    @classmethod
    def from_profile(cls, profile: dict) -> "FlightEnvelope":
        env = profile.get("flight_envelope", {}) if profile else {}
        return cls(
            max_lateral_accel_g=float(env.get("max_lateral_accel_g", 6.0)),
            max_climb_rate_mps=float(env.get("max_climb_rate_mps", 10.0)),
            max_descent_rate_mps=float(env.get("max_descent_rate_mps", 10.0)),
            min_airspeed_mps=float(env.get("min_airspeed_mps", 0.0)),
            fixed_wing=bool(env.get("fixed_wing", False)),
        )


def limit_acceleration(velocity, accel_cmd, envelope: FlightEnvelope, dt: float):
    """Return an acceleration a real airframe could fly during ``dt``."""
    velocity = np.asarray(velocity, dtype=float)
    accel = np.asarray(accel_cmd, dtype=float).astype(float).copy()

    # --- lateral (turn) g-limit about the horizontal velocity direction ---
    horiz = np.array([velocity[0], velocity[1], 0.0])
    horiz_speed = float(np.linalg.norm(horiz))
    if horiz_speed > 1e-3:
        fwd = horiz / horiz_speed
        a_h = np.array([accel[0], accel[1], 0.0])
        a_long_scalar = float(np.dot(a_h, fwd))
        a_long = a_long_scalar * fwd
        a_lat = a_h - a_long
        lat_mag = float(np.linalg.norm(a_lat))
        max_lat = envelope.max_lateral_accel_mps2
        if lat_mag > max_lat:
            a_lat *= max_lat / lat_mag

        # Fixed-wing minimum airspeed: cap the deceleration so horizontal speed
        # never falls below the floor (bank-to-turn, no stop/reverse).
        if envelope.fixed_wing and envelope.min_airspeed_mps > 0.0:
            projected = horiz_speed + a_long_scalar * dt
            if projected < envelope.min_airspeed_mps:
                allowed = (envelope.min_airspeed_mps - horiz_speed) / dt
                a_long = allowed * fwd
        accel[0] = a_long[0] + a_lat[0]
        accel[1] = a_long[1] + a_lat[1]

    # --- vertical climb / descent rate limit -----------------------------
    vz = float(velocity[2])
    vz_next = vz + accel[2] * dt
    if vz_next > envelope.max_climb_rate_mps:
        accel[2] = (envelope.max_climb_rate_mps - vz) / dt
    elif vz_next < -envelope.max_descent_rate_mps:
        accel[2] = (-envelope.max_descent_rate_mps - vz) / dt

    return accel
