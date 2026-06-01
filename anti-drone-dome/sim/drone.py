"""
Drone: VTOL quadrotor — tilts body toward thrust direction, applies force along body-Z.
LoiteringMunition: horizontal-fuselage forward-flyer, nose always tracks velocity.
"""

import math
import os
import time
import pybullet
import numpy as np

_TIMESTEP    = 1.0 / 240.0
_ROTOR_SPEED = 20.0   # rad/s visual spin (quadrotor)

# Aerodynamic constants (loitering munition)
_RHO = 1.225   # kg/m³ air density
_CD  = 0.30    # drag coefficient
_A   = 0.050   # frontal area m²
_CL  = 0.80    # lift coefficient
_A_W = 0.120   # wing area m²


class Drone:
    """
    PD-controlled quadrotor.

    Extra constructor params vs original:
      urdf   – optional absolute path to a URDF; defaults to assets/drone.urdf
      color  – pass "multi" to preserve URDF-defined per-link colours
    """

    def __init__(
        self,
        drone_id: str,
        start_position: tuple,
        physics_client: int,
        color: str   = "gray",
        max_h_force: float = 15.0,
        max_v_force: float = 20.0,
        max_speed:   float = 15.0,
        kp:          float = 10.0,
        kd:          float = 5.0,
        urdf: str    = None,
        global_scaling: float = 1.0,
    ):
        self._id_str    = drone_id
        self._client    = physics_client
        self._target    = list(start_position)
        self._prev_error = [0.0, 0.0, 0.0]
        self._rotor_angle = 0.0

        self._max_h  = max_h_force
        self._max_v  = max_v_force
        self._max_spd = max_speed
        self._kp     = kp
        self._kd     = kd

        # URDF selection — default to research-grade cf2x quadrotor model
        if urdf is None:
            urdf = os.path.normpath(
                os.path.join(os.path.dirname(__file__), "..", "assets", "interceptor.urdf")
            )
        try:
            self._body = pybullet.loadURDF(
                urdf,
                basePosition=list(start_position),
                globalScaling=global_scaling,
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
        if color == "multi":
            return  # keep URDF-defined per-link colours
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
    @staticmethod
    def _align_z_to_vec(v):
        """Quaternion (xyzw) that rotates body +Z to align with world vector v."""
        v = np.asarray(v, dtype=float)
        n = float(np.linalg.norm(v))
        if n < 1e-6:
            return (0.0, 0.0, 0.0, 1.0)
        v = v / n
        z = np.array([0.0, 0.0, 1.0])
        dot = float(np.clip(np.dot(z, v), -1.0, 1.0))
        if dot > 0.9999:
            return (0.0, 0.0, 0.0, 1.0)
        if dot < -0.9999:
            return (1.0, 0.0, 0.0, 0.0)   # 180° around X
        axis = np.cross(z, v)
        axis /= np.linalg.norm(axis)
        half = math.acos(dot) / 2.0
        s    = math.sin(half)
        return (axis[0]*s, axis[1]*s, axis[2]*s, math.cos(half))

    # ------------------------------------------------------------------
    def set_target(self, x: float, y: float, z: float):
        self._target = [x, y, z]

    def update(self):
        pos, _ = pybullet.getBasePositionAndOrientation(self._body, physicsClientId=self._client)
        vel, _ = pybullet.getBaseVelocity(self._body, physicsClientId=self._client)
        force  = self._compute_vtol(pos, vel)
        pybullet.applyExternalForce(
            self._body, -1, force, list(pos), pybullet.WORLD_FRAME,
            physicsClientId=self._client,
        )
        self._spin_rotors()

    def _compute_vtol(self, pos, vel):
        """
        VTOL flight model.

        1. PD position controller → desired world-frame force vector.
        2. Normalise to get desired body-up (= thrust direction).
        3. Clamp tilt to MAX_TILT so it never flips upside-down.
        4. Kinematically set body orientation so the mesh visually banks.
        5. Apply thrust magnitude along that tilted direction + drag.

        Using kinematic orientation (resetBasePositionAndOrientation) avoids
        inertia-scaling instability while still producing the correct tilted
        visual and the physically correct thrust direction.
        """
        MAX_TILT   = math.radians(40)        # max lean from vertical
        G_COMP     = 9.81 * 1.5             # gravity compensation constant

        err   = [self._target[i] - pos[i] for i in range(3)]
        d_err = [(err[i] - self._prev_error[i]) / _TIMESTEP for i in range(3)]
        self._prev_error = err[:]

        # Desired world-frame force (same PD as before)
        fx = self._kp * err[0] + self._kd * d_err[0]
        fy = self._kp * err[1] + self._kd * d_err[1]
        fz = self._kp * err[2] + self._kd * d_err[2] + G_COMP

        f_des = np.array([fx, fy, fz])
        f_mag = float(np.linalg.norm(f_des))

        # Desired body-up direction
        if f_mag > 1e-6:
            desired_up = f_des / f_mag
        else:
            desired_up = np.array([0.0, 0.0, 1.0])

        # Clamp tilt angle
        if desired_up[2] < math.cos(MAX_TILT):
            xy_n = float(np.linalg.norm(desired_up[:2]))
            if xy_n > 1e-8:
                desired_up = np.array([
                    desired_up[0] / xy_n * math.sin(MAX_TILT),
                    desired_up[1] / xy_n * math.sin(MAX_TILT),
                    math.cos(MAX_TILT),
                ])

        # Kinematically tilt body so mesh visually banks into the manoeuvre
        orn_new = self._align_z_to_vec(desired_up)
        pybullet.resetBasePositionAndOrientation(
            self._body, list(pos), list(orn_new), physicsClientId=self._client
        )
        pybullet.resetBaseVelocity(
            self._body, list(vel), [0.0, 0.0, 0.0], physicsClientId=self._client
        )

        # Cap total force magnitude
        MAX_F = math.sqrt(self._max_h**2 + (self._max_v + G_COMP)**2)
        f_mag = min(f_mag, MAX_F)

        # Thrust along tilted body-Z + aerodynamic drag
        vel_np = np.array(vel)
        speed  = float(np.linalg.norm(vel_np))
        if speed > self._max_spd:
            vel_np = vel_np * (self._max_spd / speed)
            pybullet.resetBaseVelocity(
                self._body, vel_np.tolist(), [0.0, 0.0, 0.0], physicsClientId=self._client
            )

        thrust = desired_up * f_mag
        drag   = -0.15 * vel_np
        return (thrust + drag).tolist()

    def _spin_rotors(self):
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


# ======================================================================

class LoiteringMunition:
    """
    Forward-flying loitering munition (Ukraine Lancet / Shahed style).

    Key differences from Drone:
      - Loads intruder.urdf (horizontal fuselage); falls back to drone.urdf.
      - resetBasePositionAndOrientation every frame so nose tracks velocity.
      - Aerodynamic drag + wing lift forces applied each step.
      - No _apply_color — URDF colours are preserved.
    """

    def __init__(
        self,
        drone_id: str,
        start_position: tuple,
        physics_client: int,
        max_speed: float = 12.0,
        kp: float = 8.0,
        kd: float = 4.0,
    ):
        self._id_str    = drone_id
        self._client    = physics_client
        self._target    = list(start_position)
        self._prev_error = [0.0, 0.0, 0.0]
        self._max_spd   = max_speed
        self._kp        = kp
        self._kd        = kd
        self._mass      = 1.4   # kg, matches intruder.urdf total

        urdf_path = os.path.normpath(
            os.path.join(os.path.dirname(__file__), "..", "assets", "intruder.urdf")
        )
        fallback = os.path.normpath(
            os.path.join(os.path.dirname(__file__), "..", "assets", "drone.urdf")
        )
        try:
            self._body = pybullet.loadURDF(
                urdf_path,
                basePosition=list(start_position),
                globalScaling=3.0,
                physicsClientId=self._client,
            )
        except Exception:
            self._body = pybullet.loadURDF(
                fallback,
                basePosition=list(start_position),
                physicsClientId=self._client,
            )

        # Tint all links red so the intruder is visually distinct
        n = pybullet.getNumJoints(self._body, physicsClientId=self._client)
        pybullet.changeVisualShape(self._body, -1, rgbaColor=[0.9, 0.1, 0.1, 1.0],
                                   physicsClientId=self._client)
        for i in range(n):
            pybullet.changeVisualShape(self._body, i, rgbaColor=[0.9, 0.1, 0.1, 1.0],
                                       physicsClientId=self._client)

        self._rotor_joints = self._find_rotor_joints()

        try:
            pybullet.addUserDebugText(
                drone_id.upper(), [0, 0, 1.0], [0.9, 0.15, 0.15],
                textSize=1.5, physicsClientId=self._client,
                parentObjectUniqueId=self._body, parentLinkIndex=-1,
            )
        except Exception:
            pass

    # ------------------------------------------------------------------
    def _find_rotor_joints(self):
        joints = []
        n = pybullet.getNumJoints(self._body, physicsClientId=self._client)
        for i in range(n):
            info = pybullet.getJointInfo(self._body, i, physicsClientId=self._client)
            if info[2] == pybullet.JOINT_REVOLUTE:
                joints.append(i)
        return joints

    @staticmethod
    def _align_x_to_vec(v):
        """Quaternion that aligns body +X axis with world vector v (xyzw)."""
        v = np.asarray(v, dtype=float)
        n = np.linalg.norm(v)
        if n < 1e-6:
            return (0.0, 0.0, 0.0, 1.0)
        v = v / n
        x = np.array([1.0, 0.0, 0.0])
        dot = float(np.clip(np.dot(x, v), -1.0, 1.0))
        if dot > 0.9999:
            return (0.0, 0.0, 0.0, 1.0)
        if dot < -0.9999:
            return (0.0, 0.0, 1.0, 0.0)   # 180° around Z
        axis  = np.cross(x, v)
        axis /= np.linalg.norm(axis)
        half  = math.acos(dot) / 2.0
        s     = math.sin(half)
        return (axis[0]*s, axis[1]*s, axis[2]*s, math.cos(half))

    # ------------------------------------------------------------------
    def set_target(self, x: float, y: float, z: float):
        self._target = [x, y, z]

    def update(self):
        pos, _ = pybullet.getBasePositionAndOrientation(
            self._body, physicsClientId=self._client
        )
        vel, _ = pybullet.getBaseVelocity(self._body, physicsClientId=self._client)

        fx, fy, fz = self._compute_forces(pos, vel)
        pybullet.applyExternalForce(
            self._body, -1, [fx, fy, fz], list(pos),
            pybullet.WORLD_FRAME, physicsClientId=self._client,
        )

        # Orient nose toward velocity (or toward target when slow)
        speed = math.sqrt(vel[0]**2 + vel[1]**2 + vel[2]**2)
        if speed > 1.0:
            nose_dir = [v / speed for v in vel]
        else:
            to_t = [self._target[i] - pos[i] for i in range(3)]
            d    = math.sqrt(sum(v*v for v in to_t))
            nose_dir = [to_t[i]/d for i in range(3)] if d > 0.1 else [1.0, 0.0, 0.0]

        orn = self._align_x_to_vec(nose_dir)
        pybullet.resetBasePositionAndOrientation(
            self._body, list(pos), list(orn), physicsClientId=self._client
        )
        # Zero angular velocity so the body doesn't tumble under physics
        pybullet.resetBaseVelocity(
            self._body, list(vel), [0.0, 0.0, 0.0], physicsClientId=self._client
        )

        # Altitude floor
        if pos[2] < 0.5:
            pybullet.resetBasePositionAndOrientation(
                self._body, [pos[0], pos[1], 0.5], list(orn),
                physicsClientId=self._client,
            )

        self._spin_rotors(speed)

    def _compute_forces(self, pos, vel):
        err   = [self._target[i] - pos[i] for i in range(3)]
        d_err = [(err[i] - self._prev_error[i]) / _TIMESTEP for i in range(3)]
        self._prev_error = err

        # PD control (provides basic navigation thrust)
        fx = self._kp * err[0] + self._kd * d_err[0]
        fy = self._kp * err[1] + self._kd * d_err[1]
        fz = self._kp * err[2] + self._kd * d_err[2] + 9.81 * self._mass

        speed = math.sqrt(sum(v*v for v in vel))

        # Aerodynamic drag: F = 0.5 * rho * Cd * A * v²
        if speed > 0.5:
            drag = 0.5 * _RHO * _CD * _A * speed * speed
            fx -= drag * vel[0] / speed
            fy -= drag * vel[1] / speed
            fz -= drag * vel[2] / speed

        # Wing lift: F_lift = 0.5 * rho * Cl * A_wing * v_fwd²
        # Use horizontal speed as proxy for forward speed
        v_fwd = math.sqrt(vel[0]**2 + vel[1]**2)
        lift  = 0.5 * _RHO * _CL * _A_W * v_fwd * v_fwd
        fz   += lift

        # Cap forces
        h_mag = math.sqrt(fx*fx + fy*fy)
        MAX_H = 22.0
        if h_mag > MAX_H:
            fx = fx / h_mag * MAX_H
            fy = fy / h_mag * MAX_H
        fz = max(-18.0, min(28.0, fz))

        # Speed cap via velocity clamp
        if speed > self._max_spd:
            sc = self._max_spd / speed
            pybullet.resetBaseVelocity(
                self._body,
                [v * sc for v in vel],
                [0.0, 0.0, 0.0],
                physicsClientId=self._client,
            )

        return fx, fy, fz

    def _spin_rotors(self, fwd_speed: float):
        # Rotor RPM proportional to forward speed (min 15, max 40 rad/s)
        rpm = max(15.0, min(40.0, 15.0 + fwd_speed * 2.0))
        for i, joint in enumerate(self._rotor_joints):
            pybullet.setJointMotorControl2(
                self._body, joint, pybullet.VELOCITY_CONTROL,
                targetVelocity=(1 if i % 2 == 0 else -1) * rpm,
                force=0.1,
                physicsClientId=self._client,
            )

    # ------------------------------------------------------------------
    def get_position(self) -> tuple:
        pos, _ = pybullet.getBasePositionAndOrientation(
            self._body, physicsClientId=self._client
        )
        return tuple(pos)

    def get_velocity(self) -> tuple:
        vel, _ = pybullet.getBaseVelocity(self._body, physicsClientId=self._client)
        return tuple(vel)

    def get_state(self) -> dict:
        pos = self.get_position()
        vel = self.get_velocity()
        _, orn = pybullet.getBasePositionAndOrientation(
            self._body, physicsClientId=self._client
        )
        return {
            "position"   : pos,
            "velocity"   : vel,
            "orientation": tuple(orn),
            "timestamp"  : time.time(),
            "target"     : tuple(self._target),
            "speed"      : math.sqrt(sum(v*v for v in vel)),
        }
