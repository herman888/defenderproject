"""Flight-log loading, frame conversion, time alignment, and error metrics."""

from __future__ import annotations

import csv
import math

import numpy as np


_ALIASES = {
    "time_s": ("time_s", "time", "t", "timestamp_s"),
    "x_m": ("x_m", "x", "east_m", "e_m", "north_m", "n_m"),
    "y_m": ("y_m", "y", "north_m", "n_m", "east_m", "e_m"),
    "z_m": ("z_m", "z", "up_m", "u_m", "down_m", "d_m", "altitude_m"),
}


def _column(
    fieldnames: list[str],
    canonical: str,
    aliases: tuple[str, ...] | None = None,
) -> str:
    lower_to_actual = {name.lower(): name for name in fieldnames}
    accepted = aliases or _ALIASES[canonical]
    for alias in accepted:
        if alias in lower_to_actual:
            return lower_to_actual[alias]
    raise ValueError(
        f"flight log requires {canonical}; accepted aliases: "
        f"{', '.join(accepted)}"
    )


def load_flight_log(path: str, frame: str = "ENU") -> dict:
    frame = frame.upper()
    if frame not in {"ENU", "NED"}:
        raise ValueError("flight-log frame must be ENU or NED")
    with open(path, newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames:
            raise ValueError("flight log has no header")
        horizontal_aliases = (
            {
                "x_m": ("x_m", "x", "north_m", "n_m", "east_m", "e_m"),
                "y_m": ("y_m", "y", "east_m", "e_m", "north_m", "n_m"),
            }
            if frame == "NED"
            else {
                "x_m": ("x_m", "x", "east_m", "e_m", "north_m", "n_m"),
                "y_m": ("y_m", "y", "north_m", "n_m", "east_m", "e_m"),
            }
        )
        columns = {
            "time_s": _column(reader.fieldnames, "time_s"),
            "x_m": _column(
                reader.fieldnames, "x_m", horizontal_aliases["x_m"]
            ),
            "y_m": _column(
                reader.fieldnames, "y_m", horizontal_aliases["y_m"]
            ),
            "z_m": _column(reader.fieldnames, "z_m"),
        }
        rows = list(reader)
    if len(rows) < 2:
        raise ValueError("flight log requires at least two samples")
    time_s = np.asarray(
        [float(row[columns["time_s"]]) for row in rows],
        dtype=float,
    )
    position = np.asarray([
        [
            float(row[columns["x_m"]]),
            float(row[columns["y_m"]]),
            float(row[columns["z_m"]]),
        ]
        for row in rows
    ], dtype=float)
    if not np.all(np.isfinite(time_s)) or not np.all(np.isfinite(position)):
        raise ValueError("flight log contains non-finite values")
    if np.any(np.diff(time_s) <= 0.0):
        raise ValueError("flight-log timestamps must increase strictly")
    if frame == "NED":
        position = position[:, [1, 0, 2]]
        position[:, 2] *= -1.0
    return {
        "time_s": time_s - time_s[0],
        "position_enu_m": position,
        "sample_count": len(rows),
        "source_frame": frame,
    }


def _estimate_time_offset(reference: dict, candidate: dict, max_offset_s: float):
    offsets = np.linspace(-max_offset_s, max_offset_s, 101)
    reference_time = reference["time_s"]
    reference_position = reference["position_enu_m"]
    candidate_time = candidate["time_s"]
    candidate_position = candidate["position_enu_m"]
    best_offset = 0.0
    best_rmse = float("inf")
    for offset in offsets:
        shifted = candidate_time + offset
        mask = (reference_time >= shifted[0]) & (reference_time <= shifted[-1])
        if np.count_nonzero(mask) < 2:
            continue
        interpolated = np.column_stack([
            np.interp(reference_time[mask], shifted, candidate_position[:, axis])
            for axis in range(3)
        ])
        error = reference_position[mask] - interpolated
        rmse = math.sqrt(float(np.mean(np.sum(error * error, axis=1))))
        if rmse < best_rmse:
            best_rmse = rmse
            best_offset = float(offset)
    return best_offset


def compare_flight_logs(
    reference: dict,
    candidate: dict,
    max_offset_s: float = 1.0,
) -> dict:
    offset = _estimate_time_offset(reference, candidate, max_offset_s)
    reference_time = reference["time_s"]
    shifted_candidate_time = candidate["time_s"] + offset
    mask = (
        (reference_time >= shifted_candidate_time[0])
        & (reference_time <= shifted_candidate_time[-1])
    )
    if np.count_nonzero(mask) < 2:
        raise ValueError("flight logs do not overlap after alignment")
    aligned_time = reference_time[mask]
    interpolated = np.column_stack([
        np.interp(
            aligned_time,
            shifted_candidate_time,
            candidate["position_enu_m"][:, axis],
        )
        for axis in range(3)
    ])
    vector_error = interpolated - reference["position_enu_m"][mask]
    distance_error = np.linalg.norm(vector_error, axis=1)
    axis_rmse = np.sqrt(np.mean(vector_error * vector_error, axis=0))
    return {
        "schema": "aegis.flight-log-comparison.v1",
        "aligned_sample_count": int(len(aligned_time)),
        "overlap_duration_s": float(aligned_time[-1] - aligned_time[0]),
        "estimated_candidate_time_offset_s": offset,
        "trajectory_rmse_m": math.sqrt(float(np.mean(distance_error ** 2))),
        "trajectory_p95_m": float(np.percentile(distance_error, 95)),
        "trajectory_max_m": float(np.max(distance_error)),
        "axis_rmse_m": {
            "east": float(axis_rmse[0]),
            "north": float(axis_rmse[1]),
            "up": float(axis_rmse[2]),
        },
    }
