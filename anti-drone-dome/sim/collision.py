"""Swept (continuous) collision tests for fast-closing engagements.

Endpoint-only hit tests silently miss intercepts whenever a body advances
further in one timestep than the contact radius it is being tested against.
That condition is the norm here, not an edge case:

    closing speed 118 m/s x dt 0.05 s = 5.9 m per step
    contact radius                    = 1.0 m

so an interceptor can pass clean through its target between two samples and
register nothing. The sampled minimum separation then reports a near-miss of
one or two metres for what was physically a hit.

These helpers test the *path* travelled during a step rather than its
endpoints, assuming linear relative motion across the interval - which is the
correct assumption at the timestep scales used here.
"""

from __future__ import annotations

import numpy as np


def closest_approach(rel_start, rel_end):
    """Minimum separation over one step of linear relative motion.

    ``rel_start`` and ``rel_end`` are the target-minus-chaser vectors at the
    start and end of the step. Returns ``(distance_m, fraction)`` where
    ``fraction`` in [0, 1] locates the closest approach within the step.
    """
    start = np.asarray(rel_start, dtype=float)
    end = np.asarray(rel_end, dtype=float)
    delta = end - start
    denom = float(delta @ delta)
    if denom <= 1e-12:
        return float(np.linalg.norm(start)), 0.0
    s = -float(start @ delta) / denom
    s = min(max(s, 0.0), 1.0)
    return float(np.linalg.norm(start + s * delta)), s


def swept_contact(
    chaser_start,
    chaser_end,
    target_start,
    target_end,
    contact_radius_m: float,
):
    """Did the pair come within ``contact_radius_m`` at any point in the step?

    Returns ``(hit, min_distance_m, fraction)``.
    """
    rel_start = np.asarray(target_start, dtype=float) - np.asarray(chaser_start, dtype=float)
    rel_end = np.asarray(target_end, dtype=float) - np.asarray(chaser_end, dtype=float)
    distance, fraction = closest_approach(rel_start, rel_end)
    return distance <= float(contact_radius_m), distance, fraction
