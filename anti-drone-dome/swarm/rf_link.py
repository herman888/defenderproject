"""Range-dependent RF link model for coordinator-to-interceptor command delivery.

Mirrors the link/latency/dropout structure of ``sensors/radar.py`` but for a one-way
command datalink. Free-space path loss for a one-way link scales as ``20*log10(R)``
(vs a radar's two-way ``40*log10(R)``). The model is deterministic given a seed.
"""

from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass

import numpy as np


def _positive(value, label: str, *, allow_zero: bool = False) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be numeric")
    value = float(value)
    if not math.isfinite(value):
        raise ValueError(f"{label} must be finite")
    if value < 0.0 or (value == 0.0 and not allow_zero):
        raise ValueError(f"{label} must be {'non-negative' if allow_zero else 'positive'}")
    return value


@dataclass(frozen=True)
class RfLinkConfig:
    """RF datalink parameters, typically sourced from a coordinator spec."""

    max_range_m: float = 4000.0
    link_budget_margin_db: float = 8.0
    loss_spread_db: float = 3.0
    base_latency_s: float = 0.05
    retx_penalty_s: float = 0.01
    update_rate_hz: float = 10.0

    def validate(self) -> None:
        _positive(self.max_range_m, "max_range_m")
        _positive(self.link_budget_margin_db, "link_budget_margin_db", allow_zero=True)
        _positive(self.loss_spread_db, "loss_spread_db")
        _positive(self.base_latency_s, "base_latency_s", allow_zero=True)
        _positive(self.retx_penalty_s, "retx_penalty_s", allow_zero=True)
        _positive(self.update_rate_hz, "update_rate_hz")

    @classmethod
    def from_dict(cls, data: dict) -> "RfLinkConfig":
        allowed = {f for f in cls.__dataclass_fields__}
        unknown = set(data) - allowed
        if unknown:
            raise ValueError(f"unknown RF link fields: {sorted(unknown)}")
        config = cls(**data)
        config.validate()
        return config


class RfLinkModel:
    """A single coordinator RF emitter shared across all interceptor links.

    ``margin_db`` is 0 dB at ``max_range_m`` and rises by 20 dB per range decade
    closer in, offset by a fixed ``link_budget_margin_db`` fade margin (the
    coordinator's "stronger RF"). Beyond ``max_range_m`` the link is hard-down.
    """

    def __init__(self, config: RfLinkConfig, seed: int | None = None):
        config.validate()
        self.config = config
        self._rng = np.random.default_rng(seed)

    def margin_db(self, range_m: float) -> float:
        r = max(float(range_m), 1.0)
        return self.config.link_budget_margin_db + 20.0 * math.log10(
            self.config.max_range_m / r
        )

    def packet_loss_probability(self, range_m: float) -> float:
        if float(range_m) > self.config.max_range_m:
            return 1.0
        margin = self.margin_db(range_m)
        # Logistic in the margin: ~0 loss with healthy margin, 0.5 at 0 dB, ->1 below.
        return 1.0 / (1.0 + math.exp(margin / self.config.loss_spread_db))

    def latency_s(self, range_m: float) -> float:
        margin = self.margin_db(range_m)
        # Retransmissions near/below the noise floor add delay.
        return self.config.base_latency_s + max(0.0, -margin) * self.config.retx_penalty_s

    def deliver(self, range_m: float) -> bool:
        """Roll one delivery attempt. Deterministic given the model's seed."""
        if float(range_m) > self.config.max_range_m:
            return False
        return self._rng.random() >= self.packet_loss_probability(range_m)


class InterceptorLink:
    """Per-interceptor delayed-delivery queue for coordinator orders.

    An order handed in at time ``t`` from range ``R`` is delivered at
    ``t + latency_s(R)`` if the delivery roll succeeds, else dropped. ``poll``
    returns the most recent order whose delivery time has arrived.
    """

    def __init__(self, model: RfLinkModel):
        self._model = model
        self._inflight: deque[tuple[float, object]] = deque()
        self.delivered = 0
        self.dropped = 0
        self.last_margin_db = float("-inf")
        self.last_delivered_time: float | None = None

    def offer(self, order, range_m: float, now: float) -> None:
        self.last_margin_db = self._model.margin_db(range_m)
        if self._model.deliver(range_m):
            arrival = now + self._model.latency_s(range_m)
            self._inflight.append((arrival, order))
            self.delivered += 1
        else:
            self.dropped += 1

    def poll(self, now: float):
        """Return the newest order that has arrived by ``now`` (or None)."""
        arrived = None
        while self._inflight and self._inflight[0][0] <= now:
            _, arrived = self._inflight.popleft()
        if arrived is not None:
            self.last_delivered_time = now
        return arrived

    def age_s(self, now: float) -> float:
        if self.last_delivered_time is None:
            return float("inf")
        return now - self.last_delivered_time
