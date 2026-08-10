"""Emit the first edge-perception evidence-gate metric template.

This intentionally performs no inference.  It makes absent measurements visible
and gives camera/Hailo runs one stable artifact shape to fill later.
"""

from __future__ import annotations

import argparse
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path


SCHEMA = "larp.edge-pipeline-measurement.v1"
NOT_MEASURED = "NOT MEASURED"
METRICS = (
    "capture_to_detection_latency_ms",
    "detection_to_track_latency_ms",
    "end_to_end_fps",
    "npu_utilization_percent",
    "board_temperature_c",
    "power_draw_w",
)


def git_commit(root: Path) -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=root, text=True
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return "NOT AVAILABLE"


def build_stub(root: Path) -> dict:
    return {
        "schema": SCHEMA,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "git_commit": git_commit(root),
        "measurement_status": NOT_MEASURED,
        "metrics": {name: NOT_MEASURED for name in METRICS},
        "note": (
            "Template only. Populate only from a timestamped target-device run "
            "with the exact camera, model artifact, Hailo runtime, and power/thermal setup."
        ),
    }


def summary_table(record: dict) -> str:
    rows = ["| Metric | Value |", "| --- | --- |"]
    rows.extend(f"| {name} | {value} |" for name, value in record["metrics"].items())
    return "\n".join(rows)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        default="reports/edge_pipeline_measurement.json",
        help="Versioned JSON artifact path.",
    )
    args = parser.parse_args()
    root = Path(__file__).resolve().parent.parent
    record = build_stub(root)
    output = Path(args.output)
    if not output.is_absolute():
        output = root / output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    print(summary_table(record))
    print(f"\nWrote {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
