"""
PyBullet 3-D flight trail renderer.
Draws a fading line trail behind a drone using debug lines.
"""

import pybullet


class TrailRenderer:
    def __init__(self, color: list, max_segments: int = 40, line_width: float = 2.0):
        self.color        = color
        self.max_segments = max_segments
        self.line_width   = line_width
        self._positions   = []
        self._line_ids    = []

    def update(self, pos: list, client: int):
        self._positions.append(list(pos))

        if len(self._positions) > self.max_segments + 1:
            if self._line_ids:
                try:
                    pybullet.removeUserDebugItem(
                        self._line_ids.pop(0), physicsClientId=client
                    )
                except Exception:
                    pass
            self._positions.pop(0)

        if len(self._positions) >= 2:
            n     = len(self._line_ids) + 1
            alpha = n / self.max_segments
            faded = [min(1.0, c * alpha) for c in self.color]
            try:
                lid = pybullet.addUserDebugLine(
                    self._positions[-2], self._positions[-1],
                    faded, lineWidth=self.line_width, physicsClientId=client,
                )
                self._line_ids.append(lid)
            except Exception:
                pass

    def clear(self, client: int):
        for lid in self._line_ids:
            try:
                pybullet.removeUserDebugItem(lid, physicsClientId=client)
            except Exception:
                pass
        self._line_ids.clear()
        self._positions.clear()
