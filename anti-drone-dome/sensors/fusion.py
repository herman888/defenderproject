"""Time-aligned, innovation-gated radar/electro-optical track fusion."""

import math
import numpy as np


class TrackFusion:
    def __init__(
        self,
        max_camera_age_s=0.75,
        innovation_gate_m=12.0,
    ):
        self.max_camera_age_s = float(max_camera_age_s)
        self.innovation_gate_m = float(innovation_gate_m)
        self._camera_track = None
        self._camera_time = None

    @staticmethod
    def _project_track(track, timestamp):
        """Project one timestamped track to the fusion epoch."""
        projected = dict(track)
        measurement_time = float(projected.get(
            "measurement_time_s",
            projected.get("timestamp", timestamp),
        ))
        state_time = float(projected.get(
            "projected_to_time_s",
            measurement_time,
        ))
        age = max(0.0, float(timestamp) - state_time)
        total_age = max(
            float(projected.get("track_age_s", state_time - measurement_time)),
            0.0,
        ) + age
        position = np.asarray(projected["position_estimate"], dtype=float)
        velocity = np.asarray(
            projected.get("velocity", (0.0, 0.0, 0.0)),
            dtype=float,
        )
        acceleration = np.asarray(
            projected.get("acceleration", (0.0, 0.0, 0.0)),
            dtype=float,
        )
        position = position + velocity * age + 0.5 * acceleration * age**2
        velocity = velocity + acceleration * age
        projected["position_estimate"] = tuple(position)
        projected["velocity"] = tuple(velocity)
        projected["track_age_s"] = total_age
        projected["projected_to_time_s"] = float(timestamp)
        return projected

    @staticmethod
    def _source_weight(source, confidence, age):
        reliability = 1.0 if source == "RADAR" else 0.65
        decay_seconds = 0.55 if source == "RADAR" else 0.35
        return (
            float(np.clip(confidence, 0.02, 1.0))
            * reliability
            * math.exp(-max(age, 0.0) / decay_seconds)
        )

    def _gate_candidates(self, candidates):
        """Reject a sensor outlier when two projected tracks disagree."""
        if len(candidates) < 2:
            return candidates, [], 0.0
        radar = next(
            (candidate for candidate in candidates if candidate[0] == "RADAR"),
            None,
        )
        camera = next(
            (candidate for candidate in candidates if candidate[0] == "EO"),
            None,
        )
        if radar is None or camera is None:
            return candidates, [], 0.0

        innovation = float(np.linalg.norm(
            np.asarray(radar[1]["position_estimate"], dtype=float)
            - np.asarray(camera[1]["position_estimate"], dtype=float)
        ))
        radar_sigma = math.sqrt(max(
            float(radar[1].get("position_variance_m2", 0.25)),
            1e-6,
        ))
        camera_sigma = math.sqrt(max(
            float(camera[1].get("position_variance_m2", 2.25)),
            1e-6,
        ))
        target_speed = max(
            np.linalg.norm(radar[1].get("velocity", (0.0, 0.0, 0.0))),
            np.linalg.norm(camera[1].get("velocity", (0.0, 0.0, 0.0))),
        )
        gate = max(
            self.innovation_gate_m,
            4.0 * math.hypot(radar_sigma, camera_sigma)
            + 0.08 * float(target_speed),
        )
        if innovation <= gate:
            return candidates, [], innovation
        best = max(candidates, key=lambda candidate: candidate[2])
        rejected = [
            candidate[0]
            for candidate in candidates
            if candidate is not best
        ]
        return [best], rejected, innovation

    def update(
        self,
        radar_track,
        camera_track,
        radar_confidence,
        timestamp,
    ):
        if camera_track and camera_track.get("detected"):
            self._camera_track = dict(camera_track)
            self._camera_time = float(camera_track.get(
                "measurement_time_s",
                timestamp,
            ))

        candidates = []
        if radar_track and radar_track.get("detected"):
            radar_candidate = self._project_track(radar_track, timestamp)
            radar_quality = float(radar_candidate.get(
                "confidence",
                radar_confidence,
            ))
            candidates.append((
                "RADAR",
                radar_candidate,
                self._source_weight(
                    "RADAR",
                    radar_quality,
                    radar_candidate["track_age_s"],
                ),
            ))
        if (
            self._camera_track
            and self._camera_time is not None
            and float(timestamp) - self._camera_time <= self.max_camera_age_s
        ):
            camera_candidate = self._project_track(
                self._camera_track,
                timestamp,
            )
            camera_confidence = float(camera_candidate.get("confidence", 0.5))
            candidates.append((
                "EO",
                camera_candidate,
                self._source_weight(
                    "EO",
                    camera_confidence,
                    camera_candidate["track_age_s"],
                ),
            ))
        if not candidates:
            return None

        candidates, rejected_sources, innovation = self._gate_candidates(
            candidates
        )
        total_weight = sum(weight for _, _, weight in candidates)
        if total_weight <= 1e-9:
            return None
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
            "measurement_time_s": float(timestamp),
            "track_age_s": 0.0,
            "innovation_m": innovation,
            "rejected_sources": rejected_sources,
            "position_variance_m2": sum(
                float(track.get("position_variance_m2", 1.0)) * weight
                for _, track, weight in candidates
            ) / total_weight,
        }

    def clear_camera_track(self):
        """Invalidate cached EO data when the camera is taken offline."""
        self._camera_track = None
        self._camera_time = None
