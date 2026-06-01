"""Red-team attack controls in the **PyBullet GUI** (User Parameters / Params panel).

Uses ``addUserDebugParameter`` sliders so everything stays in the simulation window:

* **Red ATTACK type** — ``0`` = Rocket, ``1`` = Drone swarm, ``2`` = Dive bomber  
* **Red FIRE** — drag to **1** to launch; drag back toward **0** to arm the next shot
  (rising-edge trigger so you do not need a separate window).

Do **not** call ``removeAllUserParameters`` here; that would wipe other debug sliders
(e.g. prop RPM widgets when ``user_debug_gui`` is on).
"""

from __future__ import annotations

import numpy as np
import pybullet as p


class AttackDebugUi:
    """Side-panel sliders for attack type and FIRE (no extra Matplotlib window)."""

    MODES = ("rocket", "swarm", "dive")

    def __init__(self, physics_client_id: int):
        self.client = int(physics_client_id)
        self.mode_id = p.addUserDebugParameter(
            "Red ATTACK type (0=R 1=S 2=D)",
            0,
            2,
            0,
            physicsClientId=self.client,
        )
        self.fire_id = p.addUserDebugParameter(
            "Red FIRE (slide to 1, back to 0 to re-arm)",
            0,
            1,
            0,
            physicsClientId=self.client,
        )
        self._armed = True

    def poll_launch(self) -> str | None:
        """Return ``rocket`` / ``swarm`` / ``dive`` once per FIRE stroke, else ``None``."""
        try:
            if hasattr(p, "isConnected") and not p.isConnected(self.client):
                return None
            fire = float(
                p.readUserDebugParameter(self.fire_id, physicsClientId=self.client)
            )
            if fire < 0.12:
                self._armed = True
                return None
            if self._armed and fire > 0.88:
                self._armed = False
                m = float(
                    p.readUserDebugParameter(self.mode_id, physicsClientId=self.client)
                )
                idx = int(np.clip(round(m), 0, 2))
                return self.MODES[idx]
        except Exception:
            #### GUI closed or debug params invalid — ignore ######################
            return None
        return None
