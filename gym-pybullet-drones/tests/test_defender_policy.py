"""Unit tests for defender policy (no PyBullet)."""

import numpy as np

from gym_pybullet_drones.defender.policy import DefenderPolicy, DefenderPolicyConfig


def test_defender_roles_and_shapes():
    cfg = DefenderPolicyConfig(num_assets=2)
    pol = DefenderPolicy(cfg)
    n = 4
    pos = np.array(
        [
            [0.0, -0.32, 0.12],
            [0.15, -0.32, 0.12],
            [-0.2, -0.6, 0.15],
            [0.2, -0.6, 0.15],
        ]
    )
    hold = pos[:2].copy()
    ip = np.array([0.5, 0.0, 0.2])
    iv = np.array([-0.1, 0.0, 0.0])
    targets, roles = pol.compute_targets(pos, ip, iv, hold, sim_time=0.5, threat_active=True)
    assert targets.shape == (n, 3)
    assert len(roles) == n
    assert roles[0] == "VIP (hold)"
    assert roles[1] == "VIP (hold)"
    assert "intercept" in roles[2] or "intercept" in roles[3]
    np.testing.assert_allclose(targets[0], hold[0])
    np.testing.assert_allclose(targets[1], hold[1])


def test_single_defender_intercept_only():
    cfg = DefenderPolicyConfig(num_assets=2)
    pol = DefenderPolicy(cfg)
    n = 3
    pos = np.zeros((n, 3))
    pos[0] = [0, 0, 0.12]
    pos[1] = [0.1, 0, 0.12]
    pos[2] = [-0.2, -0.2, 0.15]
    hold = pos[:2].copy()
    ip = np.array([0.4, 0.2, 0.2])
    iv = np.zeros(3)
    targets, roles = pol.compute_targets(pos, ip, iv, hold, sim_time=0.0, threat_active=True)
    assert roles[2] == "defend (intercept)"


def test_patrol_when_no_threat():
    cfg = DefenderPolicyConfig(num_assets=2)
    pol = DefenderPolicy(cfg)
    n = 3
    pos = np.ones((n, 3)) * 0.1
    hold = np.array([[0, 0, 0.12], [0.1, 0, 0.12]], dtype=float)
    targets, roles = pol.compute_targets(
        pos, np.zeros(3), np.zeros(3), hold, sim_time=0.0, threat_active=False
    )
    assert "patrol" in roles[2]
    assert targets.shape == (n, 3)

