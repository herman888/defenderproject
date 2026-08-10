"""Regression checks for the fixed-wing pop-up attack route."""

from __future__ import annotations

import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scenarios import ATTACK_PATTERNS, get_waypoints_for_path
from sim.airframe_profiles import get_airframe_profile


def test_shahed_pop_up_route_respects_representative_climb_envelope():
    """A fixed-wing route must not demand a climb it cannot physically make.

    The prior route asked the representative Shahed to gain 158 m in 157 m
    horizontally: a 46 degree climb that exceeds its 5 m/s climb envelope at
    51 m/s cruise.  The controller then had no feasible path and circled back
    toward the vertical waypoint.  Keep every climbing leg within the
    profile's published representative envelope.
    """
    profile = get_airframe_profile("intruder.shahed136.representative-v1")
    propulsion = profile["propulsion"]
    envelope = profile["flight_envelope"]
    max_climb_slope = (
        float(envelope["max_climb_rate_mps"])
        / float(propulsion["cruise_speed_mps"])
    )
    waypoints = get_waypoints_for_path(ATTACK_PATTERNS["pop_up"]["path"])

    for start, end in zip(waypoints, waypoints[1:]):
        horizontal_distance = math.dist(start[:2], end[:2])
        climb = max(float(end[2] - start[2]), 0.0)
        if climb:
            assert climb / horizontal_distance <= max_climb_slope
