"""Verify that live dashboard captures changed with mission state."""

import json
import os
import sys

import numpy as np
from PIL import Image


def main():
    capture_dir = (
        sys.argv[1]
        if len(sys.argv) > 1
        else os.path.join("reports", "live_ui_sequence")
    )
    thresholds = (3, 8, 13)
    states = []
    images = []
    for threshold in thresholds:
        stem = os.path.join(capture_dir, f"dashboard_t{threshold:03d}")
        with open(f"{stem}.json", encoding="utf-8") as handle:
            states.append(json.load(handle))
        images.append(np.asarray(Image.open(f"{stem}.png").convert("RGB")))

    altitudes = [state["intruder_altitude_m"] for state in states]
    sample_counts = [
        len(state["intruder_altitude_history"]) for state in states
    ]
    if not (altitudes[0] > altitudes[1] > altitudes[2]):
        raise AssertionError(f"Intruder altitude did not descend: {altitudes}")
    if not (sample_counts[0] < sample_counts[1] < sample_counts[2]):
        raise AssertionError(f"History did not grow: {sample_counts}")
    if "predicted_intercept_enu_m" in states[0]:
        if states[0]["predicted_intercept_enu_m"] is not None:
            raise AssertionError("Pre-launch capture exposed a predicted intercept")
        if states[1]["predicted_intercept_enu_m"] is not None:
            raise AssertionError("Pre-launch capture exposed a predicted intercept")
        if states[2]["predicted_intercept_enu_m"] is None:
            raise AssertionError("Post-launch capture lacks a predicted intercept")

    comparisons = []
    for first, second, pair in (
        (images[0], images[1], "T+3 -> T+8"),
        (images[1], images[2], "T+8 -> T+13"),
    ):
        delta = np.abs(second.astype(np.int16) - first.astype(np.int16))
        comparisons.append({
            "pair": pair,
            "mean_absolute_pixel_delta": float(delta.mean()),
            "changed_pixel_fraction": float(np.any(delta > 4, axis=2).mean()),
        })
    if any(item["changed_pixel_fraction"] < 0.01 for item in comparisons):
        raise AssertionError(f"Dashboard frames did not visibly change: {comparisons}")

    print(json.dumps({
        "mission_times_s": [state["mission_time_s"] for state in states],
        "intruder_altitudes_m": altitudes,
        "altitude_sample_counts": sample_counts,
        "image_differences": comparisons,
    }, indent=2))


if __name__ == "__main__":
    main()
