"""Publish the delta between the legacy detection curve and the physics model.

The legacy curve was piecewise-linear in ``range / max_range``, scaled by
``sqrt(rcs / 0.05)``. It had no radar equation behind it: no transmit power, no
antenna gain, no wavelength, no noise figure, no integration gain. Its
``false_alarm_probability`` was a free scenario parameter rather than a
consequence of the detection threshold, so P_d and P_fa were decoupled.

This script evaluates both models over the same range/RCS grid and writes the
comparison. Publishing the delta - rather than quietly swapping the model - is
the evidence that the change was principled.

    venv312\\Scripts\\python.exe scripts\\compare_detection_models.py
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from sensors.radar_model import RadarBudget, RadarDetectionModel  # noqa: E402

SCHEMA = "aegis.detection-model-comparison.v1"
_RCS_REF = 0.05  # legacy baseline RCS (Shahed-136 class)


def legacy_p_detect(range_m: float, rcs_m2: float, max_range_m: float) -> float:
    """The curve as it stood in sensors/radar.py before the physics model."""
    rcs_factor = math.sqrt(max(rcs_m2, 1e-4) / _RCS_REF)
    t_frac = range_m / max(max_range_m, 1.0)
    if t_frac <= 0.15:
        p_base = 0.88
    elif t_frac <= 0.50:
        p_base = 0.88 - (t_frac - 0.15) / 0.35 * 0.30
    else:
        p_base = 0.58 - (t_frac - 0.50) / 0.50 * 0.28
    return max(0.02, min(0.96, p_base * rcs_factor))


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--max-range", type=float, default=1500.0)
    parser.add_argument(
        "--rcs", type=float, nargs="+",
        default=[0.01, 0.05, 0.5],
        help="Target RCS values in m^2 (small quad / Shahed class / large).",
    )
    parser.add_argument("--samples", type=int, default=31)
    parser.add_argument("--output-dir", default="reports/detection")
    args = parser.parse_args(argv)

    budget = RadarBudget()
    model = RadarDetectionModel(budget, max_range_m=args.max_range)
    ranges = np.linspace(50.0, args.max_range, args.samples)

    rows = []
    for rcs in args.rcs:
        for rng in ranges:
            legacy = legacy_p_detect(float(rng), rcs, args.max_range)
            physics = model.p_detect(float(rng), rcs)
            rows.append({
                "rcs_m2": rcs,
                "range_m": round(float(rng), 1),
                "snr_db": round(float(budget.snr_db(rng, rcs)), 2),
                "p_detect_legacy": round(legacy, 4),
                "p_detect_physics": round(physics, 4),
                "delta": round(physics - legacy, 4),
            })

    out_dir = _ROOT / args.output_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    csv_path = out_dir / "detection_model_comparison.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    summary = {
        "schema": SCHEMA,
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "max_range_m": args.max_range,
        "budget": model.describe(),
        "detection_range_m": {
            f"rcs_{rcs}": {
                "pd_0.9": round(budget.detection_range_m(rcs, 0.9), 1),
                "pd_0.5": round(budget.detection_range_m(rcs, 0.5), 1),
            }
            for rcs in args.rcs
        },
        "note": (
            "The legacy curve is piecewise-linear in range/max_range with no "
            "radar equation behind it, and decouples P_d from P_fa. The "
            "physics model derives P_d from the range equation and Shnidman's "
            "approximation, validated against published reference values in "
            "tests/test_radar_model.py."
        ),
        "rows": rows,
    }
    json_path = out_dir / "detection_model_comparison.json"
    json_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    print(f"Wrote {csv_path}")
    print(f"Wrote {json_path}\n")
    print(f"{'RCS':>7} {'range':>8} {'SNR dB':>8} {'legacy':>8} {'physics':>8} {'delta':>8}")
    for rcs in args.rcs:
        for rng in (200.0, 600.0, 1000.0, args.max_range):
            legacy = legacy_p_detect(rng, rcs, args.max_range)
            physics = model.p_detect(rng, rcs)
            print(
                f"{rcs:>7.2f} {rng:>8.0f} {float(budget.snr_db(rng, rcs)):>8.1f}"
                f" {legacy:>8.3f} {physics:>8.3f} {physics - legacy:>+8.3f}"
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
