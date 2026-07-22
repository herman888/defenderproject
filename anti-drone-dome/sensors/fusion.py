"""Weighted radar/electro-optical track fusion for the common operating picture."""

import numpy as np


class TrackFusion:
    def __init__(self, max_camera_age_s=0.75):
        self.max_camera_age_s = float(max_camera_age_s)
        self._camera_track = None
        self._camera_time = None

    def update(
        self,
        radar_track,
        camera_track,
        radar_confidence,
        timestamp,
    ):
        if camera_track and camera_track.get("detected"):
            self._camera_track = dict(camera_track)
            self._camera_time = float(timestamp)

        candidates = []
        if radar_track and radar_track.get("detected"):
            candidates.append((
                "RADAR",
                dict(radar_track),
                max(0.15, min(1.0, float(radar_confidence))),
            ))
        if (
            self._camera_track
            and self._camera_time is not None
            and float(timestamp) - self._camera_time <= self.max_camera_age_s
        ):
            camera_confidence = float(self._camera_track.get("confidence", 0.5))
            candidates.append((
                "EO",
                self._camera_track,
                max(0.15, min(1.0, camera_confidence)),
            ))
        if not candidates:
            return None

        total_weight = sum(weight for _, _, weight in candidates)
        position = sum(
            np.asarray(track["position_estimate"], dtype=float) * weight
            for _, track, weight in candidates
        ) / total_weight
        velocity = sum(
            np.asarray(track.get("velocity", (0.0, 0.0, 0.0)), dtype=float) * weight
            for _, track, weight in candidates
        ) / total_weight
        acceleration = sum(
            np.asarray(track.get("acceleration", (0.0, 0.0, 0.0)), dtype=float) * weight
            for _, track, weight in candidates
        ) / total_weight
        sources = "+".join(source for source, _, _ in candidates)
        confidence = 1.0
        for _, _, weight in candidates:
            confidence *= 1.0 - weight
        confidence = 1.0 - confidence
        best = max(candidates, key=lambda candidate: candidate[2])[1]
        return {
            "detected": True,
            "source": sources,
            "confidence": confidence,
            "position_estimate": tuple(position),
            "velocity": tuple(velocity),
            "acceleration": tuple(acceleration),
            "range": best.get("range"),
            "bearing_deg": best.get("bearing_deg"),
            "elevation_deg": best.get("elevation_deg"),
            "timestamp": float(timestamp),
        }

    def clear_camera_track(self):
        """Invalidate cached EO data when the camera is taken offline."""
        self._camera_track = None
        self._camera_time = None
