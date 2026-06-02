"""
Drone            : VTOL quadrotor interceptor.
LoiteringMunition: Parametrized forward-flying attacker — Shahed-136, consumer
                   quad, or FPV attack drone.  All aerodynamic constants, URDF,
                   scaling, and colour are passed in at construction time from
                   the INTRUDER_TYPES config in scenarios.py.
"""

import math
import os
import time
import pybullet
import numpy as np

_TIMESTEP    = 1.0 / 240.0
_ROTOR_SPEED = 20.0   # rad/s visual spin (quadrotor interceptor)
_RHO         = 1.225  # kg/m³ air density (shared constant)


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
        self._smooth_up = np.array([0.0, 0.0, 1.0], dtype=float)
        # Trim from rigid-body mass once URDF is loaded (set in _apply_color path)
        self._hover_ff = 9.81 * 1.35

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
        try:
            mass = float(
                pybullet.getDynamicsInfo(self._body, -1, physicsClientId=self._client)[0]
            )
            if mass > 1e-4:
                self._hover_ff = mass * 9.81 * 1.06
        except Exception:
            pass

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
        VTOL flight model (interceptor).

        1. **World-frame PD** with velocity damping: ``F = Kp·e − Kd·v`` plus a
           **mass-trimmed hover bias** ``m·g`` from ``getDynamicsInfo``, so the
           quad does not hunt vertically on the real rigid-body mass.
        2. Normalise to desired **thrust direction** (body +Z).
        3. Clamp tilt to ``MAX_TILT`` so the mesh never inverts.
        4. **Slew-limit** that direction so attitude eases into hard turns
           (cinematic bank without twitch).
        5. Kinematic orientation + thrust along tilted Z + light linear drag.

        Kinematic orientation avoids torque–inertia fights with the external-force
        abstraction while keeping thrust and visuals consistent.
        """
        MAX_TILT   = math.radians(40)        # max lean from vertical
        UP_SLEW    = 0.26                    # blend toward new thrust dir (0–1)

        err = np.array(
            [self._target[i] - pos[i] for i in range(3)], dtype=float
        )
        vel_np = np.array(vel, dtype=float)

        # PD in world frame: derivative on measured velocity (smooth, standard form)
        fx = self._kp * err[0] - self._kd * vel_np[0]
        fy = self._kp * err[1] - self._kd * vel_np[1]
        fz = self._kp * err[2] - self._kd * vel_np[2] + self._hover_ff
        self._prev_error = err.tolist()

        f_des = np.array([fx, fy, fz])
        f_mag = float(np.linalg.norm(f_des))

        # Desired body-up direction
        if f_mag > 1e-6:
            desired_up = f_des / f_mag
        else:
            desired_up = np.array([0.0, 0.0, 1.0])

        # Ease attitude into aggressive direction changes
        self._smooth_up = (1.0 - UP_SLEW) * self._smooth_up + UP_SLEW * desired_up
        sn = float(np.linalg.norm(self._smooth_up))
        if sn > 1e-8:
            self._smooth_up /= sn
        desired_up = self._smooth_up.copy()

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

        # Cap total force magnitude (budget horizontal + vertical actuator)
        MAX_F = math.sqrt(self._max_h**2 + (self._max_v + self._hover_ff) ** 2)
        f_mag = min(f_mag, MAX_F)

        # Thrust along tilted body-Z + aerodynamic drag
        speed = float(np.linalg.norm(vel_np))
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

    def set_orientation_from_thrust(self, thrust_vec: list):
        """Tilt body to match the APN thrust direction and spin rotors.
        Does NOT apply any force — guidance force is applied externally."""
        MAX_TILT = math.radians(40)
        pos, _ = pybullet.getBasePositionAndOrientation(self._body, physicsClientId=self._client)
        vel, _ = pybullet.getBaseVelocity(self._body, physicsClientId=self._client)
        f   = np.array(thrust_vec, dtype=float)
        mag = float(np.linalg.norm(f))
        if mag < 1e-6:
            self._spin_rotors()
            return
        up = f / mag
        if up[2] < math.cos(MAX_TILT):
            xy = float(np.linalg.norm(up[:2]))
            if xy > 1e-8:
                up = np.array([
                    up[0] / xy * math.sin(MAX_TILT),
                    up[1] / xy * math.sin(MAX_TILT),
                    math.cos(MAX_TILT),
                ])
        orn = self._align_z_to_vec(up)
        pybullet.resetBasePositionAndOrientation(
            self._body, list(pos), list(orn), physicsClientId=self._client
        )
        pybullet.resetBaseVelocity(
            self._body, list(vel), [0.0, 0.0, 0.0], physicsClientId=self._client
        )
        self._spin_rotors()

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
    Forward-flying attacker — Shahed-136, consumer quadrotor, or FPV drone.

    All physical characteristics (aerodynamics, URDF, colour) come from the
    `intruder_cfg` dict produced by INTRUDER_TYPES in scenarios.py so that
    the same class models any drone type without subclassing.

    Fixed-wing types (Shahed): lift ≈ weight at cruise speed → below stall
    speed the drone must thrust upward to maintain altitude (realistic).
    Quadrotor types (consumer / FPV): cl=0 → pure thrust, no wing lift.
    """

    _DEFAULT_AERO = {
        "cd": 0.20, "a": 0.030,
        "cl": 0.65, "a_w": 0.013,
        "max_h_force": 160.0,
        "fz_min": -60.0, "fz_max": 90.0,
    }

    def __init__(
        self,
        drone_id:      str,
        start_position: tuple,
        physics_client: int,
        intruder_cfg:  dict = None,   # from INTRUDER_TYPES
        kp: float = 8.0,
        kd: float = 4.0,
    ):
        cfg = intruder_cfg or {}
        aero = {**self._DEFAULT_AERO, **cfg.get("aero", {})}

        self._id_str     = drone_id
        self._client     = physics_client
        self._target     = list(start_position)
        self._prev_error = [0.0, 0.0, 0.0]
        self._max_spd    = cfg.get("max_speed", 51.0)
        self._kp         = kp
        self._kd         = kd
        self._mass       = cfg.get("mass", 1.4)

        # Aerodynamic params (instance vars so _compute_forces uses self.*)
        self._cd       = aero["cd"]
        self._a_drag   = aero["a"]
        self._cl       = aero["cl"]
        self._a_wing   = aero["a_w"]
        self._max_h    = aero["max_h_force"]
        self._fz_min   = aero["fz_min"]
        self._fz_max   = aero["fz_max"]

        # Load URDF
        assets_dir = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "assets"))
        urdf_name  = cfg.get("urdf", "intruder.urdf")
        urdf_path  = os.path.join(assets_dir, urdf_name)
        fallback   = os.path.join(assets_dir, "drone.urdf")
        scaling    = cfg.get("scaling", 3.0)

        for path in (urdf_path, fallback):
            try:
                self._body = pybullet.loadURDF(
                    path,
                    basePosition=list(start_position),
                    globalScaling=scaling,
                    physicsClientId=self._client,
                )
                break
            except Exception:
                continue

        # Apply intruder-type colour
        rgba = cfg.get("color_rgba", [0.9, 0.1, 0.1, 1.0])
        n = pybullet.getNumJoints(self._body, physicsClientId=self._client)
        pybullet.changeVisualShape(self._body, -1, rgbaColor=rgba, physicsClientId=self._client)
        for i in range(n):
            pybullet.changeVisualShape(self._body, i, rgbaColor=rgba, physicsClientId=self._client)

        # 3-D label colour matches body colour (slightly brighter)
        lbl_col = [min(1.0, c * 1.3) for c in rgba[:3]]
        try:
            pybullet.addUserDebugText(
                drone_id.upper(), [0, 0, 1.0], lbl_col,
                textSize=1.5, physicsClientId=self._client,
                parentObjectUniqueId=self._body, parentLinkIndex=-1,
            )
        except Exception:
            pass

        self._rotor_joints = self._find_rotor_joints()

        # Spawn with horizontal fuselage pointing toward target (nose-first)
        # Without this, fixed-wing types (Shahed) look wrong for the first
        # ~50 settling steps before update() is called.
        to_t = [self._target[i] - start_position[i] for i in range(3)]
        horiz = math.sqrt(to_t[0]**2 + to_t[1]**2)
        if horiz > 0.1:
            nose = [to_t[0]/horiz, to_t[1]/horiz, 0.0]
            init_orn = self._align_x_to_vec(nose)
            pybullet.resetBasePositionAndOrientation(
                self._body, list(start_position), list(init_orn),
                physicsClientId=self._client,
            )

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
        """Quaternion (xyzw) aligning body +X with world vector v."""
        v = np.asarray(v, dtype=float)
        n = np.linalg.norm(v)
        if n < 1e-6:
            return (0.0, 0.0, 0.0, 1.0)
        v /= n
        x   = np.array([1.0, 0.0, 0.0])
        dot = float(np.clip(np.dot(x, v), -1.0, 1.0))
        if dot > 0.9999:
            return (0.0, 0.0, 0.0, 1.0)
        if dot < -0.9999:
            return (0.0, 0.0, 1.0, 0.0)
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
            self._body, physicsClientId=self._client)
        vel, _ = pybullet.getBaseVelocity(self._body, physicsClientId=self._client)

        fx, fy, fz = self._compute_forces(pos, vel)
        pybullet.applyExternalForce(
            self._body, -1, [fx, fy, fz], list(pos),
            pybullet.WORLD_FRAME, physicsClientId=self._client,
        )

        speed = math.sqrt(vel[0]**2 + vel[1]**2 + vel[2]**2)
        if speed > 1.0:
            nose_dir = [v / speed for v in vel]
        else:
            to_t = [self._target[i] - pos[i] for i in range(3)]
            d    = math.sqrt(sum(v*v for v in to_t))
            nose_dir = [to_t[i]/d for i in range(3)] if d > 0.1 else [1.0, 0.0, 0.0]

        orn = self._align_x_to_vec(nose_dir)
        pybullet.resetBasePositionAndOrientation(
            self._body, list(pos), list(orn), physicsClientId=self._client)
        pybullet.resetBaseVelocity(
            self._body, list(vel), [0.0, 0.0, 0.0], physicsClientId=self._client)

        alt_floor = 5.0 if self._max_spd > 40 else 1.0   # Shahed higher floor
        if pos[2] < alt_floor:
            pybullet.resetBasePositionAndOrientation(
                self._body, [pos[0], pos[1], alt_floor], list(orn),
                physicsClientId=self._client)

        self._spin_rotors(speed)

    def _compute_forces(self, pos, vel):
        err = [self._target[i] - pos[i] for i in range(3)]
        vx, vy, vz = vel[0], vel[1], vel[2]
        # PD with velocity damping (same structure as interceptor VTOL)
        fx = self._kp * err[0] - self._kd * vx
        fy = self._kp * err[1] - self._kd * vy
        fz = self._kp * err[2] - self._kd * vz + 9.81 * self._mass
        self._prev_error = err[:]

        speed = math.sqrt(sum(v*v for v in vel))

        # Aerodynamic drag
        if speed > 0.5:
            drag = 0.5 * _RHO * self._cd * self._a_drag * speed * speed
            fx  -= drag * vel[0] / speed
            fy  -= drag * vel[1] / speed
            fz  -= drag * vel[2] / speed

        # Wing lift (zero for pure-thrust quadrotors where cl=0)
        if self._cl > 0.01:
            v_fwd = math.sqrt(vel[0]**2 + vel[1]**2)
            fz   += 0.5 * _RHO * self._cl * self._a_wing * v_fwd * v_fwd

        # Force caps
        h_mag = math.sqrt(fx*fx + fy*fy)
        if h_mag > self._max_h:
            fx = fx / h_mag * self._max_h
            fy = fy / h_mag * self._max_h
        fz = max(self._fz_min, min(self._fz_max, fz))

        # Speed cap
        if speed > self._max_spd:
            sc = self._max_spd / speed
            pybullet.resetBaseVelocity(
                self._body, [v * sc for v in vel],
                [0.0, 0.0, 0.0], physicsClientId=self._client)

        return fx, fy, fz

    def _spin_rotors(self, fwd_speed: float):
        rpm = max(15.0, min(80.0, 15.0 + fwd_speed * 0.8))
        for i, joint in enumerate(self._rotor_joints):
            pybullet.setJointMotorControl2(
                self._body, joint, pybullet.VELOCITY_CONTROL,
                targetVelocity=(1 if i % 2 == 0 else -1) * rpm,
                force=0.1, physicsClientId=self._client,
            )

    # ------------------------------------------------------------------
    def get_position(self) -> tuple:
        pos, _ = pybullet.getBasePositionAndOrientation(
            self._body, physicsClientId=self._client)
        return tuple(pos)

    def get_velocity(self) -> tuple:
        vel, _ = pybullet.getBaseVelocity(self._body, physicsClientId=self._client)
        return tuple(vel)

    def get_state(self) -> dict:
        pos = self.get_position()
        vel = self.get_velocity()
        _, orn = pybullet.getBasePositionAndOrientation(
            self._body, physicsClientId=self._client)
        return {
            "position"   : pos,
            "velocity"   : vel,
            "orientation": tuple(orn),
            "timestamp"  : time.time(),
            "target"     : tuple(self._target),
            "speed"      : math.sqrt(sum(v*v for v in vel)),
        }
