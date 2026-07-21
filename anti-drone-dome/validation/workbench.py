"""Automated SIL evidence, HIL readiness gates, and validation reports."""

from __future__ import annotations

import html
import json
import os
import statistics
from datetime import datetime, timezone

import numpy as np

import config
from hardware.profile import HardwareProfile
from ml.controllers import APNController
from scripts.benchmark_controllers import run_episode, summarize
from validation.flight_log import compare_flight_logs, load_flight_log


def run_sil(profile: HardwareProfile, episodes: int, seed: int) -> dict:
    controller = APNController()
    results = [
        run_episode(
            controller,
            pattern=None,
            intruder_type=None,
            seed=seed + index,
            residual_apn=False,
            observation_version="v2",
            procedural=True,
        )
        for index in range(episodes)
    ]
    return {
        "summary": summarize("apn", results),
        "episodes": results,
    }


def evaluate_readiness(profile: HardwareProfile) -> list[dict]:
    checks = []

    def add(check_id, passed, detail, required=True):
        checks.append({
            "id": check_id,
            "passed": bool(passed),
            "required": bool(required),
            "detail": detail,
        })

    site_is_placeholder = (
        abs(config.HOME_LAT - 43.0) < 1e-9
        and abs(config.HOME_LON - (-79.0)) < 1e-9
    )
    add(
        "approved-test-site",
        not site_is_placeholder,
        (
            "Configured site is still the documented placeholder."
            if site_is_placeholder
            else "Configured geodetic site differs from the placeholder."
        ),
        required=profile.data["safety"]["approved_test_site_required"],
    )
    add(
        "actuation-safe-default",
        not profile.actuation_enabled,
        (
            "Actuation is disabled."
            if not profile.actuation_enabled
            else "Actuation is enabled and requires independent bench review."
        ),
    )
    endpoint = profile.data["autopilot"].get("endpoint")
    add(
        "hardware-endpoint",
        bool(endpoint) or profile.mode == "sil",
        (
            f"Configured endpoint: {endpoint}"
            if endpoint
            else "No physical/SITL endpoint configured."
        ),
        required=profile.mode != "sil",
    )
    protocol_compatible = not (
        profile.protocol == "msp" and profile.mode in {"sitl", "hil"}
    )
    add(
        "command-protocol",
        protocol_compatible,
        (
            "Betaflight MSP is currently supported for read-only profiling only; "
            "the command bridge is MAVLink/ArduPilot."
            if not protocol_compatible or profile.protocol == "msp"
            else f"Configured protocol: {profile.protocol}."
        ),
        required=profile.mode not in {"sil", "hardware_readonly"},
    )
    uncalibrated = [
        sensor["name"]
        for sensor in profile.data["sensors"]
        if sensor.get("calibration_required")
    ]
    add(
        "sensor-calibration",
        not uncalibrated,
        (
            "Calibration evidence required for: " + ", ".join(uncalibrated)
            if uncalibrated
            else "No outstanding sensor calibrations in this profile."
        ),
        required=profile.mode != "sil",
    )
    return checks


def evaluate_gates(
    profile: HardwareProfile,
    sil: dict,
    calibration: dict | None,
) -> list[dict]:
    gates = profile.data["validation_gates"]
    summary = sil["summary"]
    results = [
        {
            "id": "intercept-rate",
            "passed": summary["intercept_rate"] >= gates["minimum_intercept_rate"],
            "actual": summary["intercept_rate"],
            "limit": gates["minimum_intercept_rate"],
            "operator": ">=",
        },
        {
            "id": "duration-p95",
            "passed": summary["duration_s_p95"] <= gates["maximum_duration_p95_s"],
            "actual": summary["duration_s_p95"],
            "limit": gates["maximum_duration_p95_s"],
            "operator": "<=",
        },
        {
            "id": "energy-p95",
            "passed": summary["energy_used_p95"] <= gates["maximum_energy_p95"],
            "actual": summary["energy_used_p95"],
            "limit": gates["maximum_energy_p95"],
            "operator": "<=",
        },
        {
            "id": "action-saturation",
            "passed": (
                summary["mean_action_saturation_fraction"]
                <= gates["maximum_action_saturation_fraction"]
            ),
            "actual": summary["mean_action_saturation_fraction"],
            "limit": gates["maximum_action_saturation_fraction"],
            "operator": "<=",
        },
    ]
    if calibration is not None:
        results.extend([
            {
                "id": "trajectory-rmse",
                "passed": (
                    calibration["trajectory_rmse_m"]
                    <= gates["maximum_trajectory_rmse_m"]
                ),
                "actual": calibration["trajectory_rmse_m"],
                "limit": gates["maximum_trajectory_rmse_m"],
                "operator": "<=",
            },
            {
                "id": "timing-offset",
                "passed": (
                    abs(calibration["estimated_candidate_time_offset_s"])
                    <= gates["maximum_timing_offset_s"]
                ),
                "actual": abs(
                    calibration["estimated_candidate_time_offset_s"]
                ),
                "limit": gates["maximum_timing_offset_s"],
                "operator": "<=",
            },
        ])
    return results


