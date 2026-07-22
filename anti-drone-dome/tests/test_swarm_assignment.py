"""Tests for swarm weapon-target assignment."""

import itertools
import os
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from swarm.assignment import (
    build_cost_matrix,
    greedy_priority_assignment,
    hungarian_assignment,
    threat_priority,
)


class _StubGuidance:
    """time_to_intercept -> inf so cost falls back to geometric range/V_DESIGN."""

    def time_to_intercept(self, interceptor, track):
        return float("inf")


def _interceptor(iid, pos, energy=1.0):
    return {"id": iid, "position": pos, "velocity": [0.0, 0.0, 0.0],
            "energy_remaining_fraction": energy}


def _threat(tid, pos, level="MEDIUM"):
    return {"id": tid, "position_estimate": pos, "velocity": [0.0, 0.0, 0.0],
            "threat_level": level}


def test_cost_matrix_prefers_closer_interceptor():
    interceptors = [_interceptor("int-0", [0, 0, 0]), _interceptor("int-1", [100, 0, 0])]
    threats = [_threat("thr-0", [10, 0, 0]), _threat("thr-1", [90, 0, 0])]
    cost = build_cost_matrix(interceptors, threats, _StubGuidance())
    assert cost.shape == (2, 2)
    assert cost[0, 0] < cost[1, 0]   # int-0 closer to thr-0
    assert cost[1, 1] < cost[0, 1]   # int-1 closer to thr-1


def test_energy_depleted_interceptor_is_infeasible():
    interceptors = [_interceptor("int-0", [0, 0, 0], energy=0.01)]
    threats = [_threat("thr-0", [10, 0, 0])]
    cost = build_cost_matrix(interceptors, threats, _StubGuidance())
    assert not np.isfinite(cost[0, 0])


def test_threat_priority_orders_high_over_medium_and_near_over_far():
    near_high = threat_priority(_threat("a", [10, 0, 0], "HIGH"))
    far_high = threat_priority(_threat("b", [400, 0, 0], "HIGH"))
    medium = threat_priority(_threat("c", [10, 0, 0], "MEDIUM"))
    assert near_high > far_high
    assert near_high > medium


def test_greedy_covers_high_priority_when_interceptors_scarce():
    interceptors = [_interceptor("int-0", [0, 0, 0])]
    threats = [_threat("thr-0", [5, 0, 0], "MEDIUM"), _threat("thr-1", [50, 0, 0], "HIGH")]
    cost = build_cost_matrix(interceptors, threats, _StubGuidance())
    priorities = [threat_priority(t) for t in threats]
    result = greedy_priority_assignment(
        cost, priorities, [t["id"] for t in threats], [i["id"] for i in interceptors]
    )
    assert result.pairs == {1: 0}      # HIGH threat (index 1) gets the interceptor
    assert result.leakers == [0]       # MEDIUM threat leaks
    assert result.reserves == []


def test_greedy_leaves_reserves_when_interceptors_surplus():
    interceptors = [_interceptor("int-0", [0, 0, 0]), _interceptor("int-1", [10, 0, 0])]
    threats = [_threat("thr-0", [5, 0, 0])]
    cost = build_cost_matrix(interceptors, threats, _StubGuidance())
    priorities = [threat_priority(t) for t in threats]
    result = greedy_priority_assignment(
        cost, priorities, [t["id"] for t in threats], [i["id"] for i in interceptors]
    )
    assert len(result.pairs) == 1
    assert len(result.reserves) == 1


def test_greedy_tie_break_is_deterministic_by_id():
    interceptors = [_interceptor("int-0", [10, 0, 0]), _interceptor("int-1", [-10, 0, 0])]
    threats = [_threat("thr-0", [0, 0, 0])]
    cost = build_cost_matrix(interceptors, threats, _StubGuidance())
    priorities = [threat_priority(t) for t in threats]
    result = greedy_priority_assignment(
        cost, priorities, [t["id"] for t in threats], [i["id"] for i in interceptors]
    )
    assert result.pairs == {0: 0}      # equal cost -> lower interceptor id wins


def _brute_force_min(cost):
    n_i, n_t = cost.shape
    best = float("inf")
    for perm in itertools.permutations(range(n_i), min(n_i, n_t)):
        total = sum(cost[perm[j], j] for j in range(len(perm)))
        best = min(best, total)
    return best


def test_hungarian_is_cost_optimal():
    cost = np.array([[4.0, 2.0, 8.0], [2.0, 3.0, 7.0], [3.0, 1.0, 6.0]])
    result = hungarian_assignment(cost)
    total = sum(cost[i, j] for j, i in result.pairs.items())
    assert total == pytest.approx(_brute_force_min(cost))
    assert len(result.pairs) == 3


def test_hungarian_handles_more_threats_than_interceptors():
    cost = np.array([[1.0, 5.0, 9.0], [6.0, 2.0, 8.0]])
    result = hungarian_assignment(cost)
    assert len(result.pairs) == 2        # 2 interceptors -> 2 threats
    assert len(result.leakers) == 1
