"""Evidence-based episode classification and campaign aggregation."""

from __future__ import annotations

from collections import Counter, defaultdict
import math
import statistics

import numpy as np


def _wilson_interval(successes: int, episodes: int) -> list[float]:
    if episodes <= 0:
        return [0.0, 0.0]
    z = 1.959963984540054
    proportion = successes / episodes
    denominator = 1.0 + z * z / episodes
    center = (proportion + z * z / (2.0 * episodes)) / denominator
    margin = (
        z
        * math.sqrt(
            proportion * (1.0 - proportion) / episodes
            + z * z / (4.0 * episodes * episodes)
        )
        / denominator
    )
    return [max(0.0, center - margin), min(1.0, center + margin)]


def classify_episode(episode: dict) -> dict:
    """Identify measured stress factors; these are contributors, not causal proof."""
    factors = []
    if episode["sensor_latency_s"] >= 0.25:
        factors.append("high_sensor_latency")
    if episode["sensor_dropout_probability"] >= 0.15:
        factors.append("high_sensor_dropout")
    if episode["radar_noise_std_m"] >= 4.0:
        factors.append("high_measurement_noise")
    if episode["wind_speed_mps"] >= 10.0:
        factors.append("high_wind")
    if episode["evasion_mps"] >= 12.0:
        factors.append("agile_target")
    if episode["mass_factor"] >= 1.18:
        factors.append("high_mass")
    if episode["actuator_time_constant_s"] >= 0.28:
        factors.append("slow_actuator")
    if episode["action_saturation_fraction"] >= 0.30:
        factors.append("control_saturation")
    if episode["battery_remaining"] <= 0.25:
        factors.append("low_energy_reserve")
    return {
        "outcome": episode["outcome"],
        "severity": (
            "critical"
            if not episode["intercepted"]
            else "warning"
            if episode["action_saturation_fraction"] >= 0.30
            else "nominal"
        ),
        "observed_stress_factors": factors,
        "causal_claim": False,
    }


def analyze_campaign(episodes: list[dict], cases: tuple) -> dict:
    case_by_id = {case.case_id: case for case in cases}
    grouped = defaultdict(list)
    factor_outcomes = defaultdict(Counter)
    for episode in episodes:
        episode["analysis"] = classify_episode(episode)
        grouped[episode["scenario_id"]].append(episode)
        for factor in episode["analysis"]["observed_stress_factors"]:
            factor_outcomes[factor][episode["outcome"]] += 1

    scenario_results = []
    for case_id, case_episodes in grouped.items():
        case = case_by_id[case_id]
        intercepts = sum(bool(item["intercepted"]) for item in case_episodes)
        intercept_rate = intercepts / len(case_episodes)
        intercept_interval = _wilson_interval(intercepts, len(case_episodes))
        duration_p95 = float(np.percentile(
            [item["duration_s"] for item in case_episodes], 95
        ))
        energy_p95 = float(np.percentile(
            [item["energy_used"] for item in case_episodes], 95
        ))
        saturation = statistics.fmean(
            item["action_saturation_fraction"] for item in case_episodes
        )
        gates = [
            {
                "id": "intercept-rate-wilson-lower-95",
                "passed": (
                    intercept_interval[0]
                    >= case.gates["minimum_intercept_rate"]
                ),
                "actual": intercept_interval[0],
                "limit": case.gates["minimum_intercept_rate"],
                "operator": ">=",
            },
            {
                "id": "duration-p95",
                "passed": duration_p95 <= case.gates["maximum_duration_p95_s"],
                "actual": duration_p95,
                "limit": case.gates["maximum_duration_p95_s"],
                "operator": "<=",
            },
            {
                "id": "energy-p95",
                "passed": energy_p95 <= case.gates["maximum_energy_p95"],
                "actual": energy_p95,
                "limit": case.gates["maximum_energy_p95"],
                "operator": "<=",
            },
            {
                "id": "action-saturation",
                "passed": saturation
                <= case.gates["maximum_action_saturation_fraction"],
                "actual": saturation,
                "limit": case.gates["maximum_action_saturation_fraction"],
                "operator": "<=",
            },
        ]
        performance_utilization = max(
            duration_p95 / case.gates["maximum_duration_p95_s"],
            energy_p95 / case.gates["maximum_energy_p95"],
            saturation
            / case.gates["maximum_action_saturation_fraction"],
        )
        scenario_results.append({
            "scenario_id": case_id,
            "label": case.label,
            "tags": list(case.tags),
            "episodes": len(case_episodes),
            "intercept_rate": intercept_rate,
            "intercept_rate_wilson_95": intercept_interval,
            "duration_p95_s": duration_p95,
            "energy_p95": energy_p95,
            "mean_action_saturation_fraction": saturation,
            "outcomes": dict(Counter(item["outcome"] for item in case_episodes)),
            "gates": gates,
            "passed": all(item["passed"] for item in gates),
            "performance_limit_utilization": performance_utilization,
        })
    scenario_results.sort(
        key=lambda item: (
            item["passed"],
            item["intercept_rate"],
            -item["duration_p95_s"],
        )
    )
    factor_summary = []
    for factor, outcomes in factor_outcomes.items():
        total = sum(outcomes.values())
        failures = total - outcomes["intercepted"]
        factor_summary.append({
            "factor": factor,
            "episodes": total,
            "failures": failures,
            "failure_rate": failures / total,
            "outcomes": dict(outcomes),
        })
    factor_summary.sort(
        key=lambda item: (-item["failure_rate"], -item["episodes"], item["factor"])
    )
    performance_watchlist = sorted(
        scenario_results,
        key=lambda item: -item["performance_limit_utilization"],
    )[:3]
    return {
        "scenario_results": scenario_results,
        "stress_factor_summary": factor_summary,
        "failed_scenarios": [
            item["scenario_id"] for item in scenario_results if not item["passed"]
        ],
        "performance_watchlist": [
            {
                "scenario_id": item["scenario_id"],
                "performance_limit_utilization": item[
                    "performance_limit_utilization"
                ],
                "duration_p95_s": item["duration_p95_s"],
                "energy_p95": item["energy_p95"],
            }
            for item in performance_watchlist
        ],
        "release_ready": all(item["passed"] for item in scenario_results),
        "interpretation": (
            "Stress factors are measured correlations and do not prove root cause."
        ),
    }
