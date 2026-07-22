"""
Drone            : VTOL quadrotor interceptor.
LoiteringMunition: Parametrized forward-flying attacker — Shahed-136, consumer
                   quad, or FPV attack drone.  All aerodynamic constants, URDF,
                   scaling, and colour are passed in at construction time from
                   the INTRUDER_TYPES config in scenarios.py.

Stage A flight-controller interface
────────────────────────────────────
Drone.apply_setpoint(sp) consumes a guidance.setpoint.GuidanceSetpoint
(LOCAL_NED, m/s²/m/s/m) and drives PyBullet as a placeholder flight
controller — mass, gravity comp, and force saturation all live here
instead of in guidance/. Stage B replaces this method with a MAVLink
send; guidance/ does not change.
"""

import math
import os
import time
import pybullet
import numpy as np

from config import INTERCEPTOR_MASS, PLACEHOLDER_FC_KV
from guidance.setpoint import GuidanceSetpoint, ned_to_enu
from sim.airframe_profiles import get_airframe_profile

_TIMESTEP    = 1.0 / 240.0
_ROTOR_SPEED = 20.0   # rad/s visual spin (quadrotor interceptor)
_RHO         = 1.225  # kg/m³ air density (shared constant)


def placeholder_fc_accel_enu(sp: GuidanceSetpoint,
                              current_vel_enu: tuple,
                              k_v: float = PLACEHOLDER_FC_KV) -> tuple:
    """Pure reference implementation of the placeholder FC's inner velocity
    loop: a_cmd_enu = k_v·(v_des - v) + a_ff + (0, 0, 9.81).

    Returns the commanded ENU acceleration as a 3-tuple. Position-only
    setpoints return (0, 0, 0) — callers must run their own position
    controller for those (Drone.apply_setpoint delegates to Drone.update()).

    Shared between sim/drone.py:Drone.apply_setpoint and the point-mass
    simulator in tests/test_apn_comparison.py so both interpret a
    GuidanceSetpoint identically.
    """
    if sp is None or sp.is_empty:
        return (0.0, 0.0, 0.0)
    a = [0.0, 0.0, 0.0]
    if sp.velocity is not None:
        v_des = ned_to_enu(sp.velocity)
        for i in range(3):
            a[i] += k_v * (v_des[i] - current_vel_enu[i])
    if sp.accel is not None:
        a_acc = ned_to_enu(sp.accel)
        for i in range(3):
            a[i] += a_acc[i]
    a[2] += 9.81   # FC gravity comp
    return (a[0], a[1], a[2])


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
        airframe_profile_id: str | None = None,
    ):
        profile = (
            get_airframe_profile(airframe_profile_id)
            if airframe_profile_id else None
        )
        if profile:
            propulsion = profile["propulsion"]
            rigid_body = profile["rigid_body"]
            max_h_force = propulsion["max_horizontal_force_n"]
            max_v_force = propulsion["vertical_force_max_n"]
            max_speed = propulsion["max_speed_mps"]
            global_scaling = profile["geometry"]["visual_scale"]
        else:
            propulsion = {}
            rigid_body = {}
        self._id_str    = drone_id
        self._client    = physics_client
        self._target    = list(start_position)
        self._prev_error = [0.0, 0.0, 0.0]
        self._rotor_angle = 0.0
        self._smooth_up = np.array([0.0, 0.0, 1.0], dtype=float)
        self._commanded_force = np.zeros(3, dtype=float)
        self._actuator_tau_s = float(
            propulsion.get("actuator_time_constant_s", _TIMESTEP)
        )
        self._force_slew_nps = float(
            propulsion.get("force_slew_rate_nps", float("inf"))
        )
        self._energy_capacity_wh = float(
            propulsion.get("energy_capacity_wh", float("inf"))
        )
        self._energy_remaining_wh = self._energy_capacity_wh
        self._minimum_voltage_fraction = float(
            propulsion.get("minimum_voltage_fraction", 1.0)
        )
        self.airframe_profile_id = airframe_profile_id
        # Trim from rigid-body mass once URDF is loaded (set in _apply_color path)
        self._mass_kg  = float(INTERCEPTOR_MASS)
        self._hover_ff = 9.81 * 1.35

        self._max_h  = max_h_force
        self._max_v  = max_v_force
        self._min_v = float(
            propulsion.get("vertical_force_min_n", -max_v_force)
        )
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
            if profile:
                pybullet.changeDynamics(
                    self._body,
                    -1,
                    mass=float(rigid_body["mass_kg"]),
                    localInertiaDiagonal=list(rigid_body["inertia_kg_m2"]),
                    physicsClientId=self._client,
                )
            mass = float(
                pybullet.getDynamicsInfo(self._body, -1, physicsClientId=self._client)[0]
            )
            if mass > 1e-4:
                self._mass_kg  = mass
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

    @property
    def body_id(self) -> int:
        return self._body

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

        # Thrust along tilted body-Z + aerodynamic drag
        speed = float(np.linalg.norm(vel_np))
        if speed > self._max_spd:
            vel_np = vel_np * (self._max_spd / speed)
            pybullet.resetBaseVelocity(
                self._body, vel_np.tolist(), [0.0, 0.0, 0.0], physicsClientId=self._client
            )

        thrust = desired_up * f_mag
        drag   = -0.15 * vel_np
        limited = self._limit_force(thrust + drag)
        return self._condition_force(limited, vel_np).tolist()

    def _spin_rotors(self):
        for i, joint in enumerate(self._rotor_joints):
            pybullet.setJointMotorControl2(
                self._body, joint, pybullet.VELOCITY_CONTROL,
                targetVelocity=(1 if i % 2 == 0 else -1) * _ROTOR_SPEED,
                force=0.1,
                physicsClientId=self._client,
            )

    def _condition_force(self, requested, velocity) -> np.ndarray:
        requested = np.asarray(requested, dtype=float)
        alpha = min(1.0, _TIMESTEP / max(self._actuator_tau_s, _TIMESTEP))
        target = self._commanded_force + alpha * (
            requested - self._commanded_force
        )
        delta = target - self._commanded_force
        max_delta = self._force_slew_nps * _TIMESTEP
        delta_norm = float(np.linalg.norm(delta))
        if delta_norm > max_delta:
            delta *= max_delta / delta_norm
        self._commanded_force += delta

        if math.isfinite(self._energy_capacity_wh):
            speed = float(np.linalg.norm(velocity))
            mechanical_power_w = float(np.linalg.norm(self._commanded_force)) * max(
                speed, 2.0
            )
            self._energy_remaining_wh = max(
                0.0,
                self._energy_remaining_wh
                - mechanical_power_w * _TIMESTEP / (0.78 * 3600.0),
            )
            state = self._energy_remaining_wh / self._energy_capacity_wh
            voltage = self._minimum_voltage_fraction + (
                1.0 - self._minimum_voltage_fraction
            ) * state
            return self._commanded_force * voltage
        return self._commanded_force.copy()

    def _limit_force(self, force) -> np.ndarray:
        force = np.asarray(force, dtype=float).copy()
        horizontal = float(np.linalg.norm(force[:2]))
        if horizontal > self._max_h:
            force[:2] *= self._max_h / horizontal
        force[2] = max(self._min_v, min(self._max_v, force[2]))
        return force

    # ------------------------------------------------------------------
    def apply_setpoint(self, sp: GuidanceSetpoint):
        """Placeholder flight controller: consume a GuidanceSetpoint and
        drive the PyBullet rigid body to match.

        Routing:
          • sp.position only     → delegates to self.update() (existing PD path).
          • sp.velocity / accel  → inner-loop equivalent of a velocity
                                   controller: a_cmd = k_v·(v_des-v) + a_ff,
                                   plus gravity comp, then force = a·m.
          • sp.is_empty          → no-op; caller picks a fallback.

        sp.yaw is informational in Stage A — body yaw is currently derived
        implicitly from the tilt axis. The real ArduPilot in Stage B will
        honour it via its attitude controller.
        """
        if sp is None or sp.is_empty:
            return
        if sp.frame != "LOCAL_NED":
            raise ValueError(f"Unsupported setpoint frame: {sp.frame}")

        # Position-only → route through existing PD (loiter / takeoff).
        if sp.position is not None and sp.velocity is None and sp.accel is None:
            self._target = list(ned_to_enu(sp.position))
            self.update()
            return

        pos, _ = pybullet.getBasePositionAndOrientation(
            self._body, physicsClientId=self._client)
        vel, _ = pybullet.getBaseVelocity(self._body, physicsClientId=self._client)

        # FC inner loop → ENU acceleration command (includes gravity comp).
        a_cmd_enu = np.array(
            placeholder_fc_accel_enu(sp, tuple(vel)), dtype=float)

        # Convert accel command to body force via vehicle mass.
        force = a_cmd_enu * self._mass_kg

        # FC saturates each axis to the profile's physical force envelope.
        force = self._limit_force(force)
        force = self._condition_force(force, vel)
        f_mag = float(np.linalg.norm(force))

        # Kinematic tilt so the mesh visually banks into the manoeuvre.
        MAX_TILT = math.radians(40)
        UP_SLEW  = 0.26
        if f_mag > 1e-6:
            desired_up = force / f_mag
        else:
            desired_up = np.array([0.0, 0.0, 1.0])

        self._smooth_up = (1.0 - UP_SLEW) * self._smooth_up + UP_SLEW * desired_up
        sn = float(np.linalg.norm(self._smooth_up))
        if sn > 1e-8:
            self._smooth_up /= sn
        desired_up = self._smooth_up.copy()

        if desired_up[2] < math.cos(MAX_TILT):
            xy_n = float(np.linalg.norm(desired_up[:2]))
            if xy_n > 1e-8:
                desired_up = np.array([
                    desired_up[0] / xy_n * math.sin(MAX_TILT),
                    desired_up[1] / xy_n * math.sin(MAX_TILT),
                    math.cos(MAX_TILT),
                ])

        orn = self._align_z_to_vec(desired_up)
        pybullet.resetBasePositionAndOrientation(
            self._body, list(pos), list(orn), physicsClientId=self._client,
        )
        pybullet.resetBaseVelocity(
            self._body, list(vel), [0.0, 0.0, 0.0], physicsClientId=self._client,
        )

        # Airframe speed cap (vehicle limit, not guidance).
        speed = float(np.linalg.norm(vel))
        if speed > self._max_spd:
            sc = self._max_spd / speed
            pybullet.resetBaseVelocity(
                self._body,
                [v * sc for v in vel],
                [0.0, 0.0, 0.0],
                physicsClientId=self._client,
            )

        pybullet.applyExternalForce(
            self._body, -1, force.tolist(), list(pos),
            pybullet.WORLD_FRAME, physicsClientId=self._client,
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
            "airframe_profile_id": self.airframe_profile_id,
            "energy_remaining_fraction": (
                self._energy_remaining_wh / self._energy_capacity_wh
                if math.isfinite(self._energy_capacity_wh) else 1.0
            ),
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
        profile_id = cfg.get("airframe_profile_id")
        profile = get_airframe_profile(profile_id) if profile_id else None
        if profile:
            profile_aero = profile["aerodynamics"]
            profile_propulsion = profile["propulsion"]
            aero = {
                "cd": profile_aero["drag_coefficient"],
                "a": profile_aero["drag_area_m2"],
                "cl": profile_aero["lift_coefficient"],
                "a_w": profile_aero["wing_area_m2"],
                "max_h_force": profile_propulsion["max_horizontal_force_n"],
                "fz_min": profile_propulsion["vertical_force_min_n"],
                "fz_max": profile_propulsion["vertical_force_max_n"],
            }
        else:
            profile_propulsion = {}
            profile_aero = {}
            aero = {**self._DEFAULT_AERO, **cfg.get("aero", {})}

        self._id_str     = drone_id
        self._client     = physics_client
        self._target     = list(start_position)
        self._prev_error = [0.0, 0.0, 0.0]
        self._max_spd    = profile_propulsion.get(
            "max_speed_mps", cfg.get("max_speed", 51.0)
        )
        self._kp         = kp
        self._kd         = kd
        self._mass       = (
            profile["rigid_body"]["mass_kg"]
            if profile else cfg.get("mass", 1.4)
        )
        self.airframe_profile_id = profile_id
        self._dynamics_model = (
            profile["dynamics_model"] if profile else "legacy"
        )
        self._actuator_tau_s = float(
            profile_propulsion.get("actuator_time_constant_s", _TIMESTEP)
        )
        self._force_slew_nps = float(
            profile_propulsion.get("force_slew_rate_nps", float("inf"))
        )
        self._commanded_force = np.zeros(3, dtype=float)
        self._energy_capacity_wh = float(
            profile_propulsion.get("energy_capacity_wh", float("inf"))
        )
        self._energy_remaining_wh = self._energy_capacity_wh
        self._minimum_voltage_fraction = float(
            profile_propulsion.get("minimum_voltage_fraction", 1.0)
        )
        self._stall_speed = float(profile_aero.get("stall_speed_mps", 0.0))
        self._stall_angle = math.radians(
            float(profile_aero.get("stall_angle_deg", 90.0))
        )
        disturbance = profile.get("disturbance", {}) if profile else {}
        self._turbulence_std_n = float(
            disturbance.get("turbulence_force_std_n", 0.0)
        )
        self._rng = np.random.default_rng(disturbance.get("seed"))

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
        scaling = (
            profile["geometry"]["visual_scale"]
            if profile else cfg.get("scaling", 3.0)
        )

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
        if profile:
            pybullet.changeDynamics(
                self._body,
                -1,
                mass=self._mass,
                localInertiaDiagonal=list(profile["rigid_body"]["inertia_kg_m2"]),
                physicsClientId=self._client,
            )

        # Apply intruder-type colour
        rgba = cfg.get("color_rgba", [0.9, 0.1, 0.1, 1.0])
        if not cfg.get("preserve_materials", False):
            n = pybullet.getNumJoints(self._body, physicsClientId=self._client)
            pybullet.changeVisualShape(
                self._body, -1, rgbaColor=rgba, physicsClientId=self._client
            )
            for i in range(n):
                pybullet.changeVisualShape(
                    self._body, i, rgbaColor=rgba, physicsClientId=self._client
                )

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

    @property
    def body_id(self) -> int:
        return self._body

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

        # Apply hard speed cap here — the cap inside _compute_forces is
        # immediately overwritten by the resetBaseVelocity below, so it must
        # live here to actually persist into the next physics step.
        if speed > self._max_spd:
            sc = self._max_spd / speed
            vel = tuple(v * sc for v in vel)
            speed = self._max_spd

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

        # Wing lift (zero for pure-thrust quadrotors where cl=0).
        if self._cl > 0.01:
            v_fwd = math.sqrt(vel[0]**2 + vel[1]**2)
            effective_cl = self._cl
            if self._dynamics_model == "fidelity_v1":
                to_target = np.asarray(self._target, dtype=float) - np.asarray(
                    pos, dtype=float
                )
                target_angle = math.atan2(
                    to_target[2], max(np.linalg.norm(to_target[:2]), 1e-6)
                )
                flight_angle = math.atan2(vz, max(v_fwd, 1e-6))
                angle_of_attack = abs(target_angle - flight_angle)
                if angle_of_attack > self._stall_angle:
                    effective_cl *= max(
                        0.15,
                        self._stall_angle / max(angle_of_attack, 1e-6),
                    )
                if self._stall_speed > 0.0 and v_fwd < self._stall_speed:
                    effective_cl *= (v_fwd / self._stall_speed) ** 2
            fz += (
                0.5 * _RHO * effective_cl * self._a_wing * v_fwd * v_fwd
            )

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

        requested = np.asarray([fx, fy, fz], dtype=float)
        if self._dynamics_model == "fidelity_v1":
            requested += self._rng.normal(0.0, self._turbulence_std_n, 3)
            alpha = min(
                1.0, _TIMESTEP / max(self._actuator_tau_s, _TIMESTEP)
            )
            target = self._commanded_force + alpha * (
                requested - self._commanded_force
            )
            delta = target - self._commanded_force
            max_delta = self._force_slew_nps * _TIMESTEP
            delta_norm = float(np.linalg.norm(delta))
            if delta_norm > max_delta:
                delta *= max_delta / delta_norm
            self._commanded_force += delta
            speed_for_power = max(speed, 2.0)
            power_w = float(np.linalg.norm(self._commanded_force)) * speed_for_power
            self._energy_remaining_wh = max(
                0.0,
                self._energy_remaining_wh - power_w * _TIMESTEP / (0.78 * 3600.0),
            )
            energy_state = self._energy_remaining_wh / self._energy_capacity_wh
            voltage = self._minimum_voltage_fraction + (
                1.0 - self._minimum_voltage_fraction
            ) * energy_state
            requested = self._commanded_force * voltage
        return tuple(float(value) for value in requested)

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
            "airframe_profile_id": self.airframe_profile_id,
            "energy_remaining_fraction": (
                self._energy_remaining_wh / self._energy_capacity_wh
                if math.isfinite(self._energy_capacity_wh) else 1.0
            ),
        }
