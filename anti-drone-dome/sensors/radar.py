"""
Pulse-Doppler ground radar with 6-state Kalman tracker.

BEFORE: Omniscient sensor at dome centre; velocity = raw finite-difference of
        noisy position (noise_std 0.3 m -> velocity spikes of 100s m/s).

AFTER:  Physical station on south dome perimeter (0, -10, 3) — 3 m mast.
        Coverage: 360 deg azimuth, 0-60 deg elevation (anti-drone cone).
        Clutter fence: rejects returns with radial velocity < 0.5 m/s.
        6-state Kalman filter ([x,y,z,vx,vy,vz]) stabilises position and
        velocity. LP-filtered velocity derivative gives smooth acceleration
        estimate for APN guidance. Position noise 0.15 m (vs old 0.30 m).
"""

import math
import time
import random
import numpy as np

_DT        = 1.0 / 240.0   # physics timestep
_PROC_NOISE = 5.0           # expected target accel magnitude (m/s^2), tunes Q
_ACC_ALPHA  = 0.08          # LP weight for accel estimate (lower = smoother)


class KalmanTracker:
    """
    6-state constant-velocity Kalman filter.
    State      : [x, y, z, vx, vy, vz]
    Measurement: [x, y, z]  (noisy radar position return)
    Acceleration: LP-filtered derivative of Kalman velocity output.
    """

    def __init__(self, pos0: np.ndarray, meas_std: float, dt: float = _DT):
        self.dt = dt
        self.x  = np.array([*pos0, 0.0, 0.0, 0.0], dtype=float)
        self.P  = np.diag([meas_std**2]*3 + [10.0]*3)

        self.F      = np.eye(6)
        self.F[0,3] = self.F[1,4] = self.F[2,5] = dt

        self.H      = np.zeros((3, 6))
        self.H[0,0] = self.H[1,1] = self.H[2,2] = 1.0

        q      = _PROC_NOISE
        self.Q = np.diag([0.5*q*dt**2]*3 + [q*dt]*3)
        self.R = np.eye(3) * (meas_std**2)

        self._prev_vel = np.zeros(3)
        self._acc      = np.zeros(3)

    def step(self, meas: np.ndarray):
        # Predict
        self.x = self.F @ self.x
        self.P = self.F @ self.P @ self.F.T + self.Q
        # Update
        y = meas - self.H @ self.x
        S = self.H @ self.P @ self.H.T + self.R
        K = self.P @ self.H.T @ np.linalg.inv(S)
        self.x += K @ y
        self.P  = (np.eye(6) - K @ self.H) @ self.P
        # LP-filtered acceleration
        vel           = self.x[3:6]
        raw_acc       = (vel - self._prev_vel) / self.dt
        self._acc     = _ACC_ALPHA * raw_acc + (1.0 - _ACC_ALPHA) * self._acc
        self._prev_vel = vel.copy()

    @property
    def pos(self) -> tuple: return tuple(self.x[:3])
    @property
    def vel(self) -> tuple: return tuple(self.x[3:6])
    @property
    def acc(self) -> tuple: return tuple(self._acc)


