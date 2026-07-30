"""Validate continuous authoritative motion in a tactical JSONL recording."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path


def _distance(first, second) -> float:
    return math.sqrt(sum(
        (float(second[index]) - float(first[index])) ** 2
        for index in range(3)
    ))


def summarize_motion(path: Path, movement_threshold_m: float = 0.01) -> dict:
    packets = [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    if len(packets) < 2:
        raise ValueError("recording must contain at least two packets")

    intruder_intervals = 0
    intruder_moving = 0
    engagement_intervals = 0
    interceptor_moving = 0
    both_moving = 0
    for previous, current in zip(packets, packets[1:]):
        previous_tracks = previous["tracks"]
        current_tracks = current["tracks"]
        intruder_intervals += 1
        intruder_delta = _distance(
            previous_tracks["intruder"]["position_enu_m"],
            current_tracks["intruder"]["position_enu_m"],
        )
        intruder_is_moving = intruder_delta > movement_threshold_m
        intruder_moving += int(intruder_is_moving)

        previous_interceptor = previous_tracks.get("interceptor")
        current_interceptor = current_tracks.get("interceptor")
        if previous_interceptor is None or current_interceptor is None:
            continue
        engagement_intervals += 1
        interceptor_delta = _distance(
            previous_interceptor["position_enu_m"],
            current_interceptor["position_enu_m"],
        )
        interceptor_is_moving = interceptor_delta > movement_threshold_m
        interceptor_moving += int(interceptor_is_moving)
        both_moving += int(intruder_is_moving and interceptor_is_moving)

    return {
        "packets": len(packets),
        "intruder_intervals": intruder_intervals,
        "intruder_moving_intervals": intruder_moving,
        "engagement_intervals": engagement_intervals,
        "interceptor_moving_intervals": interceptor_moving,
        "both_moving_intervals": both_moving,
        "guidance_modes": sorted({
            packet.get("simulation", {}).get("guidance_mode", "UNKNOWN")
            for packet in packets
        }),
        "last_status": packets[-1]["status"],
    }


def motion_is_valid(summary: dict, minimum_ratio: float = 0.95) -> bool:
    engagement_intervals = summary["engagement_intervals"]
    return (
        summary["intruder_intervals"] > 0
        and engagement_intervals > 0
        and summary["intruder_moving_intervals"]
        / summary["intruder_intervals"] >= minimum_ratio
        and summary["interceptor_moving_intervals"]
        / engagement_intervals >= minimum_ratio
        and summary["both_moving_intervals"]
        / engagement_intervals >= minimum_ratio
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("recording", type=Path)
    parser.add_argument("--minimum-ratio", type=float, default=0.95)
    args = parser.parse_args()
    summary = summarize_motion(args.recording)
    print(json.dumps(summary, indent=2))
    if not motion_is_valid(summary, args.minimum_ratio):
        print("FAILED: tactical tracks were not continuously moving")
        return 1
    print("PASSED: both tracks move continuously during engagement")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
