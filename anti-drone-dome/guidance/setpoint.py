"""
GuidanceSetpoint and frame conversion helpers.

A GuidanceSetpoint is the command output from guidance laws — the same
shape ArduPilot's SET_POSITION_TARGET_LOCAL_NED accepts. Any field set
to None is ignored, which is the dataclass-friendly equivalent of
setting the corresponding IGNORE bit in MAVLink's type_mask.

Stage A: consumed by the placeholder FC inside sim/drone.py:Drone.
Stage B: forwarded to ArduPilot SITL via comms/datalink.py's
         VehicleLink as SET_POSITION_TARGET_LOCAL_NED. Guidance code
         does not change between stages.

Frame convention
────────────────
Setpoints are always in LOCAL_NED:  x = North, y = East, z = Down.
Position is metres, velocity m/s, acceleration m/s², yaw rad
(0 = north, clockwise positive looking down), yaw_rate rad/s.

PyBullet's world frame is ENU (x = East, y = North, z = Up). The
``enu_to_ned`` / ``ned_to_enu`` helpers below are the single boundary
where the two frames meet — never mix them in guidance or FC code.
"""

from dataclasses import dataclass, field
from typing import Optional, Tuple

import math

Vec3 = Tuple[float, float, float]


# ── Setpoint dataclass ──────────────────────────────────────────────
@dataclass(frozen=True)
class GuidanceSetpoint:
    frame:    str                 = "LOCAL_NED"
    position: Optional[Vec3]      = None   # (n, e, d) metres
    velocity: Optional[Vec3]      = None   # (vn, ve, vd) m/s
    accel:    Optional[Vec3]      = None   # (an, ae, ad) m/s²
    yaw:      Optional[float]     = None   # rad, NED  (0 = north, CW positive)
    yaw_rate: Optional[float]     = None   # rad/s

    @property
    def is_empty(self) -> bool:
        """True when nothing is commanded — the caller should choose a fallback
        (e.g. position-hold). Equivalent to a MAVLink message with every
        IGNORE bit set."""
        return (self.position is None and self.velocity is None
                and self.accel is None and self.yaw is None
                and self.yaw_rate is None)


# ── Frame conversion ────────────────────────────────────────────────
def enu_to_ned(v_enu: Vec3) -> Vec3:
    """(east, north, up) → (north, east, down)."""
    e, n, u = v_enu
    return (float(n), float(e), float(-u))


def ned_to_enu(v_ned: Vec3) -> Vec3:
    """(north, east, down) → (east, north, up)."""
    n, e, d = v_ned
    return (float(e), float(n), float(-d))


def yaw_enu_to_ned(yaw_enu_rad: float) -> float:
    """ENU yaw (CCW from +east, math convention) → NED yaw (CW from +north).

    Both wrap into (-π, π].
    """
    y = math.pi / 2.0 - yaw_enu_rad
    # Wrap to (-π, π]
    while y > math.pi:
        y -= 2.0 * math.pi
    while y <= -math.pi:
        y += 2.0 * math.pi
    return float(y)


def los_yaw_ned(from_pos_enu: Vec3, to_pos_enu: Vec3) -> float:
    """NED yaw of the line-of-sight from one ENU position to another.

    Returns the angle measured from +north, clockwise positive looking
    down, in (-π, π]. Returns 0.0 if the two points are co-located.
    """
    de = to_pos_enu[0] - from_pos_enu[0]   # x_enu = east
    dn = to_pos_enu[1] - from_pos_enu[1]   # y_enu = north
    if abs(de) < 1e-9 and abs(dn) < 1e-9:
        return 0.0
    return float(math.atan2(de, dn))
