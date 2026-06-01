"""
Drone: URDF loader + PD hover controller + rotor spin.

BEFORE: All drones shared global module-level constants
        (MAX_H_FORCE=15 N, MAX_V_FORCE=20 N, MAX_SPEED=15 m/s, KP=10, KD=5).
        Interceptor was identical in performance to intruder.

AFTER:  All force/speed/gain params are per-instance constructor arguments
        so the interceptor can be tuned independently.
        Interceptor defaults (set in main.py):
            max_h_force=40 N, max_v_force=40 N, max_speed=30 m/s, kp=15, kd=7
        Intruder keeps original defaults (15/20/15/10/5).
"""

import math
import os
import time
import pybullet
import numpy as np

_TIMESTEP    = 1.0 / 240.0
_ROTOR_SPEED = 20.0     # rad/s visual spin


class Drone:
    def __init__(
        self,
        drone_id: str,
        start_position: tuple,
        physics_client: int,
        color: str  = "gray",
        # --- tunable per-drone parameters ---
        max_h_force: float = 15.0,
        max_v_force: float = 20.0,
        max_speed:   float = 15.0,
        kp:          float = 10.0,
        kd:          float = 5.0,
    ):
        self._id_str    = drone_id
        self._client    = physics_client
        self._target    = list(start_position)
        self._prev_error = [0.0, 0.0, 0.0]
        self._rotor_angle = 0.0

        # Store per-instance dynamics params
        self._max_h  = max_h_force
        self._max_v  = max_v_force
        self._max_spd = max_speed
        self._kp     = kp
        self._kd     = kd

        urdf_path = os.path.normpath(
            os.path.join(os.path.dirname(__file__), "..", "assets", "drone.urdf")
        )
        try:
            self._body = pybullet.loadURDF(
                urdf_path,
                basePosition=list(start_position),
                physicsClientId=self._client,
            )
        except Exception:
            self._body = pybullet.loadURDF(
                "sphere2.urdf",
                basePosition=list(start_position),
                physicsClientId=self._client,
            )

        self._apply_color(color)
        self._rotor_joints = self._find_rotor_joints()

        label_color = [0.9, 0.15, 0.15] if color == "red" else [0.1, 0.5, 1.0]
        try:
            pybullet.addUserDebugText(
                drone_id.upper(), [0, 0, 1.2], label_color,
                textSize=1.5, physicsClientId=self._client,
                parentObjectUniqueId=self._body, parentLinkIndex=-1,
            )
        except Exception:
            pass

    # ------------------------------------------------------------------
    def _apply_color(self, color: str):
        rgba = {"red": [0.9,0.15,0.15,1.0], "blue": [0.1,0.3,0.9,1.0]}.get(
            color, [0.3,0.3,0.3,1.0]
        )
        n = pybullet.getNumJoints(self._body, physicsClientId=self._client)
        pybullet.changeVisualShape(self._body, -1, rgbaColor=rgba, physicsClientId=self._client)
        for i in range(n):
            pybullet.changeVisualShape(self._body, i, rgbaColor=rgba, physicsClientId=self._client)

    def _find_rotor_joints(self):
        joints = []
        n = pybullet.getNumJoints(self._body, physicsClientId=self._client)
        for i in range(n):
            info = pybullet.getJointInfo(self._body, i, physicsClientId=self._client)
            if info[2] == pybullet.JOINT_REVOLUTE:
                joints.append(i)
        return joints

    # ------------------------------------------------------------------
    def set_target(self, x: float, y: float, z: float):
        self._target = [x, y, z]

    def update(self):
        pos, _ = pybullet.getBasePositionAndOrientation(self._body, physicsClientId=self._client)
        vel, _ = pybullet.getBaseVelocity(self._body, physicsClientId=self._client)
        fx, fy, fz = self._compute_forces(pos, vel)
        pybullet.applyExternalForce(
            self._body, -1, [fx, fy, fz], pos, pybullet.WORLD_FRAME,
            physicsClientId=self._client,
        )
        self._spin_rotors()

    def _compute_forces(self, pos, vel):
        err   = [self._target[i] - pos[i] for i in range(3)]
        d_err = [(err[i] - self._prev_error[i]) / _TIMESTEP for i in range(3)]
        self._prev_error = err

        fx = self._kp * err[0] + self._kd * d_err[0]
        fy = self._kp * err[1] + self._kd * d_err[1]
        fz = self._kp * err[2] + self._kd * d_err[2] + 9.81 * 1.5   # gravity comp

        h_mag = math.sqrt(fx*fx + fy*fy)
        if h_mag > self._max_h:
            fx = fx / h_mag * self._max_h
            fy = fy / h_mag * self._max_h
        fz = max(-self._max_v, min(self._max_v + 9.81*1.5, fz))

        speed = math.sqrt(sum(v*v for v in vel))
        if speed > self._max_spd:
            scale = self._max_spd / speed
            pybullet.resetBaseVelocity(
                self._body,
                [v * scale for v in vel],
                [0, 0, 0],
                physicsClientId=self._client,
            )

        return fx, fy, fz

    def _spin_rotors(self):
        self._rotor_angle += _ROTOR_SPEED * _TIMESTEP
        for i, joint in enumerate(self._rotor_joints):
            pybullet.setJointMotorControl2(
                self._body, joint, pybullet.VELOCITY_CONTROL,
                targetVelocity=(1 if i % 2 == 0 else -1) * _ROTOR_SPEED,
                force=0.1,
                physicsClientId=self._client,
            )

    # ------------------------------------------------------------------
    def get_position(self) -> tuple:
        pos, _ = pybullet.getBasePositionAndOrientation(self._body, physicsClientId=self._client)
        return tuple(pos)

    def get_velocity(self) -> tuple:
        vel, _ = pybullet.getBaseVelocity(self._body, physicsClientId=self._client)
        return tuple(vel)

    def get_state(self) -> dict:
        pos = self.get_position()
        vel = self.get_velocity()
        _, orn = pybullet.getBasePositionAndOrientation(self._body, physicsClientId=self._client)
        return {
            "position"   : pos,
            "velocity"   : vel,
            "orientation": tuple(orn),
            "timestamp"  : time.time(),
            "target"     : tuple(self._target),
            "speed"      : math.sqrt(sum(v*v for v in vel)),
        }
