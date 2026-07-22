"""Compare real and simulated trajectories and emit bounded recommendations."""

from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from validation.flight_log import load_flight_log  # noqa: E402
from validation.model_calibration import (  # noqa: E402
    build_calibration_report,
    write_calibration_report,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", required=True, help="Airframe profile ID")
    parser.add_argument("--reference", required=True, help="Measured flight CSV")
    parser.add_argument("--simulation", required=True, help="Simulated flight CSV")
    parser.add_argument("--output", required=True, help="New report JSON path")
    parser.add_argument("--reference-frame", choices=("ENU", "NED"), default="ENU")
    parser.add_argument("--simulation-frame", choices=("ENU", "NED"), default="ENU")
    args = parser.parse_args()
    try:
        report = build_calibration_report(
            args.profile,
            load_flight_log(args.reference, frame=args.reference_frame),
            load_flight_log(args.simulation, frame=args.simulation_frame),
        )
        write_calibration_report(args.output, report)
    except (OSError, ValueError, KeyError) as exc:
        parser.error(str(exc))
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
