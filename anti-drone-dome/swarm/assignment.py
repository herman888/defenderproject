"""Weapon-target assignment for the interceptor swarm (pure, numpy-only).

Given interceptor states and threat tracks, build a cost matrix (expected
time-to-intercept) and allocate interceptors to threats. The default policy is
priority-greedy: the most dangerous threats are covered first, so a saturation
attack degrades gracefully (lowest-priority threats leak) rather than leaving a
high-value threat uncovered by a cost-optimal-but-priority-blind solver.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

_V_DESIGN = 65.0            # m/s design intercept speed (matches guidance._V_INT)
_ENERGY_FLOOR = 0.05        # interceptors below this energy fraction are infeasible
_PRIORITY_REF_M = 300.0     # proximity-urgency reference distance to protected asset

_THREAT_LEVEL_WEIGHT = {"HIGH": 30.0, "MEDIUM": 20.0, "LOW": 10.0}


@dataclass(frozen=True)
class Assignment:
    """Result of an allocation pass (all fields index into the input lists)."""

    pairs: dict            # threat_index -> interceptor_index
    leakers: list          # threat indices with no interceptor assigned
    reserves: list         # interceptor indices left unassigned


def threat_priority(threat: dict, protected_center=(0.0, 0.0, 0.0)) -> float:
    """Urgency score (higher = engage first).

    Combines a threat-level weight with proximity to the protected asset, so a
    high-value threat near the centre outranks a distant lesser one.
    """
    level = str(threat.get("threat_level", "MEDIUM")).upper()
    score = _THREAT_LEVEL_WEIGHT.get(level, _THREAT_LEVEL_WEIGHT["MEDIUM"])
    position = np.asarray(threat.get("position_estimate", (0.0, 0.0, 0.0)), dtype=float)
    center = np.asarray(protected_center, dtype=float)
    distance = float(np.linalg.norm(position - center))
    proximity = 1.0 - min(distance / _PRIORITY_REF_M, 1.0)
    return score + 5.0 * proximity


def _pair_cost(interceptor: dict, threat: dict, guidance) -> float:
    if float(interceptor.get("energy_remaining_fraction", 1.0)) < _ENERGY_FLOOR:
        return float("inf")
    track = {
        "detected": True,
        "position_estimate": threat["position_estimate"],
        "velocity": threat.get("velocity", (0.0, 0.0, 0.0)),
    }
    ttc = guidance.time_to_intercept(interceptor, track)
    if np.isfinite(ttc):
        return float(ttc)
    # Not currently closing: fall back to a geometric estimate — the interceptor
    # will accelerate toward the threat rather than being deemed unreachable.
    i_pos = np.asarray(interceptor["position"], dtype=float)
    t_pos = np.asarray(threat["position_estimate"], dtype=float)
    return float(np.linalg.norm(t_pos - i_pos) / _V_DESIGN)


def build_cost_matrix(interceptor_states, threat_tracks, guidance):
    """Return an (n_interceptors x n_threats) cost matrix of intercept times."""
    n_i = len(interceptor_states)
    n_t = len(threat_tracks)
    cost = np.full((n_i, n_t), np.inf, dtype=float)
    for i, interceptor in enumerate(interceptor_states):
        for j, threat in enumerate(threat_tracks):
            cost[i, j] = _pair_cost(interceptor, threat, guidance)
    return cost


def greedy_priority_assignment(cost, priorities, threat_ids=None, interceptor_ids=None):
    """Assign highest-priority threats first to their lowest-cost interceptor.

    Ties are broken deterministically by id (or index) so the result never
    depends on dict/iteration order.
    """
    cost = np.asarray(cost, dtype=float)
    n_i, n_t = cost.shape
    threat_ids = threat_ids if threat_ids is not None else list(range(n_t))
    interceptor_ids = (
        interceptor_ids if interceptor_ids is not None else list(range(n_i))
    )
    # Threat order: highest priority first, then id for stable tie-break.
    order = sorted(
        range(n_t), key=lambda j: (-float(priorities[j]), str(threat_ids[j]))
    )
    used = set()
    pairs: dict = {}
    for j in order:
        best_i = None
        best_key = None
        for i in range(n_i):
            if i in used or not np.isfinite(cost[i, j]):
                continue
            key = (float(cost[i, j]), str(interceptor_ids[i]))
            if best_key is None or key < best_key:
                best_key, best_i = key, i
        if best_i is not None:
            pairs[j] = best_i
            used.add(best_i)
    leakers = [j for j in range(n_t) if j not in pairs]
    reserves = [i for i in range(n_i) if i not in used]
    return Assignment(pairs=pairs, leakers=leakers, reserves=reserves)


def hungarian_assignment(cost):
    """Minimum-total-cost assignment via Kuhn-Munkres (numpy-only, no scipy).

    Cost-optimal but priority-blind; offered as an alternative to the greedy
    policy for balanced counts. Non-finite costs are treated as unpickable.
    Returns an ``Assignment`` (one interceptor per threat where feasible).
    """
    cost = np.asarray(cost, dtype=float)
    n_i, n_t = cost.shape
    n = max(n_i, n_t)
    big = 0.0
    finite = cost[np.isfinite(cost)]
    if finite.size:
        big = float(finite.max()) * 10.0 + 1.0
    # Square, padded matrix; inf/pad entries get a large finite sentinel.
    padded = np.full((n, n), big, dtype=float)
    real = np.where(np.isfinite(cost), cost, big)
    padded[:n_i, :n_t] = real

    # Kuhn-Munkres on `padded`.
    u = np.zeros(n + 1)
    v = np.zeros(n + 1)
    p = np.zeros(n + 1, dtype=int)
    way = np.zeros(n + 1, dtype=int)
    for i in range(1, n + 1):
        p[0] = i
        j0 = 0
        minv = np.full(n + 1, np.inf)
        used = np.zeros(n + 1, dtype=bool)
        while True:
            used[j0] = True
            i0 = p[j0]
            delta = np.inf
            j1 = -1
            for j in range(1, n + 1):
                if used[j]:
                    continue
                cur = padded[i0 - 1, j - 1] - u[i0] - v[j]
                if cur < minv[j]:
                    minv[j] = cur
                    way[j] = j0
                if minv[j] < delta:
                    delta = minv[j]
                    j1 = j
            for j in range(n + 1):
                if used[j]:
                    u[p[j]] += delta
                    v[j] -= delta
                else:
                    minv[j] -= delta
            j0 = j1
            if p[j0] == 0:
                break
        while j0:
            j1 = way[j0]
            p[j0] = p[j1]
            j0 = j1

    pairs: dict = {}
    used_i: set = set()
    for j in range(1, n + 1):
        i = p[j] - 1
        col = j - 1
        if i < n_i and col < n_t and np.isfinite(cost[i, col]):
            pairs[col] = i
            used_i.add(i)
    leakers = [j for j in range(n_t) if j not in pairs]
    reserves = [i for i in range(n_i) if i not in used_i]
    return Assignment(pairs=pairs, leakers=leakers, reserves=reserves)