class RadarNode:
    """
    Pulse-Doppler radar.

    Parameters
    ----------
    station_pos    : antenna (x,y,z) — default south perimeter 3 m mast
    protected_center : dome centre (reference for bearing prints)
    max_range      : instrumented range (m)
    elev_max_deg   : upper elevation limit  (60 deg anti-drone cone)
    min_vel        : clutter fence — min detectable radial velocity (m/s)
    noise_std      : 1-sigma position measurement noise (m)
    """

    def __init__(
        self,
        station_pos      = (0.0, -10.0, 3.0),
        protected_center = (0.0,   0.0, 0.0),
        max_range: float   = 25.0,
        elev_max_deg: float = 60.0,
        min_vel: float     = 0.5,
        noise_std: float   = 0.15,
    ):
        self.station_pos      = np.array(station_pos,      dtype=float)
        self.protected_center = np.array(protected_center, dtype=float)
        self.max_range        = max_range
        self._elev_max        = math.radians(elev_max_deg)
        self._min_vel         = min_vel
        self._noise_std       = noise_std

        self._tracker: KalmanTracker | None = None
        self._hits       = 0
        self._seq        = 0
        self._first      = True
        self._locked     = False   # True once track is confirmed — skips probabilistic gate
        self._miss_count = 0       # consecutive misses while locked
        self.last_detection_time: float | None = None
        self._track_history: list = []   # list of (x,y,z) detected positions

    # ------------------------------------------------------------------
    def _in_beam(self, t: np.ndarray) -> tuple[bool, float, float, float]:
        """Return (in_beam, range_m, elevation_rad, bearing_deg)."""
        delta = t - self.station_pos
        rng   = float(np.linalg.norm(delta))
        if rng < 0.1 or rng > self.max_range:
            return False, rng, 0.0, 0.0

        horiz   = math.sqrt(delta[0]**2 + delta[1]**2)
        elev    = math.atan2(delta[2], horiz)
        bearing = math.degrees(math.atan2(delta[1], delta[0])) % 360.0

        if elev < 0.0 or elev > self._elev_max:
            return False, rng, elev, bearing   # outside elevation cone

        if t[2] < 0.5:                         # ground-hugging blind spot
            return False, rng, elev, bearing

        return True, rng, elev, bearing

    def _doppler_ok(self, t: np.ndarray) -> bool:
        """Radial velocity must clear the clutter fence.
        Skip gate for first 8 hits so Kalman velocity estimate can converge."""
        if self._tracker is None or self._hits < 8:
            return True
        vel = np.array(self._tracker.vel)
        u   = (t - self.station_pos)
        u  /= (np.linalg.norm(u) + 1e-9)
        return abs(float(np.dot(vel, u))) >= self._min_vel

    def get_last_track(self) -> dict | None:
        """Return last Kalman state for guidance coasting when radar loses lock."""
        if self._tracker is None:
            return None
        return {
            "detected"          : True,   # treat as valid for guidance
            "coasted"           : True,
            "position_estimate" : self._tracker.pos,
            "velocity"          : self._tracker.vel,
            "acceleration"      : self._tracker.acc,
        }

    # ------------------------------------------------------------------
    def scan(self, true_pos: tuple, target_rcs: float = 0.05) -> dict:
        """
        target_rcs : radar cross-section of the target (m²).
          Shahed-136  ≈ 0.05  (composite body, some metal engine)
          Consumer quad ≈ 0.003  (small plastic frame)
          FPV attack   ≈ 0.001  (carbon fibre, near-zero metal)
        Detection probability scales as sqrt(rcs / rcs_ref) — Swerling-I model
        where SNR ∝ RCS and P_d ∝ SNR^0.5 in the detection threshold regime.
        """
        """
        One radar frame.

        SEARCHING mode: probabilistic Swerling-I detection + Doppler gate.
        LOCKED mode   : once hits >= 15, skip probabilistic gate — just update
                        Kalman every frame (like a real tracker in lock).
                        Loses lock after 30 consecutive beam misses.
        """
        self._seq += 1
        t = np.array(true_pos, dtype=float)

        in_beam, rng, elev, bearing_deg = self._in_beam(t)

        # ── LOCKED track — just update Kalman, no probability roll ──────
        if self._locked:
            if not in_beam:
                self._miss_count += 1
                if self._miss_count > 30:         # lost track
                    self._locked     = False
                    self._hits       = 0
                    self._miss_count = 0
                    print("RADAR: Track lost")
                # Return coasted prediction while beam is blocked
                if self._tracker:
                    self._tracker.step(np.array(self._tracker.pos))  # coast
                return {"detected": False, "seq": self._seq}

            self._miss_count = 0
            meas = t + np.random.normal(0.0, self._noise_std, 3)
            self._tracker.step(meas)
            self.last_detection_time = time.time()
            self._track_history.append(self._tracker.pos)
            if len(self._track_history) > 200:
                self._track_history.pop(0)
            snr = 30.0 - 40.0 * math.log10(max(rng, 1.0) / 5.0)
            return {
                "detected"          : True,
                "seq"               : self._seq,
                "range"             : rng,
                "bearing_deg"       : bearing_deg,
                "elevation_deg"     : math.degrees(elev),
                "snr"               : float(snr),
                "locked"            : True,
                "position_estimate" : self._tracker.pos,
                "velocity"          : self._tracker.vel,
                "acceleration"      : self._tracker.acc,
            }

        # ── SEARCHING mode — probabilistic acquisition ───────────────────
        if not in_beam:
            self._hits = max(0, self._hits - 2)
            return {"detected": False, "seq": self._seq}

        # Range-normalised detection curve (Swerling-I, scaled by target RCS)
        _RCS_REF = 0.05   # baseline RCS (Shahed-136)
        rcs_factor = math.sqrt(max(target_rcs, 1e-4) / _RCS_REF)  # ≤1 for small targets

        t_frac = rng / max(self.max_range, 1.0)
        if t_frac <= 0.15:
            p_base = 0.88
        elif t_frac <= 0.50:
            p_base = 0.88 - (t_frac - 0.15) / 0.35 * 0.30   # 0.88 → 0.58
        else:
            p_base = 0.58 - (t_frac - 0.50) / 0.50 * 0.28   # 0.58 → 0.30

        p_det = max(0.02, min(0.96, p_base * rcs_factor))

        if random.random() > p_det:
            self._hits = max(0, self._hits - 1)
            return {"detected": False, "seq": self._seq}

        if not self._doppler_ok(t):
            return {"detected": False, "seq": self._seq, "clutter_rejected": True}

        meas = t + np.random.normal(0.0, self._noise_std, 3)

        if self._tracker is None:
            self._tracker = KalmanTracker(meas, self._noise_std)
            if self._first:
                print(f"RADAR: Track acquired — range {rng:.1f} m  "
                      f"bearing {bearing_deg:.1f} deg  elev {math.degrees(elev):.1f} deg")
                self._first = False
        else:
            self._tracker.step(meas)

        self._hits = min(self._hits + 1, 30)
        self.last_detection_time = time.time()
        self._track_history.append(self._tracker.pos)
        if len(self._track_history) > 200:
            self._track_history.pop(0)

        # Promote to locked track once confidence is high
        if self._hits >= 15 and not self._locked:
            self._locked = True
            print("RADAR: Track LOCKED")

        snr = 30.0 - 40.0 * math.log10(max(rng, 1.0) / 5.0)

        return {
            "detected"          : True,
            "seq"               : self._seq,
            "range"             : rng,
            "bearing_deg"       : bearing_deg,
            "elevation_deg"     : math.degrees(elev),
            "snr"               : float(snr),
            "position_estimate" : self._tracker.pos,
            "velocity"          : self._tracker.vel,
            "acceleration"      : self._tracker.acc,
        }

    def get_track_history(self) -> list:
        """Return list of (x,y,z) detected positions in detection order."""
        return list(self._track_history)

    def track_confidence(self) -> float:
        return min(1.0, self._hits / 15.0)
