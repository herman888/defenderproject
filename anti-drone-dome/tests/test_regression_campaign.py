import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from ml.controllers import APNController
from ml.stress_scenarios import load_campaign
from scripts.benchmark_controllers import run_episode
from validation.failure_analysis import analyze_campaign, classify_episode


ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
CATALOG = os.path.join(ROOT, "scenario_data", "regression_campaign_v1.json")


def test_campaign_catalog_is_versioned_unique_and_repeatable():
    campaign = load_campaign(CATALOG)
    assert campaign["schema"] == "aegis.regression-campaign.v1"
    assert len(campaign["cases"]) >= 8
    assert len({case.case_id for case in campaign["cases"]}) == len(
        campaign["cases"]
    )
    case = campaign["cases"][0]
    first = run_episode(
        APNController(),
        case.scenario.profile,
        case.scenario.intruder_type,
        seed=44,
        observation_version="v2",
        fixed_scenario=case.scenario,
    )
    second = run_episode(
        APNController(),
        case.scenario.profile,
        case.scenario.intruder_type,
        seed=44,
        observation_version="v2",
        fixed_scenario=case.scenario,
    )
    assert first["scenario_id"] == case.case_id
    assert first["duration_s"] == second["duration_s"]
    assert first["energy_used"] == second["energy_used"]


def test_campaign_rejects_duplicate_scenario_ids(tmp_path):
    data = json.loads(open(CATALOG, encoding="utf-8").read())
    data["scenarios"].append(dict(data["scenarios"][0]))
    path = tmp_path / "invalid.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ValueError, match="unique"):
        load_campaign(str(path))


def test_failure_analysis_reports_correlations_without_causal_claim():
    campaign = load_campaign(CATALOG)
    case = campaign["cases"][-1]
    episode = {
        "scenario_id": case.case_id,
        "intercepted": False,
        "outcome": "breach",
        "duration_s": 42.0,
        "energy_used": 9.0,
        "battery_remaining": 0.8,
        "action_saturation_fraction": 0.35,
        "sensor_latency_s": 0.35,
        "sensor_dropout_probability": 0.25,
        "radar_noise_std_m": 5.5,
        "wind_speed_mps": 16.0,
        "evasion_mps": 16.0,
        "mass_factor": 1.2,
        "actuator_time_constant_s": 0.3,
    }
    classification = classify_episode(episode)
    assert classification["severity"] == "critical"
    assert not classification["causal_claim"]
    assert "high_sensor_latency" in classification["observed_stress_factors"]
    analysis = analyze_campaign([episode], (case,))
    assert not analysis["release_ready"]
    assert analysis["failed_scenarios"] == [case.case_id]
    assert "do not prove root cause" in analysis["interpretation"]


def test_reliability_gate_rejects_underpowered_perfect_sample():
    campaign = load_campaign(CATALOG)
    case = campaign["cases"][0]
    episodes = []
    for seed in range(20):
        episodes.append({
            "scenario_id": case.case_id,
            "intercepted": True,
            "outcome": "intercepted",
            "duration_s": 5.0,
            "energy_used": 1.0,
            "battery_remaining": 0.9,
            "action_saturation_fraction": 0.01,
            "sensor_latency_s": 0.0,
            "sensor_dropout_probability": 0.0,
            "radar_noise_std_m": 0.1,
            "wind_speed_mps": 0.0,
            "evasion_mps": 0.0,
            "mass_factor": 1.0,
            "actuator_time_constant_s": 0.1,
            "seed": seed,
        })
    analysis = analyze_campaign(episodes, (case,))
    result = analysis["scenario_results"][0]
    assert result["intercept_rate"] == 1.0
    assert result["intercept_rate_wilson_95"][0] < 0.95
    assert not result["passed"]
