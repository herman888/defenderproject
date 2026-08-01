"""
Pulse-Doppler ground radar with a constant-acceleration Kalman tracker.

BEFORE: Omniscient sensor at dome centre; velocity = raw finite-difference of
        noisy position (noise_std 0.3 m -> velocity spikes of 100s m/s).

AFTER:  Physical station on south dome perimeter (0, -10, 3) — 3 m mast.
        Coverage: 360 deg azimuth, 0-60 deg elevation (anti-drone cone).
        Clutter fence: rejects returns with radial velocity < 0.5 m/s.
        9-state Kalman filter ([position, velocity, acceleration]) stabilises
        the complete motion estimate used by APN guidance. Delayed tracks are
        timestamped and projected to the current sensor time before reuse.
"""

import math
import time
from collections import deque
import numpy as np

from sensors.radar_model import RadarDetectionModel

_DT        = 1.0 / 240.0   # physics timestep
_PROC_NOISE = 5.0           # continuous white-jerk spectral density, tunes Q
_ACC_ALPHA  = 0.08          # retained API setting for scenario compatibility


class KalmanTracker:
    """
    9-state constant-acceleration Kalman filter.
    State      : [x, y, z, vx, vy, vz, ax, ay, az]
    Measurement: [x, y, z]  (noisy radar position return)

    Process noise follows the discrete white-jerk model. This preserves the
    cross-covariance between position, velocity, and acceleration that a
    diagonal approximation loses, and allows a genuine predict-only coast.
    """

    def __init__(
        self,
        pos0: np.ndarray,
        meas_std: float,
        dt: float = _DT,
        process_noise: float = _PROC_NOISE,
        acceleration_alpha: float = _ACC_ALPHA,
    ):
        self.dt = dt
        self.x = np.array(
            [*pos0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
            dtype=float,
        )
        self.P = np.diag(
            [meas_std**2] * 3
            + [100.0] * 3
            + [64.0] * 3
        )

        self.F = np.eye(9)
        self.F[0:3, 3:6] = np.eye(3) * dt
        self.F[0:3, 6:9] = np.eye(3) * (0.5 * dt**2)
        self.F[3:6, 6:9] = np.eye(3) * dt

        self.H = np.zeros((3, 9))
        self.H[:, 0:3] = np.eye(3)

        q = float(process_noise)
        self.Q = np.zeros((9, 9))
        white_jerk = q * np.asarray([
            [dt**5 / 20.0, dt**4 / 8.0, dt**3 / 6.0],
            [dt**4 / 8.0, dt**3 / 3.0, dt**2 / 2.0],
            [dt**3 / 6.0, dt**2 / 2.0, dt],
        ])
        for axis in range(3):
            indices = [axis, axis + 3, axis + 6]
            self.Q[np.ix_(indices, indices)] = white_jerk
        self.R = np.eye(3) * (meas_std**2)
        self._acceleration_alpha = float(acceleration_alpha)

    def step(self, meas: np.ndarray | None):
        """Advance one filter interval, optionally applying a measurement."""
        self.x = self.F @ self.x
        self.P = self.F @ self.P @ self.F.T + self.Q
        if meas is None:
            return

        meas = np.asarray(meas, dtype=float)
        y = meas - self.H @ self.x
        S = self.H @ self.P @ self.H.T + self.R
        K = self.P @ self.H.T @ np.linalg.inv(S)
        self.x += K @ y
        # Joseph form remains symmetric and positive semi-definite under
        # long runs and very low measurement noise.
        residual_projection = np.eye(9) - K @ self.H
        self.P = (
            residual_projection @ self.P @ residual_projection.T
            + K @ self.R @ K.T
        )
        self.P = 0.5 * (self.P + self.P.T)

    @property
    def pos(self) -> tuple: return tuple(self.x[:3])
    @property
    def vel(self) -> tuple: return tuple(self.x[3:6])
    @property
    def acc(self) -> tuple: return tuple(self.x[6:9])
    @property
    def position_variance_m2(self) -> float:
        return float(np.trace(self.P[:3, :3]) / 3.0)


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
        process_noise: float = _PROC_NOISE,
        acceleration_alpha: float = _ACC_ALPHA,
        dwell_steps: int = 1,
        latency_steps: int = 0,
        false_alarm_probability: float = 0.0,
        seed: int | None = None,
        detection_model=None,
    ):
        self.station_pos      = np.array(station_pos,      dtype=float)
        self.protected_center = np.array(protected_center, dtype=float)
        self.max_range        = max_range
        self._elev_max        = math.radians(elev_max_deg)
        self._min_vel         = min_vel
        self._noise_std       = noise_std
        self._process_noise = float(process_noise)
        self._acceleration_alpha = float(acceleration_alpha)
        self._dwell_steps = int(dwell_steps)
        self._latency_steps = int(latency_steps)
        self._false_alarm_probability = float(false_alarm_probability)
        if self._dwell_steps <= 0 or self._latency_steps < 0:
            raise ValueError("radar dwell_steps must be positive and latency non-negative")
        if not 0.0 <= self._false_alarm_probability <= 1.0:
            raise ValueError("false_alarm_probability must be in [0, 1]")
        # Detection physics. Defaults to the radar range equation plus
        # Shnidman's P_d, which couples P_d to P_fa through the detection
        # threshold. The curve this replaced was piecewise-linear in
        # range/max_range with no radar equation behind it, and let P_d and
        # P_fa be set independently - physically impossible.
        self._detection_model = detection_model or RadarDetectionModel(
            max_range_m=self.max_range,
        )
        self._rng = np.random.default_rng(seed)
        self._scan_calls = 0
        self._latency_queue = deque()
        self._held_result = {"detected": False, "seq": 0}
        self._last_delivered_track: dict | None = None

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
        """Return a delivered track projected to the current radar clock."""
        if self._last_delivered_track is None:
            return None
        track = dict(self._last_delivered_track)
        measurement_time = float(track.get(
            "measurement_time_s",
            self._scan_calls * _DT,
        ))
        current_time = self._scan_calls * _DT
        age = max(0.0, current_time - measurement_time)
        position = np.asarray(track["position_estimate"], dtype=float)
        velocity = np.asarray(
            track.get("velocity", (0.0, 0.0, 0.0)),
            dtype=float,
        )
        acceleration = np.asarray(
            track.get("acceleration", (0.0, 0.0, 0.0)),
            dtype=float,
        )
        position = position + velocity * age + 0.5 * acceleration * age**2
        velocity = velocity + acceleration * age
        track["position_estimate"] = tuple(position)
        track["velocity"] = tuple(velocity)
        track["track_age_s"] = age
        track["projected_to_time_s"] = current_time
        if "position_variance_m2" in track:
            track["position_variance_m2"] = float(
                track["position_variance_m2"]
                + self._process_noise * age**2
            )
        track["coasted"] = True
        return track

    def reset_latency(self):
        """Discard delayed outputs when radar availability changes."""
        self._latency_queue.clear()
        self._held_result = {"detected": False, "seq": self._seq}
        self._last_delivered_track = None

    def _link_margin_db(self, range_m: float, target_rcs: float) -> float:
        """Relative radar link margin: 0 dB at max range for reference RCS."""
        rcs_term = 10.0 * math.log10(max(target_rcs, 1e-4) / 0.05)
        range_term = 40.0 * math.log10(
            self.max_range / max(float(range_m), 1.0)
        )
        return rcs_term + range_term

    def _measurement_time_s(self) -> float:
        """Simulation epoch of the state sampled by the current scan call."""
        return max(0.0, (self._scan_calls - 1) * _DT)

    # ------------------------------------------------------------------
    def scan(self, true_pos: tuple, target_rcs: float = 0.05) -> dict:
        """Apply dwell, false-alarm, and latency behavior around one radar frame."""
        self._scan_calls += 1
        if (self._scan_calls - 1) % self._dwell_steps:
            held = dict(self._held_result)
            held["held_for_dwell"] = True
            return held
        result = self._scan_now(true_pos, target_rcs)
        if (
            not result.get("detected")
            and self._rng.random() < self._false_alarm_probability
        ):
            bearing = self._rng.uniform(0.0, 2.0 * math.pi)
            distance = self._rng.uniform(0.1 * self.max_range, self.max_range)
            altitude = self._rng.uniform(1.0, 0.25 * self.max_range)
            position = (
                float(self.station_pos[0] + distance * math.cos(bearing)),
                float(self.station_pos[1] + distance * math.sin(bearing)),
                float(self.station_pos[2] + altitude),
            )
            result = {
                "detected": True,
                "false_alarm": True,
                "seq": result["seq"],
                "position_estimate": position,
                "velocity": (0.0, 0.0, 0.0),
                "acceleration": (0.0, 0.0, 0.0),
                "confidence": 0.05,
                "measurement_time_s": self._measurement_time_s(),
                "position_variance_m2": max(self._noise_std**2, 25.0),
            }
        self._latency_queue.append(result)
        if len(self._latency_queue) <= self._latency_steps:
            delayed = {"detected": False, "seq": result["seq"], "latency_pending": True}
        else:
            delayed = self._latency_queue.popleft()
        delayed = dict(delayed)
        delayed["latency_steps"] = self._latency_steps
        self._held_result = delayed
        if delayed.get("detected"):
            self._last_delivered_track = dict(delayed)
        return delayed

    def _scan_now(self, true_pos: tuple, target_rcs: float = 0.05) -> dict:
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
                    self._tracker.step(None)
                return {"detected": False, "seq": self._seq}

            self._miss_count = 0
            meas = t + self._rng.normal(0.0, self._noise_std, 3)
            self._tracker.step(meas)
            self.last_detection_time = time.time()
            self._track_history.append(self._tracker.pos)
            if len(self._track_history) > 200:
                self._track_history.pop(0)
            link_margin = self._link_margin_db(rng, target_rcs)
            return {
                "detected"          : True,
                "seq"               : self._seq,
                "range"             : rng,
                "bearing_deg"       : bearing_deg,
                "elevation_deg"     : math.degrees(elev),
                "snr"               : float(link_margin),
                "link_margin_db"    : float(link_margin),
                "locked"            : True,
                "position_estimate" : self._tracker.pos,
                "velocity"          : self._tracker.vel,
                "acceleration"      : self._tracker.acc,
                "measurement_time_s": self._measurement_time_s(),
                "position_variance_m2": self._tracker.position_variance_m2,
            }

        # ── SEARCHING mode — probabilistic acquisition ───────────────────
        if not in_beam:
            self._hits = max(0, self._hits - 2)
            if self._tracker:
                self._tracker.step(None)
            return {"detected": False, "seq": self._seq}

        p_det = self._detection_model.p_detect(rng, max(target_rcs, 1e-4))

        if self._rng.random() > p_det:
            self._hits = max(0, self._hits - 1)
            if self._tracker:
                self._tracker.step(None)
            return {"detected": False, "seq": self._seq}

        if not self._doppler_ok(t):
            if self._tracker:
                self._tracker.step(None)
            return {"detected": False, "seq": self._seq, "clutter_rejected": True}

        meas = t + self._rng.normal(0.0, self._noise_std, 3)

        if self._tracker is None:
            self._tracker = KalmanTracker(
                meas,
                self._noise_std,
                dt=_DT * self._dwell_steps,
                process_noise=self._process_noise,
                acceleration_alpha=self._acceleration_alpha,
            )
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

        link_margin = self._link_margin_db(rng, target_rcs)

        return {
            "detected"          : True,
            "seq"               : self._seq,
            "range"             : rng,
            "bearing_deg"       : bearing_deg,
            "elevation_deg"     : math.degrees(elev),
            "snr"               : float(link_margin),
            "link_margin_db"    : float(link_margin),
            "position_estimate" : self._tracker.pos,
            "velocity"          : self._tracker.vel,
            "acceleration"      : self._tracker.acc,
            "measurement_time_s": self._measurement_time_s(),
            "position_variance_m2": self._tracker.position_variance_m2,
        }

    def get_track_history(self) -> list:
        """Return list of (x,y,z) detected positions in detection order."""
        return list(self._track_history)

    def track_confidence(self) -> float:
        return min(1.0, self._hits / 15.0)
