"""The swarm coordination brain: assignment + RF command delivery + re-tasking.

Substrate independent — consumes plain ENU state dicts (the same shape as
``Drone.get_state()``), never imports PyBullet. Reused by the headless runner and
by the optional PyBullet path in ``main.py``.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from guidance.intercept import PurePursuitGuidance
from swarm.assignment import (
    build_cost_matrix,
    greedy_priority_assignment,
    hungarian_assignment,
    threat_priority,
)
from swarm.rf_link import InterceptorLink, RfLinkModel

# Per-interceptor command/link states.
ASSIGNED = "ASSIGNED"                 # fresh coordinator order, link healthy
COASTING = "COASTING"                 # link stale, still pursuing last order
AUTONOMOUS_LOCAL = "AUTONOMOUS_LOCAL"  # link lost and last target gone; self-selecting
RESERVE = "RESERVE"                   # no active threat to service


@dataclass(frozen=True)
class InterceptorOrder:
    assigned_threat_id: str | None
    state: str
    link_margin_db: float
    link_age_s: float


@dataclass(frozen=True)
class SwarmPlan:
    orders: dict                 # interceptor_id -> InterceptorOrder
    assignment: dict             # threat_id -> interceptor_id (coordinator intent)
    leakers: list                # threat_ids with no interceptor assigned
    link_health: dict


class _InterceptorLinkState:
    __slots__ = ("link", "desired_threat", "desired_since", "last_offer_time",
                 "effective_threat")

    def __init__(self, link: InterceptorLink):
        self.link = link
        self.desired_threat: str | None = None
        self.desired_since: float = 0.0
        self.last_offer_time: float = float("-inf")
        self.effective_threat: str | None = None


class SwarmCoordinator:
    """Airborne coordinator that assigns a swarm of interceptors to threats."""

    def __init__(
        self,
        rf_model: RfLinkModel,
        *,
        protected_center=(0.0, 0.0, 0.0),
        guidance: PurePursuitGuidance | None = None,
        policy: str = "greedy",
        reassign_margin: float = 0.15,
        min_dwell_s: float = 1.0,
        link_timeout_s: float = 0.5,
    ):
        if policy not in ("greedy", "hungarian"):
            raise ValueError("policy must be 'greedy' or 'hungarian'")
        self.rf_model = rf_model
        self.protected_center = tuple(float(c) for c in protected_center)
        self.guidance = guidance or PurePursuitGuidance()
        self.policy = policy
        self.reassign_margin = float(reassign_margin)
        self.min_dwell_s = float(min_dwell_s)
        self.link_timeout_s = float(link_timeout_s)
        self._offer_interval_s = 1.0 / rf_model.config.update_rate_hz
        self._links: dict[str, _InterceptorLinkState] = {}

    def _link_state(self, interceptor_id: str) -> _InterceptorLinkState:
        state = self._links.get(interceptor_id)
        if state is None:
            state = _InterceptorLinkState(InterceptorLink(self.rf_model))
            self._links[interceptor_id] = state
        return state

    def _fresh_assignment(self, interceptor_states, threat_tracks):
        cost = build_cost_matrix(interceptor_states, threat_tracks, self.guidance)
        priorities = [
            threat_priority(threat, self.protected_center) for threat in threat_tracks
        ]
        threat_ids = [t["id"] for t in threat_tracks]
        interceptor_ids = [i["id"] for i in interceptor_states]
        if self.policy == "hungarian":
            result = hungarian_assignment(cost)
        else:
            result = greedy_priority_assignment(
                cost, priorities, threat_ids, interceptor_ids
            )
        return cost, result

    def plan(self, coordinator_state, interceptor_states, threat_tracks, t) -> SwarmPlan:
        coord_pos = np.asarray(coordinator_state["position"], dtype=float)
        active_ids = {threat["id"] for threat in threat_tracks}
        threat_by_id = {threat["id"]: threat for threat in threat_tracks}
        interceptor_index = {i["id"]: idx for idx, i in enumerate(interceptor_states)}

        cost, result = self._fresh_assignment(interceptor_states, threat_tracks)
        threat_ids = [threat["id"] for threat in threat_tracks]
        # Proposed desired target per interceptor id, from the fresh assignment.
        proposed: dict[str, str | None] = {i["id"]: None for i in interceptor_states}
        for threat_idx, inter_idx in result.pairs.items():
            proposed[interceptor_states[inter_idx]["id"]] = threat_ids[threat_idx]

        orders: dict[str, InterceptorOrder] = {}
        for interceptor in interceptor_states:
            iid = interceptor["id"]
            link_state = self._link_state(iid)

            # ── Hysteresis on the coordinator's *desired* target ──────────────
            current = link_state.desired_threat
            new_target = proposed[iid]
            keep = False
            if current is not None and current in active_ids:
                if new_target is None or new_target == current:
                    keep = True
                else:
                    # Only switch if the new target beats the current by margin
                    # and the minimum dwell has elapsed.
                    ii = interceptor_index[iid]
                    ci = threat_ids.index(current)
                    ni = threat_ids.index(new_target)
                    cur_cost = cost[ii, ci]
                    new_cost = cost[ii, ni]
                    dwell_ok = (t - link_state.desired_since) >= self.min_dwell_s
                    improves = new_cost < cur_cost * (1.0 - self.reassign_margin)
                    keep = not (dwell_ok and improves)
            chosen = current if keep else new_target
            if chosen != link_state.desired_threat:
                link_state.desired_threat = chosen
                link_state.desired_since = t

            # ── Transmit the order over the RF link at the datalink rate ──────
            if chosen is not None and (
                t - link_state.last_offer_time >= self._offer_interval_s
            ):
                inter_pos = np.asarray(interceptor["position"], dtype=float)
                rng = float(np.linalg.norm(inter_pos - coord_pos))
                link_state.link.offer(chosen, rng, t)
                link_state.last_offer_time = t

            delivered = link_state.link.poll(t)
            if delivered is not None:
                link_state.effective_threat = delivered

            # ── Resolve the effective target + link state ─────────────────────
            age = link_state.link.age_s(t)
            healthy = age <= self.link_timeout_s
            eff = link_state.effective_threat
            if eff is not None and eff not in active_ids:
                eff = None

            if healthy:
                resolved = eff if eff is not None else (
                    chosen if chosen in active_ids else None
                )
                state = ASSIGNED if resolved is not None else RESERVE
            elif eff is not None:
                resolved, state = eff, COASTING
            else:
                resolved = self._nearest_active(interceptor, threat_tracks)
                state = AUTONOMOUS_LOCAL if resolved is not None else RESERVE

            orders[iid] = InterceptorOrder(
                assigned_threat_id=resolved,
                state=state,
                link_margin_db=link_state.link.last_margin_db,
                link_age_s=age,
            )

        assignment = {
            tid: interceptor_states[inter_idx]["id"]
            for tid, inter_idx in (
                (threat_ids[j], i) for j, i in result.pairs.items()
            )
        }
        leakers = [threat_ids[j] for j in result.leakers]
        link_health = self._link_health(orders)
        return SwarmPlan(
            orders=orders, assignment=assignment, leakers=leakers,
            link_health=link_health,
        )

    @staticmethod
    def _nearest_active(interceptor, threat_tracks):
        if not threat_tracks:
            return None
        pos = np.asarray(interceptor["position"], dtype=float)
        best_id, best_d = None, float("inf")
        for threat in threat_tracks:
            d = float(np.linalg.norm(np.asarray(threat["position_estimate"]) - pos))
            if d < best_d:
                best_d, best_id = d, threat["id"]
        return best_id

    def _link_health(self, orders) -> dict:
        delivered = sum(s.link.delivered for s in self._links.values())
        dropped = sum(s.link.dropped for s in self._links.values())
        in_link = sum(
            1 for o in orders.values() if o.state in (ASSIGNED, RESERVE)
        )
        lost = sum(
            1 for o in orders.values() if o.state in (COASTING, AUTONOMOUS_LOCAL)
        )
        total = delivered + dropped
        return {
            "packets_delivered": delivered,
            "packets_dropped": dropped,
            "delivery_ratio": (delivered / total) if total else 1.0,
            "interceptors_in_link": in_link,
            "interceptors_lost_link": lost,
        }