def build_report(
    profile: HardwareProfile,
    episodes: int,
    seed: int,
    reference_log: str | None = None,
    candidate_log: str | None = None,
    reference_frame: str = "ENU",
    candidate_frame: str = "ENU",
) -> dict:
    if bool(reference_log) != bool(candidate_log):
        raise ValueError("reference and candidate logs must be supplied together")
    sil = run_sil(profile, episodes, seed)
    calibration = None
    if reference_log and candidate_log:
        calibration = compare_flight_logs(
            load_flight_log(reference_log, reference_frame),
            load_flight_log(candidate_log, candidate_frame),
        )
    readiness = evaluate_readiness(profile)
    gates = evaluate_gates(profile, sil, calibration)
    required_readiness = [
        item for item in readiness if item["required"]
    ]
    return {
        "schema": "aegis.validation-report.v1",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "profile": profile.summary(),
        "evaluation": {
            "episodes": episodes,
            "seed_start": seed,
            "controller": "APN",
            "procedural_curriculum_level": 1.0,
        },
        "sil": sil,
        "calibration": calibration,
        "readiness": readiness,
        "gates": gates,
        "decision": {
            "sil_passed": all(item["passed"] for item in gates),
            "hardware_ready": (
                all(item["passed"] for item in required_readiness)
                and calibration is not None
                and all(item["passed"] for item in gates)
            ),
            "hardware_actuation_authorized": False,
            "reason": (
                "This report never authorizes physical actuation; independent "
                "safety/range approval and explicit operator acknowledgement "
                "remain required."
            ),
        },
    }


def _status(value: bool) -> str:
    return "PASS" if value else "FAIL"


def write_report(report: dict, output_stem: str) -> tuple[str, str]:
    output_stem = os.path.abspath(output_stem)
    os.makedirs(os.path.dirname(output_stem), exist_ok=True)
    json_path = output_stem + ".json"
    html_path = output_stem + ".html"
    with open(json_path, "w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2, allow_nan=False)

    summary = report["sil"]["summary"]
    readiness_rows = "".join(
        f"<tr><td>{html.escape(item['id'])}</td>"
        f"<td>{_status(item['passed'])}</td>"
        f"<td>{html.escape(item['detail'])}</td></tr>"
        for item in report["readiness"]
    )
    gate_rows = "".join(
        f"<tr><td>{html.escape(item['id'])}</td>"
        f"<td>{_status(item['passed'])}</td>"
        f"<td>{item['actual']:.4g} {html.escape(item['operator'])} "
        f"{item['limit']:.4g}</td></tr>"
        for item in report["gates"]
    )
    calibration = report["calibration"]
    calibration_html = (
        "<p>No real/reference flight-log comparison supplied.</p>"
        if calibration is None
        else (
            f"<p>Trajectory RMSE: {calibration['trajectory_rmse_m']:.3f} m; "
            f"p95: {calibration['trajectory_p95_m']:.3f} m; "
            f"time offset: "
            f"{calibration['estimated_candidate_time_offset_s']:.3f} s.</p>"
        )
    )
    document = f"""<!doctype html>
<html><head><meta charset="utf-8"><title>AEGIS validation report</title>
<style>
body{{font-family:Arial,sans-serif;max-width:1100px;margin:32px auto;color:#17212b}}
table{{border-collapse:collapse;width:100%;margin:12px 0 24px}}
th,td{{border:1px solid #b8c0c8;padding:7px;text-align:left}}
th{{background:#e8edf1}} code{{background:#eef2f5;padding:2px 4px}}
</style></head><body>
<h1>AEGIS Hardware Validation Workbench</h1>
<p>Profile: <strong>{html.escape(report['profile']['label'])}</strong>
({html.escape(report['profile']['mode'])})</p>
<h2>SIL evidence</h2>
<p>{summary['intercepts']}/{summary['episodes']} interceptions;
mean duration {summary['mean_duration_s']:.3f} s;
p95 duration {summary['duration_s_p95']:.3f} s;
p95 energy {summary['energy_used_p95']:.3f}.</p>
<h2>Validation gates</h2><table><tr><th>Gate</th><th>Status</th><th>Evidence</th></tr>
{gate_rows}</table>
<h2>Hardware readiness</h2><table><tr><th>Check</th><th>Status</th><th>Detail</th></tr>
{readiness_rows}</table>
<h2>Flight-log calibration</h2>{calibration_html}
<h2>Decision</h2>
<p>SIL: <strong>{_status(report['decision']['sil_passed'])}</strong><br>
Hardware ready: <strong>{_status(report['decision']['hardware_ready'])}</strong><br>
Physical actuation authorized: <strong>NO</strong></p>
<p>{html.escape(report['decision']['reason'])}</p>
</body></html>"""
    with open(html_path, "w", encoding="utf-8") as handle:
        handle.write(document)
    return json_path, html_path
