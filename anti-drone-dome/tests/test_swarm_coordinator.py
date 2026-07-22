"""Tests for the swarm coordinator brain (assignment + RF + re-tasking)."""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from swarm.coordinator import (
    ASSIGNED,
    AUTONOMOUS_LOCAL,
    COASTING,
    SwarmCoordinator,
)
from swarm.rf_link import RfLinkConfig, RfLinkModel

_COORD = {"position": [0.0, 0.0, 150.0], "velocity": [0.0, 0.0, 0.0]}


def _coordinator(max_range_m=5000.0, min_dwell_s=1.0, seed=11):
    config = RfLinkConfig(max_range_m=max_range_m, link_budget_margin_db=8.0)
    return SwarmCoordinator(
        RfLinkModel(config, seed=seed), min_dwell_s=min_dwell_s, link_timeout_s=0.5
    )


def _interceptor(iid, pos):
    return {"id": iid, "position": pos, "velocity": [0.0, 0.0, 0.0],
            "energy_remaining_fraction": 1.0}


def _threat(tid, pos, level="HIGH"):
    return {"id": tid, "position_estimate": pos, "velocity": [0.0, 0.0, 0.0],
            "threat_level": level}


def _run(coord, interceptors_fn, threats_fn, ticks, t0=0.0, dt=0.05):
    t = t0
    plan = None
    for _ in range(ticks):
        plan = coord.plan(_COORD, interceptors_fn(t), threats_fn(t), t)
        t += dt
    return plan, t


def test_in_range_interceptor_becomes_assigned():
    coord = _coordinator()
    interceptors = [_interceptor("int-0", [0.0, 0.0, 10.0])]
    threats = [_threat("thr-0", [200.0, 0.0, 50.0])]
    plan, _ = _run(coord, lambda t: interceptors, lambda t: threats, ticks=15)
    order = plan.orders["int-0"]
    assert order.state == ASSIGNED
    assert order.assigned_threat_id == "thr-0"


def test_out_of_range_interceptor_goes_autonomous_local():
    coord = _coordinator(max_range_m=1000.0)
    interceptors = [_interceptor("int-0", [5000.0, 0.0, 10.0])]
    threats = [_threat("thr-0", [4800.0, 0.0, 50.0]), _threat("thr-1", [200.0, 0.0, 50.0])]
    plan = coord.plan(_COORD, interceptors, threats, 0.0)
    order = plan.orders["int-0"]
    assert order.state == AUTONOMOUS_LOCAL
    # Self-selects the nearest active threat with no coordinator link.
    assert order.assigned_threat_id == "thr-0"


def test_link_loss_transitions_assigned_to_coasting():
    coord = _coordinator(max_range_m=1000.0)
    threats = [_threat("thr-0", [200.0, 0.0, 50.0])]
    near = [_interceptor("int-0", [0.0, 0.0, 10.0])]
    far = [_interceptor("int-0", [5000.0, 0.0, 10.0])]

    plan, t = _run(coord, lambda t: near, lambda t: threats, ticks=12)
    assert plan.orders["int-0"].state == ASSIGNED

    # Interceptor flies out of RF range; orders stop arriving.
    plan, _ = _run(coord, lambda t: far, lambda t: threats, ticks=20, t0=t)
    order = plan.orders["int-0"]
    assert order.state == COASTING
    assert order.assigned_threat_id == "thr-0"    # still pursuing last order


def test_replan_reassigns_after_threat_neutralized():
    coord = _coordinator()
    interceptors = [_interceptor("int-0", [0.0, 0.0, 10.0])]
    both = [_threat("thr-0", [150.0, 0.0, 40.0]), _threat("thr-1", [400.0, 0.0, 40.0])]

    plan, t = _run(coord, lambda t: interceptors, lambda t: both, ticks=15)
    first = plan.orders["int-0"].assigned_threat_id
    assert first in ("thr-0", "thr-1")

    # Remove the assigned threat -> coordinator must retask to the survivor.
    remaining = [th for th in both if th["id"] != first]
    plan, _ = _run(coord, lambda t: interceptors, lambda t: remaining, ticks=15, t0=t)
    assert plan.orders["int-0"].assigned_threat_id == remaining[0]["id"]


def test_hysteresis_holds_target_until_dwell_and_margin():
    coord = _coordinator(min_dwell_s=1.0)
    interceptors = [_interceptor("int-0", [0.0, 0.0, 0.0])]

    # thr-a is the higher-priority (nearer-centre) threat -> int-0 is assigned it.
    near = [_threat("thr-a", [50.0, 0.0, 0.0]), _threat("thr-b", [60.0, 0.0, 0.0])]
    plan, t = _run(coord, lambda t: interceptors, lambda t: near, ticks=12)
    assert plan.orders["int-0"].assigned_threat_id == "thr-a"

    # thr-b now becomes both nearer-centre (higher priority) and much cheaper, so
    # the fresh proposal flips to thr-b -- but within the dwell window int-0 holds.
    moved = [_threat("thr-a", [55.0, 0.0, 0.0]), _threat("thr-b", [40.0, 0.0, 0.0])]
    plan, t = _run(coord, lambda t: interceptors, lambda t: moved, ticks=4, t0=t)
    assert plan.orders["int-0"].assigned_threat_id == "thr-a"

    # Past the dwell time, the margin-beating switch is allowed.
    plan, _ = _run(coord, lambda t: interceptors, lambda t: moved, ticks=20, t0=t)
    assert plan.orders["int-0"].assigned_threat_id == "thr-b"


def test_plan_is_deterministic():
    threats = [_threat("thr-0", [4800.0, 0.0, 50.0])]
    interceptors = [_interceptor("int-0", [4600.0, 0.0, 10.0])]   # near RF edge

    coord_a = _coordinator(max_range_m=5000.0, seed=99)
    coord_b = _coordinator(max_range_m=5000.0, seed=99)
    plan_a, _ = _run(coord_a, lambda t: interceptors, lambda t: threats, ticks=25)
    plan_b, _ = _run(coord_b, lambda t: interceptors, lambda t: threats, ticks=25)
    a = plan_a.orders["int-0"]
    b = plan_b.orders["int-0"]
    assert (a.state, a.assigned_threat_id) == (b.state, b.assigned_threat_id)
    assert plan_a.link_health == plan_b.link_health
