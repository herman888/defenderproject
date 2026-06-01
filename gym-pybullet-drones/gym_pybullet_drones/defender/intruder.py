"""Kinematic intruder visualized in PyBullet (no physical interaction with drones)."""

from __future__ import annotations

import numpy as np
import pybullet as p


class KinematicIntruder:
    """Moves toward the centroid of VIP positions, then loiters in a small orbit.

    The body is teleported each control step so it does not disturb drone dynamics.
    Collisions with drones are disabled via collision filter pairs.
    """

    def __init__(
        self,
        client: int,
        start_xyz,
        drone_ids,
        speed_m_s: float = 0.18,
        urdf: str = "sphere2.urdf",
    ):
        self.client = int(client)
        self.speed = float(speed_m_s)
        self.pos = np.asarray(start_xyz, dtype=float).reshape(3).copy()
        self.vel = np.zeros(3, dtype=float)
        self._orbit_phase = 0.0
        orn = p.getQuaternionFromEuler([0.0, 0.0, 0.0])
        try:
            self.body_id = p.loadURDF(
                urdf,
                self.pos.tolist(),
                orn,
                globalScaling=0.14,
                physicsClientId=self.client,
            )
        except TypeError:
            self.body_id = p.loadURDF(
                urdf,
                self.pos.tolist(),
                orn,
                physicsClientId=self.client,
            )
        p.resetBasePositionAndOrientation(
            self.body_id, self.pos.tolist(), orn, physicsClientId=self.client
        )
        #### Ghost: do not collide with quadcopters (still visible) ################
        if drone_ids is not None:
            for did in np.atleast_1d(drone_ids).flatten():
                p.setCollisionFilterPair(
                    int(self.body_id),
                    int(did),
                    -1,
                    -1,
                    0,
                    physicsClientId=self.client,
                )
        #### Reduce residual dynamics (teleport-driven "actor") ###################
        p.changeDynamics(
            self.body_id,
            -1,
            mass=0.001,
            linearDamping=10,
            angularDamping=10,
            physicsClientId=self.client,
        )

    def step(self, vip_positions: np.ndarray, dt: float) -> tuple[np.ndarray, np.ndarray]:
        """Advance intruder toward VIP centroid; loiter when close.

        Parameters
        ----------
        vip_positions : (A, 3) ndarray
            World positions of asset / VIP drones.
        dt : float
            Control timestep in seconds.

        Returns
        -------
        pos, vel : (3,) ndarrays
            Intruder position and approximate velocity for lead pursuit.
        """
        vip_positions = np.asarray(vip_positions, dtype=float).reshape(-1, 3)
        center = np.mean(vip_positions, axis=0)
        to_c = center - self.pos
        dist = float(np.linalg.norm(to_c))
        if dist < 0.30:
            self._orbit_phase += 1.35 * dt
            desired = center + 0.16 * np.array(
                [np.cos(self._orbit_phase), np.sin(self._orbit_phase), 0.0],
                dtype=float,
            )
            direction = desired - self.pos
        else:
            direction = to_c
        n = float(np.linalg.norm(direction))
        if n < 1e-7:
            self.vel[:] = 0.0
        else:
            self.vel = self.speed * direction / n
        self.pos = self.pos + self.vel * dt
        #### Keep a modest flight height #########################################
        self.pos[2] = float(np.clip(self.pos[2], 0.08, 0.55))
        orn = p.getQuaternionFromEuler([0.0, 0.0, 0.0])
        p.resetBasePositionAndOrientation(
            self.body_id, self.pos.tolist(), orn, physicsClientId=self.client
        )
        return self.pos.copy(), self.vel.copy()

    def remove(self) -> None:
        try:
            p.removeBody(self.body_id, physicsClientId=self.client)
        except Exception:
            pass
