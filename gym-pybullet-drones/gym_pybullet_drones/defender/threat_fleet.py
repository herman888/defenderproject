"""Kinematic red-team threats: rocket, small swarm, or high-altitude dive."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pybullet as p


def _disable_vs_drones(body_id: int, client: int, drone_ids) -> None:
    for did in np.atleast_1d(drone_ids).flatten():
        p.setCollisionFilterPair(
            int(body_id), int(did), -1, -1, 0, physicsClientId=client
        )


def _load_sphere(client: int, pos, scale: float = 0.12) -> int:
    orn = p.getQuaternionFromEuler([0.0, 0.0, 0.0])
    try:
        bid = p.loadURDF(
            "sphere2.urdf",
            pos,
            orn,
            globalScaling=scale,
            physicsClientId=client,
        )
    except TypeError:
        bid = p.loadURDF("sphere2.urdf", pos, orn, physicsClientId=client)
    p.resetBasePositionAndOrientation(bid, pos, orn, physicsClientId=client)
    return int(bid)


@dataclass
class _Agent:
    body_id: int
    pos: np.ndarray
    vel: np.ndarray
    speed: float
    target: np.ndarray
    kind: str
    dive_phase: int = 0


class ThreatFleet:
    """Spawns and steps kinematic threats; does not collide with blue drones."""

    def __init__(self, physics_client_id: int, drone_ids):
        self.client = int(physics_client_id)
        self.drone_ids = drone_ids
        self.agents: list[_Agent] = []
        self.mode: str | None = None

    def clear(self) -> None:
        for a in self.agents:
            try:
                p.removeBody(a.body_id, physicsClientId=self.client)
            except Exception:
                pass
        self.agents = []
        self.mode = None

    def spawn(self, mode: str, vip_centroid: np.ndarray) -> None:
        """``mode`` in ``rocket | swarm | dive``."""
        self.clear()
        self.mode = mode
        c = np.asarray(vip_centroid, dtype=float).reshape(3).copy()
        c[2] = float(np.clip(c[2], 0.1, 0.45))

        if mode == "rocket":
            pos = np.array([0.95, 0.52, c[2] + 0.02], dtype=float)
            bid = _load_sphere(self.client, pos.tolist(), scale=0.09)
            _disable_vs_drones(bid, self.client, self.drone_ids)
            self.agents.append(
                _Agent(
                    body_id=bid,
                    pos=pos,
                    vel=np.zeros(3),
                    speed=0.42,
                    target=c.copy(),
                    kind="rocket",
                )
            )
        elif mode == "swarm":
            offs = [np.array([0.0, 0.0, 0.0]), np.array([0.07, -0.05, 0.02]), np.array([-0.06, -0.06, 0.01])]
            starts = [np.array([0.88, 0.42 + 0.05 * k, 0.16 + 0.02 * k]) for k in range(3)]
            for k in range(3):
                bid = _load_sphere(self.client, starts[k].tolist(), scale=0.065)
                _disable_vs_drones(bid, self.client, self.drone_ids)
                self.agents.append(
                    _Agent(
                        body_id=bid,
                        pos=starts[k].copy(),
                        vel=np.zeros(3),
                        speed=0.11,
                        target=c + offs[k],
                        kind="swarm",
                    )
                )
        elif mode == "dive":
            pos = np.array([0.1, 0.58, 0.92], dtype=float)
            bid = _load_sphere(self.client, pos.tolist(), scale=0.11)
            _disable_vs_drones(bid, self.client, self.drone_ids)
            self.agents.append(
                _Agent(
                    body_id=bid,
                    pos=pos,
                    vel=np.zeros(3),
                    speed=0.22,
                    target=np.array([c[0], c[1], 0.42], dtype=float),
                    kind="dive",
                    dive_phase=0,
                )
            )
        else:
            self.mode = None

    def is_active(self) -> bool:
        return len(self.agents) > 0

    def step(self, vip_positions: np.ndarray, dt: float) -> tuple[np.ndarray, np.ndarray]:
        """Integrate all agents; return aggregate position & mean velocity."""
        vip_positions = np.asarray(vip_positions, dtype=float).reshape(-1, 3)
        c = np.mean(vip_positions, axis=0)

        for a in self.agents:
            if a.kind == "rocket":
                self._steer_direct(a, a.target, dt)
            elif a.kind == "swarm":
                self._steer_direct(a, a.target, dt)
            elif a.kind == "dive":
                if a.dive_phase == 0:
                    self._steer_direct(a, a.target, dt)
                    if float(np.linalg.norm(a.pos[0:2] - c[0:2])) < 0.24:
                        a.dive_phase = 1
                        a.target = np.array([c[0], c[1], c[2] + 0.05], dtype=float)
                        a.speed = 0.28
                else:
                    self._steer_direct(a, a.target, dt)
            orn = p.getQuaternionFromEuler([0.0, 0.0, 0.0])
            try:
                p.resetBasePositionAndOrientation(
                    a.body_id, a.pos.tolist(), orn, physicsClientId=self.client
                )
            except Exception:
                pass

        if not self.agents:
            return np.zeros(3), np.zeros(3)
        poss = np.stack([x.pos for x in self.agents])
        vels = np.stack([x.vel for x in self.agents])
        return np.mean(poss, axis=0), np.mean(vels, axis=0)

    @staticmethod
    def _steer_direct(a: _Agent, goal: np.ndarray, dt: float) -> None:
        g = np.asarray(goal, dtype=float).reshape(3)
        dirv = g - a.pos
        n = float(np.linalg.norm(dirv))
        if n < 1e-7:
            a.vel[:] = 0.0
        else:
            a.vel = a.speed * dirv / n
        a.pos = a.pos + a.vel * dt
        a.pos[2] = float(np.clip(a.pos[2], 0.06, 1.05))

    def closest_to(self, point: np.ndarray) -> np.ndarray:
        """Nearest threat position to ``point`` (for camera / yaw)."""
        point = np.asarray(point, dtype=float).reshape(3)
        if not self.agents:
            return point.copy()
        d = [float(np.linalg.norm(a.pos - point)) for a in self.agents]
        j = int(np.argmin(d))
        return self.agents[j].pos.copy()

    def min_clearance_vips(self, vip_positions: np.ndarray) -> float:
        vip_positions = np.asarray(vip_positions, dtype=float).reshape(-1, 3)
        if not self.agents:
            return float("inf")
        best = float("inf")
        for v in vip_positions:
            for a in self.agents:
                best = min(best, float(np.linalg.norm(v - a.pos)))
        return best
