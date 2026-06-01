"""Drone class: loads URDF, applies PD hover + 3D navigation forces, spins rotors."""

import math
import os
import time
import pybullet
import numpy as np

_TIMESTEP = 1.0 / 240.0
_KP = 10.0
_KD = 5.0
_MAX_H_FORCE = 15.0
_MAX_V_FORCE = 20.0
_MAX_SPEED = 15.0
_ROTOR_SPEED = 20.0  # rad/s visual spin


class Drone:
    def __init__(self, drone_id: str, start_position: tuple, physics_client: int, color: str = "gray"):
        self._id_str = drone_id
        self._client = physics_client
        self._target = list(start_position)
        self._prev_error = [0.0, 0.0, 0.0]
        self._rotor_angle = 0.0

        urdf_path = os.path.join(os.path.dirname(__file__), "..", "assets", "drone.urdf")
        urdf_path = os.path.normpath(urdf_path)

        try:
            self._body = pybullet.loadURDF(
                urdf_path,
                basePosition=list(start_position),
                physicsClientId=self._client,
            )
        except Exception:
            import pybullet_data
            self._body = pybullet.loadURDF(
                "sphere2.urdf",
                basePosition=list(start_position),
                physicsClientId=self._client,
            )

        self._apply_color(color)
        self._rotor_joints = self._find_rotor_joints()
        self._label_color = [0.9, 0.15, 0.15] if color == "red" else [0.1, 0.5, 1.0]
        self._label_id = pybullet.addUserDebugText(
            drone_id.upper(), [0, 0, 1.2], self._label_color,
            textSize=1.5, physicsClientId=self._client,
            parentObjectUniqueId=self._body, parentLinkIndex=-1,
        )

    def _apply_color(self, color: str):
        if color == "red":
            rgba = [0.9, 0.15, 0.15, 1.0]
        elif color == "blue":
            rgba = [0.1, 0.3, 0.9, 1.0]
        else:
            rgba = [0.3, 0.3, 0.3, 1.0]
        n_links = pybullet.getNumJoints(self._body, physicsClientId=self._client)
        pybullet.changeVisualShape(self._body, -1, rgbaColor=rgba, physicsClientId=self._client)
        for i in range(n_links):
            pybullet.changeVisualShape(self._body, i, rgbaColor=rgba, physicsClientId=self._client)

    def _find_rotor_joints(self):
        joints = []
        n = pybullet.getNumJoints(self._body, physicsClientId=self._client)
        for i in range(n):
            info = pybullet.getJointInfo(self._body, i, physicsClientId=self._client)
            if info[2] == pybullet.JOINT_REVOLUTE:
                joints.append(i)
        return joints

    def set_target(self, x: float, y: float, z: float):
        self._target = [x, y, z]

    def update(self):
        pos, _ = pybullet.getBasePositionAndOrientation(self._body, physicsClientId=self._client)
        vel, _ = pybullet.getBaseVelocity(self._body, physicsClientId=self._client)

        fx, fy, fz = self._compute_forces(pos, vel)
        pybullet.applyExternalForce(
            self._body, -1, [fx, fy, fz], pos, pybullet.WORLD_FRAME, physicsClientId=self._client
        )
        self._spin_rotors()

    def _compute_forces(self, pos, vel):
        err = [self._target[i] - pos[i] for i in range(3)]
        d_err = [(err[i] - self._prev_error[i]) / _TIMESTEP for i in range(3)]
        self._prev_error = err

        fx = _KP * err[0] + _KD * d_err[0]
        fy = _KP * err[1] + _KD * d_err[1]
        fz = _KP * err[2] + _KD * d_err[2]

        # Gravity compensation on vertical
        fz += 9.81 * 1.5  # mass * g

        h_mag = math.sqrt(fx * fx + fy * fy)
        if h_mag > _MAX_H_FORCE:
            fx = fx / h_mag * _MAX_H_FORCE
            fy = fy / h_mag * _MAX_H_FORCE
        fz = max(-_MAX_V_FORCE, min(_MAX_V_FORCE + 9.81 * 1.5, fz))

        # Speed cap via velocity damping
        speed = math.sqrt(sum(v * v for v in vel))
        if speed > _MAX_SPEED:
            scale = _MAX_SPEED / speed
            vel_arr = list(vel)
            pybullet.resetBaseVelocity(
                self._body,
                [v * scale for v in vel_arr],
                [0, 0, 0],
                physicsClientId=self._client,
            )

        return fx, fy, fz

    def _spin_rotors(self):
        self._rotor_angle += _ROTOR_SPEED * _TIMESTEP
        for i, joint in enumerate(self._rotor_joints):
            direction = 1 if i % 2 == 0 else -1
            pybullet.setJointMotorControl2(
                self._body,
                joint,
                pybullet.VELOCITY_CONTROL,
                targetVelocity=direction * _ROTOR_SPEED,
                force=0.1,
                physicsClientId=self._client,
            )

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
            "position": pos,
            "velocity": vel,
            "orientation": tuple(orn),
            "timestamp": time.time(),
            "target": tuple(self._target),
            "speed": math.sqrt(sum(v * v for v in vel)),
        }
