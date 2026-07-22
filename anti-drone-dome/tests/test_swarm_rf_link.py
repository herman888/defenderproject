"""Tests for the coordinator-to-interceptor RF link model."""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from swarm.rf_link import InterceptorLink, RfLinkConfig, RfLinkModel


def _model(**overrides):
    base = dict(max_range_m=1000.0, link_budget_margin_db=0.0, loss_spread_db=3.0)
    base.update(overrides)
    return RfLinkModel(RfLinkConfig(**base), seed=7)


def test_margin_decreases_with_range():
    model = _model()
    margins = [model.margin_db(r) for r in (10, 100, 500, 999)]
    assert margins == sorted(margins, reverse=True)


def test_margin_zero_at_max_range_with_zero_budget():
    model = _model()
    assert model.margin_db(1000.0) == pytest.approx(0.0, abs=1e-9)
    # With margin 0 and a logistic loss, edge-of-range loss is 0.5.
    assert model.packet_loss_probability(1000.0) == pytest.approx(0.5, abs=1e-9)


def test_loss_increases_with_range():
    model = _model()
    assert model.packet_loss_probability(50.0) < model.packet_loss_probability(900.0)


def test_beyond_max_range_is_hard_down():
    model = _model()
    assert model.packet_loss_probability(1500.0) == 1.0
    assert all(model.deliver(1500.0) is False for _ in range(20))


def test_deliver_is_deterministic_with_seed():
    a = _model()
    b = _model()
    seq_a = [a.deliver(700.0) for _ in range(50)]
    seq_b = [b.deliver(700.0) for _ in range(50)]
    assert seq_a == seq_b
    # Close range with margin should almost always deliver.
    assert sum(_model().deliver(20.0) for _ in range(100)) >= 95


def test_latency_grows_past_the_edge():
    model = _model()
    assert model.latency_s(20.0) == pytest.approx(model.config.base_latency_s)
    assert model.latency_s(3000.0) > model.latency_s(20.0)


def test_interceptor_link_delivers_after_latency():
    model = _model(base_latency_s=0.1, retx_penalty_s=0.0)
    link = InterceptorLink(model)
    link.offer("threat-a", range_m=20.0, now=0.0)
    # Delivered but not yet arrived.
    assert link.poll(0.05) is None
    assert link.poll(0.11) == "threat-a"
    assert link.delivered == 1 and link.dropped == 0


def test_interceptor_link_drops_out_of_range():
    model = _model()
    link = InterceptorLink(model)
    link.offer("threat-a", range_m=5000.0, now=0.0)
    assert link.dropped == 1
    assert link.poll(10.0) is None
    assert link.age_s(10.0) == float("inf")


def test_rf_config_rejects_bad_values():
    with pytest.raises(ValueError):
        RfLinkConfig(max_range_m=-1.0).validate()
    with pytest.raises(ValueError):
        RfLinkConfig.from_dict({"max_range_m": 1000.0, "unknown": 1})
