"""
PyBullet **User Parameters** (right-hand panel) zoom controls.

PyBullet does not expose literal +/− push-buttons in this API — only sliders.
These sliders use the same **rising-edge** pattern as ``AttackDebugUi`` in
``gym-pybullet-drones``: drag toward **1** to fire one zoom step, drag back
toward **0** to re-arm.  Labels read like **+ ZOOM** / **− ZOOM**.
"""

from __future__ import annotations

import pybullet as p


class CameraZoomDebugUi:
    """Side-panel sliders for one-shot zoom in / zoom out (no matplotlib required)."""

    def __init__(self, physics_client_id: int):
        self.client = int(physics_client_id)
        self._armed_in = True
        self._armed_out = True
        self.zoom_in_id = p.addUserDebugParameter(
            "3D + ZOOM (slide→1, back→0)",
            0,
            1,
            0,
            physicsClientId=self.client,
        )
        self.zoom_out_id = p.addUserDebugParameter(
            "3D − ZOOM (slide→1, back→0)",
            0,
            1,
            0,
            physicsClientId=self.client,
        )

    def poll(self) -> str | None:
        """Return ``\"in\"`` / ``\"out\"`` once per slider stroke, else ``None``."""
        try:
            if hasattr(p, "isConnected") and not p.isConnected(self.client):
                return None
            zin = float(
                p.readUserDebugParameter(self.zoom_in_id, physicsClientId=self.client)
            )
            if zin < 0.12:
                self._armed_in = True
            elif self._armed_in and zin > 0.88:
                self._armed_in = False
                return "in"

            zout = float(
                p.readUserDebugParameter(self.zoom_out_id, physicsClientId=self.client)
            )
            if zout < 0.12:
                self._armed_out = True
            elif self._armed_out and zout > 0.88:
                self._armed_out = False
                return "out"
        except Exception:
            return None
        return None
