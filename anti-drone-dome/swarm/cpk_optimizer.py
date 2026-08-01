"""Cost-per-kill weighted allocation across a mixed effector inventory.

Extends the single-type weapon-target assignment in ``swarm/assignment.py`` to a
heterogeneous inventory (quadcopter interceptors, micro-rockets, EW effects) by
scoring each effector-threat pair on three axes:

* **Time to intercept** - can this effector reach the threat before it arrives?
* **Probability of hit** - is the engagement geometrically feasible?
* **Cost per kill** - expected dollars expended per threat neutralised,
  measured against the value of what the threat would destroy.

The economic axis is the point of the module: a $1,800 rocket fired at a $500
decoy is a loss even when it hits, and a system whose pitch is "cheaper than the
threat it defeats" has to be able to show that trade.

This module deliberately reuses ``swarm.assignment.hungarian_assignment`` (pure
numpy, deterministic, already pinned by ``tests/test_swarm_assignment.py``)
rather than pulling in ``scipy.optimize``. Forking the solver would double the
WTA logic and add an undeclared dependency.

Evidence status: ``design-placeholder``. The p_hit model is kinematic only - no
sensor error, no fuzing, no fragmentation pattern. Replace with campaign-derived
hit statistics before quoting a cost-per-kill figure.
"""

from __future__ import annotations

import numpy as np

from swarm.assignment import Assignment, hungarian_assignment

# Normalisation references. Each converts a raw quantity into a roughly [0, 1]
# penalty so the weights are comparable; they are not physical limits.
_TTI_REF_S = 30.0           # a 30 s intercept scores 1.0 on the time axis
_PHIT_RANGE_REF_M = 3000.0  # hit probability decays to the floor by this range
_PHIT_FLOOR = 0.05
_PHIT_CEILING = 0.95
_CPK_PENALTY_CAP = 2.0      # cap so one absurd ratio cannot dominate the sum
_DEFAULT_THREAT_VALUE_USD = 5000.0
_TAIL_CHASE_COS = 0.5       # cos(60 deg): beyond this the threat is opening away


def probability_of_hit(
    effector_pos,
    effector_speed,
    threat_pos,
    threat_vel,
    *,
    is_kinematically_limited: bool,
) -> float:
    """Kinematic hit probability for one effector-threat pair.

    A slower effector is only hopeless in a *tail chase*. Head-on and crossing
    geometries remain feasible because the threat closes the distance itself,
    so speed alone is the wrong test - the original formulation rejected
    perfectly good head-on shots.
    """
    effector_pos = np.asarray(effector_pos, dtype=float)
    threat_pos = np.asarray(threat_pos, dtype=float)
    threat_vel = np.asarray(threat_vel, dtype=float)

    r_vec = threat_pos - effector_pos
    distance = float(np.linalg.norm(r_vec))
    if distance <= 1e-6:
        return _PHIT_CEILING

    threat_speed = float(np.linalg.norm(threat_vel))
    if is_kinematically_limited and threat_speed > float(effector_speed):
        # Positive projection means the threat is running away from us.
        u_los = r_vec / distance
        opening = float(threat_vel @ u_los) / max(threat_speed, 1e-9)
        if opening > _TAIL_CHASE_COS:
            return _PHIT_FLOOR

    ranged = 1.0 - (distance / _PHIT_RANGE_REF_M)
    return float(np.clip(ranged, _PHIT_FLOOR, _PHIT_CEILING))


class CostPerKillOptimizer:
    """Hungarian allocator over a mixed effector inventory with CPK weighting."""

    def __init__(self, w_tti: float = 0.4, w_phit: float = 0.3, w_cpk: float = 0.3):
        total = float(w_tti) + float(w_phit) + float(w_cpk)
        if total <= 0.0:
            raise ValueError("assignment weights must sum to a positive value")
        # Normalise so the combined cost stays on a comparable scale regardless
        # of how the caller expressed the weights.
        self.w_tti = float(w_tti) / total
        self.w_phit = float(w_phit) / total
        self.w_cpk = float(w_cpk) / total

    def build_cost_matrix(self, effectors, threats) -> np.ndarray:
        """Return an ``(n_effectors, n_threats)`` cost matrix.

        Infeasible pairs are ``inf``; ``hungarian_assignment`` treats those as
        unpickable and reports the threat as a leaker rather than forcing a
        hopeless engagement.
        """
        n_eff, n_thr = len(effectors), len(threats)
        cost = np.full((n_eff, n_thr), np.inf, dtype=float)

        for i, eff in enumerate(effectors):
            eff_pos = np.asarray(eff["pos"], dtype=float)
            eff_speed = float(eff.get("speed", 30.0))
            eff_cost = float(eff.get("cost", 500.0))
            limited = str(eff.get("type", "quad")) == "quad"
            if not bool(eff.get("available", True)):
                continue

            for j, thr in enumerate(threats):
                thr_pos = np.asarray(thr["pos"], dtype=float)
                thr_vel = np.asarray(thr.get("vel", (0.0, 0.0, 0.0)), dtype=float)
                thr_value = float(
                    thr.get("value", _DEFAULT_THREAT_VALUE_USD)
                )

                distance = float(np.linalg.norm(thr_pos - eff_pos))
                tti = distance / max(eff_speed, 1.0)

                p_hit = probability_of_hit(
                    eff_pos, eff_speed, thr_pos, thr_vel,
                    is_kinematically_limited=limited,
                )

                # Expected cost per kill: 1/p_hit shots are needed on average,
                # so a cheap effector that rarely connects is not actually
                # cheap. Scored against what the threat would destroy.
                expected_cost = eff_cost / max(p_hit, 1e-6)
                cpk_penalty = min(
                    expected_cost / max(thr_value, 1.0), _CPK_PENALTY_CAP
                )

                cost[i, j] = (
                    self.w_tti * (tti / _TTI_REF_S)
                    + self.w_phit * (1.0 - p_hit)
                    + self.w_cpk * cpk_penalty
                )

        return cost

    def solve(self, effectors, threats) -> Assignment:
        """Return the raw ``Assignment`` (threat index -> effector index)."""
        if not effectors or not threats:
            return Assignment(
                pairs={},
                leakers=list(range(len(threats))),
                reserves=list(range(len(effectors))),
            )
        return hungarian_assignment(self.build_cost_matrix(effectors, threats))

    def compute_assignment(self, effectors, threats) -> list:
        """Assignment records, ordered by threat index for determinism.

        Kept for callers that want dicts rather than the index-based
        ``Assignment``; ``solve`` is the lower-level entry point.
        """
        if not effectors or not threats:
            return []

        cost = self.build_cost_matrix(effectors, threats)
        assignment = hungarian_assignment(cost)

        records = []
        for threat_index in sorted(assignment.pairs):
            eff_index = assignment.pairs[threat_index]
            records.append({
                "effector_id": effectors[eff_index]["id"],
                "effector_type": effectors[eff_index].get("type", "quad"),
                "threat_id": threats[threat_index]["id"],
                "assigned_cost": float(cost[eff_index, threat_index]),
            })
        return records
