"""Tests for the headless swarm engagement runner."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from swarm.rf_link import RfLinkConfig
from swarm.runner import run_scenario
from swarm.scenario import (
    CoordinatorSpec,
    InterceptorSpec,
    SwarmScenario,
    ThreatSpec,
    get_swarm_scenario,
)
from swarm.telemetry import SCHEMA, validate_swarm_packet


class _CapturePublisher:
    """Validates every emitted telemetry body; raises on a bad packet."""

    def __init__(self):
        self.count = 0

    def publish(self, body):
        validate_swarm_packet({"schema": SCHEMA, "sequence": self.count, **body})
        self.count += 1

    def close(self):
        pass


def test_bundled_scenario_is_deterministic():
    scenario = get_swarm_scenario("saturation_6v4")
    first = run_scenario(scenario, seed=42).to_dict()
    second = run_scenario(scenario, seed=42).to_dict()
    assert first == second


def test_every_threat_reaches_a_terminal_status():
    result = run_scenario(get_swarm_scenario("saturation_6v4"), seed=42)
    statuses = {o["status"] for o in result.threat_outcomes}
    assert "ACTIVE" not in statuses
    assert result.neutralized + result.breached + result.leaked == result.threats_total


def test_oversaturation_produces_leakers():
    result = run_scenario(get_swarm_scenario("overwhelm_8v3"), seed=7)
    # 8 threats, 3 one-shot interceptors -> at least some leak through.
    assert result.leaked >= 1
    assert result.interceptors_expended <= result.interceptors_total


def _small_scenario():
    rf = RfLinkConfig(max_range_m=4000.0, link_budget_margin_db=10.0)
    return SwarmScenario(
        scenario_id="unit_5v2",
        description="surplus interceptors vs two slow threats",
        seed=123,
        protected_center_enu_m=(0.0, 0.0, 0.0),
        coordinator=CoordinatorSpec(
            id="coordinator-01", start_enu_m=(0.0, -60.0, 120.0), rf_link=rf
        ),
        interceptors=tuple(
            InterceptorSpec(
                id=f"int-{i}",
                airframe_profile_id="interceptor.reference-v1",
                start_enu_m=(float(-120 + 60 * i), -80.0, 8.0),
            )
            for i in range(5)
        ),
        threats=(
            ThreatSpec("thr-0", "consumer_quad", "MEDIUM", (140.0, 40.0, 40.0), 16.0),
            ThreatSpec("thr-1", "consumer_quad", "MEDIUM", (-140.0, 40.0, 40.0), 16.0),
        ),
        duration_limit_s=60.0,
    )


def test_surplus_swarm_neutralizes_all_threats():
    result = run_scenario(_small_scenario())
    assert result.neutralized == result.threats_total
    assert result.breached == 0
    assert result.leaked == 0


def test_telemetry_packets_validate():
    capture = _CapturePublisher()
    run_scenario(_small_scenario(), telemetry=capture)
    assert capture.count > 0
