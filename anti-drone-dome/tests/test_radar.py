"""Test: radar detection, field names, noise application, track history."""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from sensors.radar import RadarNode


def run_tests():
    results = []
    radar = RadarNode(protected_center=(0, 0, 0), max_range=20.0, noise_std=0.3)

    # Test 1: Radar detects drone at 5m range (should detect >=90% at 95% probability)
    detections = [radar.scan((5, 0, 0)) for _ in range(20)]
    detect_count = sum(1 for d in detections if d.get("detected"))
    always_detected = detect_count >= 18  # allow up to 2 misses from 95% probability
    results.append(("Radar detects drone at 5m (>=90%)", always_detected,
                    f"{detect_count}/20 detected"))

    # Test 2: Output has correct field names
    sample = detections[0]
    required = {"detected", "range", "bearing_deg", "elevation_deg", "position_estimate", "snr"}
    has_fields = required.issubset(set(sample.keys()))
    results.append(("Radar output has correct field names", has_fields,
                    f"keys={set(sample.keys())}"))

    # Test 3: Noise is being applied (10 detections should not all be identical)
    positions = [d["position_estimate"] for d in detections if d.get("detected")]
    unique_positions = len(set(positions)) > 1
    results.append(("Noise applied (positions not identical)", unique_positions))

    # Test 4: Track history accumulates
    radar2 = RadarNode()
    for _ in range(10):
        radar2.scan((3, 0, 5))
    hist_len = len(radar2.get_track_history())
    results.append(("Track history accumulates", hist_len > 0, f"len={hist_len}"))

    print("\n=== test_radar.py ===")
    for item in results:
        name, passed = item[0], item[1]
        detail = item[2] if len(item) > 2 else ""
        status = "PASS" if passed else "FAIL"
        print(f"  [{status}] {name}" + (f" ({detail})" if detail else ""))


if __name__ == "__main__":
    run_tests()
