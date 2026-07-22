"""Bounded airframe recommendations derived from aligned trajectory logs."""

from __future__ import annotations

import json
from datetime import datetime, timezone

from sim.airframe_profiles import get_airframe_profile
from validation.flight_log import compare_flight_logs


def _clamp(value: float, minimum: float = 0.8, maximum: float = 1.2) -> float:
    return max(minimum, min(maximum, float(value)))


def build_calibration_report(
    profile_id: str,
    reference_log: dict,
    simulated_log: dict,
) -> dict:
    """Recommend bounded scale changes; never mutate or validate a profile."""
    profile = get_airframe_profile(profile_id)
    comparison = compare_flight_logs(reference_log, simulated_log)
    reference_speed = comparison["reference_mean_speed_mps"]
    simulated_speed = comparison["candidate_mean_speed_mps"]
    speed_ratio = (
        reference_speed / simulated_speed
        if simulated_speed > 1e-6 else 1.0
    )
    propulsion_scale = _clamp(speed_ratio)
    drag_scale = _clamp(1.0 / max(speed_ratio, 1e-6))
    return {
        "schema": "aegis.airframe-calibration.v1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "profile_id": profile_id,
        "input_evidence_status": profile["evidence"]["status"],
        "comparison": comparison,
        "recommendations": {
            "propulsion_force_scale": propulsion_scale,
            "aerodynamic_drag_scale": drag_scale,
            "position_bias_correction_enu_m": [
                -comparison["axis_bias_m"]["east"],
                -comparison["axis_bias_m"]["north"],
                -comparison["axis_bias_m"]["up"],
            ],
        },
        "bounds": {
            "minimum_scale": 0.8,
            "maximum_scale": 1.2,
        },
        "validation_status": "candidate-only",
        "review_required": True,
        "automatic_profile_mutation": False,
        "notes": (
            "Recommendations are diagnostic starting points. Bench or flight "
            "validation is required before changing profile evidence status."
        ),
    }


def write_calibration_report(path: str, report: dict) -> None:
    with open(path, "x", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2)
        handle.write("\n")
