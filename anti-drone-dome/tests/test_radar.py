"""Test: radar detection, field names, noise application, track history."""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from sensors.radar import RadarNode


def run_tests():
    results = []

    # Use a station centred at origin so scan positions are intuitive
    radar = RadarNode(
        station_pos      = (0.0, 0.0, 0.0),
        protected_center = (0.0, 0.0, 0.0),
        max_range        = 20.0,
        noise_std        = 0.3,
    )

    # Test 1: Radar detects drone at ~5m range, above ground (z>0.5)
    detections = [radar.scan((5, 0, 2)) for _ in range(20)]
    detect_count = sum(1 for d in detections if d.get("detected"))
    always_detected = detect_count >= 18  # ≥18/20 from 99% Pd at 5m
    results.append(("Radar detects drone at 5m (>=90%)", always_detected,
                    f"{detect_count}/20 detected"))

    # Test 2: Output has correct field names (only check first detected sample)
    detected_samples = [d for d in detections if d.get("detected")]
    if detected_samples:
        sample = detected_samples[0]
        required = {"detected", "range", "bearing_deg", "elevation_deg",
                    "position_estimate", "snr"}
        has_fields = required.issubset(set(sample.keys()))
        results.append(("Radar output has correct field names", has_fields,
                        f"keys={set(sample.keys())}"))
    else:
        results.append(("Radar output has correct field names", False, "no detections"))

    # Test 3: Noise is being applied (positions should vary)
    positions = [d["position_estimate"] for d in detected_samples]
    unique_positions = len(set(positions)) > 1
    results.append(("Noise applied (positions not identical)", unique_positions))

    # Test 4: Track history accumulates
    radar2 = RadarNode(station_pos=(0, 0, 0), max_range=20.0)
    for _ in range(20):
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
