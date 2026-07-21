"""Run named synthetic C-UAS stress cases and produce regression evidence."""

from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import html
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from ml.controllers import APNController
from ml.stress_scenarios import load_campaign
from scripts.benchmark_controllers import run_episode
from validation.failure_analysis import analyze_campaign


def _write_report(report: dict, output_stem: str) -> tuple[str, str, str]:
    output_stem = os.path.abspath(output_stem)
    os.makedirs(os.path.dirname(output_stem), exist_ok=True)
    json_path = output_stem + ".json"
    csv_path = output_stem + ".csv"
    html_path = output_stem + ".html"
    with open(json_path, "w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2, allow_nan=False)
    rows = report["analysis"]["scenario_results"]
    with open(csv_path, "w", newline="", encoding="utf-8") as handle:
        fields = [
            "scenario_id", "label", "episodes", "intercept_rate",
            "intercept_rate_wilson_95",
            "duration_p95_s", "energy_p95",
            "mean_action_saturation_fraction",
            "performance_limit_utilization", "passed",
        ]
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows({
            key: (
                json.dumps(row[key])
                if key == "intercept_rate_wilson_95"
                else row[key]
            )
            for key in fields
        } for row in rows)

    scenario_rows = "".join(
        "<tr>"
        f"<td>{html.escape(row['scenario_id'])}</td>"
        f"<td>{'PASS' if row['passed'] else 'FAIL'}</td>"
        f"<td>{row['intercept_rate']:.1%}</td>"
        f"<td>{row['intercept_rate_wilson_95'][0]:.1%}</td>"
        f"<td>{row['duration_p95_s']:.2f}s</td>"
        f"<td>{row['energy_p95']:.2f}</td>"
        f"<td>{row['mean_action_saturation_fraction']:.1%}</td>"
        f"<td>{html.escape(', '.join(row['tags']))}</td>"
        "</tr>"
        for row in rows
    )
    factor_rows = "".join(
        "<tr>"
        f"<td>{html.escape(item['factor'])}</td>"
        f"<td>{item['episodes']}</td>"
        f"<td>{item['failures']}</td>"
        f"<td>{item['failure_rate']:.1%}</td>"
        "</tr>"
        for item in report["analysis"]["stress_factor_summary"]
    ) or "<tr><td colspan='4'>No threshold stress factors observed.</td></tr>"
    watch_rows = "".join(
        "<tr>"
        f"<td>{html.escape(item['scenario_id'])}</td>"
        f"<td>{item['performance_limit_utilization']:.1%}</td>"
        f"<td>{item['duration_p95_s']:.2f}s</td>"
        f"<td>{item['energy_p95']:.2f}</td>"
        "</tr>"
        for item in report["analysis"]["performance_watchlist"]
    )
    decision = "PASS" if report["analysis"]["release_ready"] else "FAIL"
    document = f"""<!doctype html>
<html><head><meta charset="utf-8"><title>AEGIS regression campaign</title>
<style>
body{{font-family:Arial,sans-serif;max-width:1200px;margin:32px auto;color:#17212b}}
table{{border-collapse:collapse;width:100%;margin:12px 0 28px}}
th,td{{border:1px solid #b8c0c8;padding:7px;text-align:left}}
th{{background:#e8edf1}} .decision{{font-size:1.4rem;font-weight:bold}}
</style></head><body>
<h1>AEGIS Synthetic Regression Campaign</h1>
<p>Campaign: <strong>{html.escape(report['campaign_id'])}</strong><br>
Controller: APN &middot; Seeds: {report['seed_start']} onward &middot;
Repeats per case: {report['repeats_per_case']}</p>
<p class="decision">Release gate: {decision}</p>
<h2>Scenario gates</h2>
<table><tr><th>Scenario</th><th>Status</th><th>Intercept</th>
<th>Wilson lower 95%</th><th>Duration p95</th><th>Energy p95</th>
<th>Saturation</th><th>Tags</th></tr>
{scenario_rows}</table>
<h2>Performance-margin watchlist</h2>
<p>Highest utilization of any duration, energy, or saturation limit.</p>
<table><tr><th>Scenario</th><th>Limit utilization</th><th>Duration p95</th>
<th>Energy p95</th></tr>{watch_rows}</table>
<h2>Observed stress-factor correlation</h2>
<p>{html.escape(report['analysis']['interpretation'])}</p>
<table><tr><th>Factor</th><th>Episodes</th><th>Failures</th>
<th>Failure rate</th></tr>{factor_rows}</table>
<h2>Reproduction</h2>
<p>Every episode stores its scenario ID and seed in the JSON artifact.</p>
</body></html>"""
    with open(html_path, "w", encoding="utf-8") as handle:
        handle.write(document)
    return json_path, csv_path, html_path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--campaign",
        default="scenario_data/regression_campaign_v1.json",
    )
    parser.add_argument("--repeats", type=int, default=100)
    parser.add_argument("--seed", type=int, default=1000)
    parser.add_argument("--output", default="validation_reports/regression_campaign")
    args = parser.parse_args()
    if args.repeats <= 0:
        parser.error("--repeats must be positive")

    campaign = load_campaign(args.campaign)
    controller = APNController()
    episodes = []
    for case_index, case in enumerate(campaign["cases"]):
        for repeat in range(args.repeats):
            seed = args.seed + case_index * 10000 + repeat
            episode = run_episode(
                controller,
                pattern=case.scenario.profile,
                intruder_type=case.scenario.intruder_type,
                seed=seed,
                observation_version="v2",
                fixed_scenario=case.scenario,
            )
            episode["case_label"] = case.label
            episode["case_tags"] = list(case.tags)
            episodes.append(episode)
    analysis = analyze_campaign(episodes, campaign["cases"])
    report = {
        "schema": "aegis.regression-report.v1",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "campaign_id": campaign["campaign_id"],
        "campaign_schema": campaign["schema"],
        "controller": "APN",
        "seed_start": args.seed,
        "repeats_per_case": args.repeats,
        "total_episodes": len(episodes),
        "analysis": analysis,
        "episodes": episodes,
    }
    paths = _write_report(report, args.output)
    print(
        f"{'PASS' if analysis['release_ready'] else 'FAIL'} | "
        f"{len(campaign['cases'])} scenarios | {len(episodes)} episodes"
    )
    for row in analysis["scenario_results"]:
        print(
            f"{'PASS' if row['passed'] else 'FAIL'} "
            f"{row['scenario_id']}: {row['intercept_rate']:.0%}, "
            f"p95 {row['duration_p95_s']:.1f}s"
        )
    for path in paths:
        print(path)


if __name__ == "__main__":
    main()
