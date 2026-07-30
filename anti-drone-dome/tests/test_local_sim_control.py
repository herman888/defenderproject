"""Regression coverage for loopback-only simulation controls."""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from integration.local_sim_control import (  # noqa: E402
    LocalSimulationControlReceiver,
    SCHEMA,
    validate_command,
)


def test_accepts_only_whitelisted_simulation_actions():
    assert validate_command({"schema": SCHEMA, "action": "pause_toggle"}) == {
        "action": "pause_toggle"
    }
    assert validate_command({"schema": SCHEMA, "action": "set_speed", "speed": 4}) == {
        "action": "set_speed", "speed": 4.0
    }
    assert validate_command({
        "schema": SCHEMA, "action": "toggle_failure", "failure": "radar"
    }) == {"action": "toggle_failure", "failure": "radar"}
    assert validate_command({"schema": SCHEMA, "action": "next_preset"}) == {
        "action": "next_preset"
    }
    with pytest.raises(ValueError):
        validate_command({"schema": SCHEMA, "action": "arm"})
    with pytest.raises(ValueError):
        validate_command({"schema": SCHEMA, "action": "set_speed", "speed": 3})
    with pytest.raises(ValueError):
        validate_command({
            "schema": SCHEMA, "action": "toggle_failure", "failure": "weapon"
        })


def test_receiver_refuses_non_loopback_bindings():
    with pytest.raises(ValueError):
        LocalSimulationControlReceiver("0.0.0.0", 8789)
