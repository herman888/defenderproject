"""Run repeatable SIL/HIL readiness validation and generate evidence reports."""

import argparse
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from hardware.profile import load_hardware_profile
from validation.workbench import build_report, write_report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--profile",
        default="hardware_profiles/reference_sil.json",
        help="Versioned hardware profile JSON",
    )
    parser.add_argument("--episodes", type=int, default=20)
    parser.add_argument("--seed", type=int, default=70000)
    parser.add_argument("--reference-log")
    parser.add_argument("--candidate-log")
    parser.add_argument("--reference-frame", choices=("ENU", "NED"), default="ENU")
    parser.add_argument("--candidate-frame", choices=("ENU", "NED"), default="ENU")
    parser.add_argument(
        "--output",
        default="reports/hardware_validation",
        help="Output path without extension",
    )
    args = parser.parse_args()
    if args.episodes < 1:
        parser.error("--episodes must be at least 1")

    profile = load_hardware_profile(args.profile)
    report = build_report(
        profile=profile,
        episodes=args.episodes,
        seed=args.seed,
        reference_log=args.reference_log,
        candidate_log=args.candidate_log,
        reference_frame=args.reference_frame,
        candidate_frame=args.candidate_frame,
    )
    json_path, html_path = write_report(report, args.output)
    print(
        f"SIL {'PASS' if report['decision']['sil_passed'] else 'FAIL'} | "
        f"hardware ready "
        f"{'YES' if report['decision']['hardware_ready'] else 'NO'}"
    )
    for item in report["readiness"]:
        if item["required"] and not item["passed"]:
            print(f"BLOCKED {item['id']}: {item['detail']}")
    print(json_path)
    print(html_path)


if __name__ == "__main__":
    main()
