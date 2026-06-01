"""Optional PyBullet GUI camera: auto-orbit and keyboard pan/rotate/zoom.

PyBullet already lets you drag with the mouse to orbit; this adds:

* **Auto-orbit** — slowly rotate the view (good for demos / screen recording).
* **Keyboard** — with the **3D view focused** (click it first):

  - **J** / **L** — yaw left / right
  - **I** / **K** — pitch up / down
  - **U** / **O** — zoom out / in

Yaw and pitch are in degrees, matching ``resetDebugVisualizerCamera``.
"""

from __future__ import annotations

from typing import Optional

import numpy as np
import pybullet as p


class GuiCameraController:
    """Reads the current debug camera, applies orbit / keys, writes it back."""

    def __init__(
        self,
        physics_client_id: int,
        *,
        orbit_enabled: bool = False,
        orbit_speed_deg_s: float = 14.0,
        follow_drones: bool = False,
    ):
        self.client = int(physics_client_id)
        self.orbit_enabled = bool(orbit_enabled)
        self.orbit_speed_deg_s = float(orbit_speed_deg_s)
        self.follow_drones = bool(follow_drones)
        self._printed_help = False

    def step(
        self,
        dt: float,
        *,
        drone_centroid_xyz: Optional[np.ndarray] = None,
    ) -> None:
        """Call once per control step after ``env.render()`` while GUI is active."""
        try:
            if hasattr(p, "isConnected") and not p.isConnected(self.client):
                return
        except Exception:
            return
        try:
            self._step_impl(dt, drone_centroid_xyz=drone_centroid_xyz)
        except Exception:
            #### Never let optional camera controls kill the simulation loop #####
            return

    def _step_impl(
        self,
        dt: float,
        *,
        drone_centroid_xyz: Optional[np.ndarray] = None,
    ) -> None:
        if not self._printed_help:
            print(
                "[INFO] PyBullet camera: mouse-drag to orbit (built-in). "
                "Keys (focus 3D window): J/L yaw, I/K pitch, U/O zoom. "
                f"Auto-orbit={'on' if self.orbit_enabled else 'off'}."
            )
            self._printed_help = True

        ret = p.getDebugVisualizerCamera(physicsClientId=self.client)
        if len(ret) < 12:
            return
        yaw = float(ret[8])
        pitch = float(ret[9])
        dist = float(ret[10])
        target = np.asarray(ret[11], dtype=float).reshape(3).copy()

        if self.follow_drones and drone_centroid_xyz is not None:
            c = np.asarray(drone_centroid_xyz, dtype=float).reshape(3)
            target = c

        dyaw = self.orbit_speed_deg_s * dt if self.orbit_enabled else 0.0
        dpitch = 0.0
        ddist = 0.0
        key_step_deg = 48.0 * dt
        key_step_dist = 0.45 * dt

        #### Some PyBullet builds only support getKeyboardEvents() with no client id #
        try:
            keys = p.getKeyboardEvents(physicsClientId=self.client)
        except TypeError:
            keys = p.getKeyboardEvents()
        if ord("j") in keys and (keys[ord("j")] & p.KEY_IS_DOWN):
            dyaw -= key_step_deg
        if ord("l") in keys and (keys[ord("l")] & p.KEY_IS_DOWN):
            dyaw += key_step_deg
        if ord("i") in keys and (keys[ord("i")] & p.KEY_IS_DOWN):
            dpitch += key_step_deg
        if ord("k") in keys and (keys[ord("k")] & p.KEY_IS_DOWN):
            dpitch -= key_step_deg
        if ord("u") in keys and (keys[ord("u")] & p.KEY_IS_DOWN):
            ddist += key_step_dist
        if ord("o") in keys and (keys[ord("o")] & p.KEY_IS_DOWN):
            ddist -= key_step_dist

        yaw_n = yaw + dyaw
        pitch_n = float(np.clip(pitch + dpitch, -85.0, -3.0))
        dist_n = float(np.clip(dist + ddist, 0.55, 18.0))

        p.resetDebugVisualizerCamera(
            cameraDistance=dist_n,
            cameraYaw=yaw_n,
            cameraPitch=pitch_n,
            cameraTargetPosition=target.tolist(),
            physicsClientId=self.client,
        )
