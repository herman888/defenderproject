"""Auditable mission telemetry and artifact manifests."""

from __future__ import annotations

import hashlib
import json
import os
import platform
import sys
from datetime import datetime, timezone

import numpy as np


_TELEMETRY_FIELDS = {
    "dome_status",
    "intruder_pos",
    "interceptor_pos",
    "radar_return",
    "camera_return",
    "fused_track",
    "intruder_key",
    "pattern_key",
    "environment_name",
    "visibility_m",
    "wind_mps",
    "site_name",
    "guidance_mode",
    "radar_station",
    "predicted_intercept",
    "intruder_speed",
    "interceptor_speed",
    "intruder_velocity",
    "interceptor_velocity",
    "tti",
    "track_confidence",
    "last_detection_time",
    "events",
    "mission_time",
    "sim_speed",
    "real_time_factor",
    "render_backend",
    "terrain_source",
    "compute_backend",
    "hardware_profile",
    "hardware_mode",
    "mission_run_id",
}


def _json_value(value):
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    if isinstance(value, float) and not np.isfinite(value):
        return None
    return value


def _sha256(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


class MissionRecorder:
    SCHEMA = "aegis.mission.v1"

    def __init__(
        self,
        root_dir: str,
        mission: dict,
        hardware_profile: dict,
    ):
        timestamp = datetime.now(timezone.utc)
        self.run_id = timestamp.strftime("%Y%m%dT%H%M%S_%fZ")
        self.run_dir = os.path.abspath(os.path.join(root_dir, self.run_id))
        os.makedirs(self.run_dir, exist_ok=False)
        self.telemetry_path = os.path.join(self.run_dir, "telemetry.jsonl")
        self.events_path = os.path.join(self.run_dir, "events.jsonl")
        self.manifest_path = os.path.join(self.run_dir, "manifest.json")
        self._telemetry = open(self.telemetry_path, "w", encoding="utf-8")
        self._events = open(self.events_path, "w", encoding="utf-8")
        self._sample_count = 0
        self._event_count = 0
        self._manifest = {
            "schema": self.SCHEMA,
            "run_id": self.run_id,
            "created_at_utc": timestamp.isoformat(),
            "status": "recording",
            "coordinate_frame": "LOCAL_ENU",
            "units": {
                "position": "m",
                "velocity": "m/s",
                "acceleration": "m/s^2",
                "time": "s",
            },
            "mission": _json_value(mission),
            "hardware_profile": _json_value(hardware_profile),
            "runtime": {
                "python": sys.version.split()[0],
                "platform": platform.platform(),
            },
            "artifacts": {},
        }
        self._write_manifest()

    def _write_manifest(self):
        temporary = self.manifest_path + ".tmp"
        with open(temporary, "w", encoding="utf-8") as handle:
            json.dump(self._manifest, handle, indent=2, allow_nan=False)
        os.replace(temporary, self.manifest_path)

    def record_snapshot(self, state: dict):
        normalized_state = {
            key: state[key]
            for key in _TELEMETRY_FIELDS
            if key in state
        }
        payload = {
            "schema": "aegis.telemetry-sample.v1",
            "sequence": self._sample_count,
            **_json_value(normalized_state),
        }
        self._telemetry.write(json.dumps(payload, allow_nan=False) + "\n")
        self._sample_count += 1
        for event in state.get("events", []) or []:
            if isinstance(event, dict):
                mission_time_s = event.get(
                    "time", state.get("mission_time", 0.0)
                )
                message = event.get("message", event.get("type", "EVENT"))
                event_type = event.get("type")
            else:
                mission_time_s = state.get("mission_time", 0.0)
                message = str(event)
                event_type = None
            self.record_event(
                mission_time_s,
                message,
                state.get("dome_status", "UNKNOWN"),
                event_type=event_type,
            )
        if self._sample_count % 20 == 0:
            self._telemetry.flush()

    def record_event(
        self,
        mission_time_s: float,
        message: str,
        status: str,
        event_type: str | None = None,
    ):
        payload = {
            "schema": "aegis.mission-event.v1",
            "sequence": self._event_count,
            "mission_time_s": float(mission_time_s),
            "status": status,
            "message": message,
        }
        if event_type:
            payload["type"] = event_type
        self._events.write(json.dumps(payload, allow_nan=False) + "\n")
        self._events.flush()
        self._event_count += 1

    def finalize(self, result: dict, artifacts: dict | None = None):
        if self._telemetry.closed:
            return
        self._telemetry.flush()
        self._events.flush()
        self._telemetry.close()
        self._events.close()
        artifact_paths = {
            "telemetry": self.telemetry_path,
            "events": self.events_path,
            **(artifacts or {}),
        }
        resolved_artifacts = {}
        for name, path in artifact_paths.items():
            if not path:
                continue
            absolute = os.path.abspath(path)
            if os.path.isfile(absolute):
                resolved_artifacts[name] = {
                    "path": os.path.relpath(absolute, self.run_dir),
                    "sha256": _sha256(absolute),
                    "bytes": os.path.getsize(absolute),
                }
        self._manifest.update({
            "status": "complete",
            "completed_at_utc": datetime.now(timezone.utc).isoformat(),
            "sample_count": self._sample_count,
            "event_count": self._event_count,
            "result": _json_value(result),
            "artifacts": resolved_artifacts,
        })
        self._write_manifest()

    def close_incomplete(self, reason: str):
        if self._telemetry.closed:
            return
        self._telemetry.close()
        self._events.close()
        self._manifest.update({
            "status": "incomplete",
            "completed_at_utc": datetime.now(timezone.utc).isoformat(),
            "reason": reason,
            "sample_count": self._sample_count,
            "event_count": self._event_count,
        })
        self._write_manifest()
