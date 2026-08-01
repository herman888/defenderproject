"""Passive monocular optical tracking from camera bounding boxes.

Estimates target 3D kinematics from 2D detections alone, giving a radar-free
track for EW-jammed or emission-controlled operation.

**Range is the weak axis and must be treated as such.** Bearing comes from the
pinhole ray and is accurate to roughly a pixel; range comes from apparent size
via the linear pinhole relation ``Z = W_ref * f / w_px``, which assumes the
target's true width equals ``reference_width_m``. Two error sources dominate:

* *Scale error* - a target 2x wider than assumed reads 2x closer, with no
  observable signature. Bounded only by classification.
* *Quantisation* - fractional range error equals fractional width error, so a
  10 px box with +/-1 px jitter carries ~10% range noise, and it degrades as
  1/w_px with distance.

Consequently this is a **bearing-quality, range-poor** source. Fuse it with a
ranging sensor (the ground radar uplink) rather than treating its range as
authoritative; ``track()`` reports per-axis variance so the consumer can weight
it correctly.

Evidence status: ``design-placeholder``. ``reference_width_m`` and the intrinsics
are nominal until measured against the selected camera and threat set.
"""

from __future__ import annotations

import numpy as np

_MIN_BOX_WIDTH_PX = 1.0
_MIN_DT_S = 1e-3


class PassiveOpticalTracker:
    """Alpha-beta tracker over monocular bounding-box detections.

    Camera convention: **Z forward, X right, Y down** (standard pinhole).
    ``camera_ori_matrix`` must map that camera frame into world ENU. If your
    camera basis differs, convert before calling rather than adjusting here.
    """

    def __init__(
        self,
        focal_length_px: float = 800.0,
        reference_width_m: float = 0.8,
        principal_point_px=(640.0, 360.0),
        *,
        alpha: float = 0.4,
        beta: float = 0.2,
        bbox_width_sigma_px: float = 1.0,
        min_range_m: float = 2.0,
        max_range_m: float = 1500.0,
    ):
        self.focal_length = float(focal_length_px)
        self.reference_width = float(reference_width_m)
        self.cx, self.cy = (float(v) for v in principal_point_px)
        self.alpha = float(alpha)
        self.beta = float(beta)
        self.bbox_width_sigma_px = float(bbox_width_sigma_px)
        self.min_range = float(min_range_m)
        self.max_range = float(max_range_m)

        # State vector: [x, y, z, vx, vy, vz] in world ENU.
        self.state = np.zeros(6)
        self.initialized = False
        self.last_timestamp = 0.0
        self.last_range_m = float("nan")
        self.last_range_sigma_m = float("inf")

    # -- geometry ---------------------------------------------------------
    def _range_from_width(self, width_px: float):
        """Return ``(range_m, sigma_m)`` from apparent width.

        Fractional range error equals fractional width error, so
        ``sigma_range = range * (sigma_px / w_px)``.
        """
        width = max(float(width_px), _MIN_BOX_WIDTH_PX)
        raw = (self.reference_width * self.focal_length) / width
        clamped = min(max(raw, self.min_range), self.max_range)
        sigma = clamped * (self.bbox_width_sigma_px / width)
        return clamped, sigma

    def _ray_world(self, u: float, v: float, camera_ori_matrix) -> np.ndarray:
        ray_cam = np.array([
            (float(u) - self.cx) / self.focal_length,
            (float(v) - self.cy) / self.focal_length,
            1.0,
        ])
        ray_cam /= np.linalg.norm(ray_cam)
        ray_world = np.asarray(camera_ori_matrix, dtype=float) @ ray_cam
        norm = float(np.linalg.norm(ray_world))
        return ray_world / norm if norm > 1e-9 else ray_world

    # -- filtering --------------------------------------------------------
    def update_from_bbox(self, bbox, timestamp, camera_pos, camera_ori_matrix):
        """Fold one detection into the track.

        ``bbox`` is ``[x_center_px, y_center_px, width_px, height_px]``.
        Returns ``(position_enu, velocity_enu)``.
        """
        u, v, w, _h = bbox
        timestamp = float(timestamp)

        estimated_range, range_sigma = self._range_from_width(w)
        self.last_range_m = estimated_range
        self.last_range_sigma_m = range_sigma

        ray_world = self._ray_world(u, v, camera_ori_matrix)
        measurement = np.asarray(camera_pos, dtype=float) + ray_world * estimated_range

        if not self.initialized:
            self.state[:3] = measurement
            self.state[3:] = 0.0
            self.initialized = True
        else:
            dt = max(timestamp - self.last_timestamp, _MIN_DT_S)
            # Predict, then correct. Without the prediction step the residual
            # absorbs the whole inter-frame displacement, which biases position
            # low and inflates the velocity estimate without bound.
            predicted = self.state[:3] + self.state[3:] * dt
            residual = measurement - predicted
            self.state[:3] = predicted + self.alpha * residual
            self.state[3:] = self.state[3:] + (self.beta / dt) * residual

        self.last_timestamp = timestamp
        return self.state[:3].copy(), self.state[3:].copy()

    def predict(self, timestamp: float) -> np.ndarray:
        """Position extrapolated to ``timestamp`` without a measurement."""
        if not self.initialized:
            return self.state[:3].copy()
        dt = max(float(timestamp) - self.last_timestamp, 0.0)
        return self.state[:3] + self.state[3:] * dt

    # -- integration -------------------------------------------------------
    def track(self, timestamp: float | None = None) -> dict:
        """Track in the dict shape ``sensors.fusion.TrackFusion`` consumes.

        ``track_confidence`` degrades with fractional range uncertainty, so a
        small, distant, noisy box is down-weighted against a ranging sensor
        instead of competing with it on equal terms.
        """
        stamp = self.last_timestamp if timestamp is None else float(timestamp)
        if not self.initialized:
            return {"detected": False, "source": "passive_optical"}

        fractional = (
            self.last_range_sigma_m / self.last_range_m
            if self.last_range_m > 0.0 else 1.0
        )
        confidence = float(np.clip(1.0 - fractional, 0.05, 0.95))

        return {
            "detected": True,
            "source": "passive_optical",
            "position_estimate": self.state[:3].tolist(),
            "velocity": self.state[3:].tolist(),
            "measurement_time_s": stamp,
            "track_confidence": confidence,
            "range_m": self.last_range_m,
            "range_sigma_m": self.last_range_sigma_m,
            "range_observable": False,
        }
