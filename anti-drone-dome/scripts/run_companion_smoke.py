"""Exercise the Pi companion perception contract without physical hardware."""

from __future__ import annotations

import argparse
import json
import os
import platform
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from integration.companion_link import (
    build_perception_packet,
    encode_perception_packet,
)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--frames", type=int, default=1000)
    parser.add_argument("--width", type=int, default=1280)
    parser.add_argument("--height", type=int, default=720)
    parser.add_argument("--output")
    args = parser.parse_args()
    if args.frames <= 0:
        parser.error("--frames must be positive")

    started = time.perf_counter()
    total_bytes = 0
    for sequence in range(args.frames):
        packet = build_perception_packet(
            sequence,
            time.monotonic_ns(),
            "camera_optical",
            (args.width, args.height),
            [{
                "class_id": 0,
                "label": "drone",
                "confidence": 0.82,
                "bbox_xyxy": [420.0, 210.0, 520.0, 300.0],
            }],
            model_id="smoke-test",
        )
        total_bytes += len(encode_perception_packet(packet))
    elapsed = time.perf_counter() - started
    report = {
        "schema": "aegis.companion-smoke.v1",
        "platform": platform.platform(),
        "machine": platform.machine(),
        "frames": args.frames,
        "elapsed_s": elapsed,
        "serialization_rate_hz": args.frames / elapsed,
        "mean_packet_bytes": total_bytes / args.frames,
        "actuation_enabled": False,
    }
    rendered = json.dumps(report, indent=2)
    print(rendered)
    if args.output:
        output = os.path.abspath(args.output)
        os.makedirs(os.path.dirname(output), exist_ok=True)
        with open(output, "w", encoding="utf-8") as handle:
            handle.write(rendered + "\n")


if __name__ == "__main__":
    main()
