"""Swept-collision geometry and env/report consistency.

`test_env_info_matches_termination_regression` pins a bug that cost real
measured intercepts: `step()` terminated on a swept contact while `_info()`
recomputed an endpoint-only check, so a genuine hit whose sampled endpoint
separation was still outside the contact radius got reported as a miss and the
regression campaign scored it as a failure.
"""

from __future__ import annotations

import os
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import INTERCEPT_CONTACT_RADIUS_M  # noqa: E402
from ml.controllers import APNController  # noqa: E402
from ml.environment import InterceptionEnv  # noqa: E402
from sim.collision import closest_approach, swept_contact  # noqa: E402


# --------------------------------------------------------------------------
# Geometry
# --------------------------------------------------------------------------

def test_straight_through_pass_has_zero_closest_approach():
    distance, fraction = closest_approach([0.0, 5.0, 0.0], [0.0, -5.0, 0.0])
    assert distance == pytest.approx(0.0, abs=1e-9)
    assert 0.0 <= fraction <= 1.0


def test_closest_approach_never_exceeds_either_endpoint():
    rng = np.random.default_rng(3)
    for _ in range(200):
        start = rng.uniform(-50, 50, 3)
        end = rng.uniform(-50, 50, 3)
        distance, fraction = closest_approach(start, end)
        assert distance <= np.linalg.norm(start) + 1e-9
        assert distance <= np.linalg.norm(end) + 1e-9
        assert 0.0 <= fraction <= 1.0


def test_stationary_relative_motion_returns_endpoint():
    distance, fraction = closest_approach([3.0, 4.0, 0.0], [3.0, 4.0, 0.0])
    assert distance == pytest.approx(5.0)
    assert fraction == 0.0


def test_swept_contact_is_a_superset_of_the_endpoint_test():
    """Anything an endpoint check catches, the swept check must also catch."""
    rng = np.random.default_rng(11)
    radius = 1.0
    for _ in range(300):
        chaser_start = rng.uniform(-20, 20, 3)
        chaser_end = chaser_start + rng.uniform(-6, 6, 3)
        target_start = rng.uniform(-20, 20, 3)
        target_end = target_start + rng.uniform(-3, 3, 3)
        endpoint_hit = np.linalg.norm(target_end - chaser_end) <= radius
        hit, distance, _ = swept_contact(
            chaser_start, chaser_end, target_start, target_end, radius
        )
        if endpoint_hit:
            assert hit
        assert distance <= np.linalg.norm(target_end - chaser_end) + 1e-9


def test_fast_pass_through_is_detected():
    """A body crossing the target in one step must register.

    Endpoint-only testing misses this: both endpoints are 5 m out, but the
    path goes straight through the target.
    """
    hit, distance, _ = swept_contact(
        [0.0, -5.0, 0.0], [0.0, 5.0, 0.0],   # chaser sweeps through origin
        [0.0, 0.0, 0.0], [0.0, 0.0, 0.0],    # stationary target
        1.0,
    )
    assert hit
    assert distance == pytest.approx(0.0, abs=1e-9)


# --------------------------------------------------------------------------
# Environment consistency
# --------------------------------------------------------------------------

def _run_episode(seed: int):
    env = InterceptionEnv(
        pattern="direct",
        intruder_type="shahed136",
        domain_randomization=True,
        observation_version="v2",
    )
    controller = APNController()
    observation, info = env.reset(seed=seed)
    terminated = truncated = False
    while not (terminated or truncated):
        observation, _r, terminated, truncated, info = env.step(
            controller.predict(observation, env)
        )
    return env, info, terminated


def test_env_info_matches_termination_regression():
    """`info['intercepted']` must agree with what actually ended the episode.

    Recomputing an endpoint-only check in `_info()` disagreed with the swept
    termination test, so real hits were reported as misses.
    """
    for seed in range(1000, 1006):
        env, info, terminated = _run_episode(seed)
        assert info["intercepted"] == env._intercepted
        if info["intercepted"]:
            assert terminated


def test_intercept_flag_is_false_before_any_step():
    env = InterceptionEnv(pattern="direct", intruder_type="shahed136")
    _observation, info = env.reset(seed=7)
    assert info["intercepted"] is False


def test_reset_clears_a_previous_intercept():
    env, info, _ = _run_episode(1000)
    env.reset(seed=1001)
    assert env._intercepted is False


def test_reported_intercept_implies_true_contact():
    """A reported intercept must correspond to an actual sub-radius approach."""
    for seed in range(1000, 1006):
        env, info, _ = _run_episode(seed)
        if info["intercepted"]:
            separation = float(
                np.linalg.norm(env.intruder_position - env.interceptor_position)
            )
            # Endpoint separation may exceed the radius on a swept hit, but not
            # by more than the distance travelled in one step.
            step_travel = float(
                np.linalg.norm(env.interceptor_velocity) * env.dt
                + np.linalg.norm(env.intruder_velocity) * env.dt
            )
            assert separation <= INTERCEPT_CONTACT_RADIUS_M + step_travel + 1e-6
