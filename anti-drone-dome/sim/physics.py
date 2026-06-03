"""
PyBullet world setup: dark military ground, tactical grid, range rings,
protected-asset markers, dome wireframe, performance flags.
"""

import math
import pybullet
import pybullet_data

_TIMESTEP = 1.0 / 240.0

# Grid params
_GRID_HALF  = 30    # metres in each direction
_GRID_STEP  = 10    # grid spacing (m) — fewer lines than 5 m for faster debug draw
_GRID_MAJOR = 25    # thick lines every 25 m


class PhysicsWorld:
    def __init__(self, gui=True):
        self._gui = gui
        mode = pybullet.GUI if gui else pybullet.DIRECT
        self.client = pybullet.connect(mode)
        pybullet.setAdditionalSearchPath(
            pybullet_data.getDataPath(), physicsClientId=self.client
        )
        self._dome_lines   = []
        self._grid_lines   = []
        self._ring_lines   = []
        self._setup()

    # ------------------------------------------------------------------
    def _setup(self):
        pybullet.setGravity(0, 0, -9.81, physicsClientId=self.client)
        pybullet.setTimeStep(_TIMESTEP, physicsClientId=self.client)
        pybullet.setRealTimeSimulation(0, physicsClientId=self.client)

        if self._gui:
            # Disable expensive rendering features for maximum throughput
            pybullet.configureDebugVisualizer(
                pybullet.COV_ENABLE_SHADOWS, 0, physicsClientId=self.client
            )
            # GUI on = right-hand **User Parameters** panel (+/− zoom sliders, etc.).
            pybullet.configureDebugVisualizer(
                pybullet.COV_ENABLE_GUI, 1, physicsClientId=self.client
            )
            pybullet.configureDebugVisualizer(
                pybullet.COV_ENABLE_RGB_BUFFER_PREVIEW, 0, physicsClientId=self.client
            )

        # ── Custom dark ground (replaces checkerboard plane.urdf) ──────
        ground_col = pybullet.createCollisionShape(
            pybullet.GEOM_BOX, halfExtents=[60, 60, 0.10],
            physicsClientId=self.client,
        )
        ground_vis = pybullet.createVisualShape(
            pybullet.GEOM_BOX, halfExtents=[60, 60, 0.10],
            rgbaColor=[0.13, 0.16, 0.13, 1.0],
            physicsClientId=self.client,
        )
        pybullet.createMultiBody(
            0, ground_col, ground_vis, [0, 0, -0.10],
            physicsClientId=self.client,
        )

        if self._gui:
            self._draw_grid()
            self._draw_range_rings()
            self._draw_protected_assets()
            self._setup_camera()

    # ------------------------------------------------------------------
    def _draw_grid(self):
        c = self.client
        for i in range(-_GRID_HALF, _GRID_HALF + 1, _GRID_STEP):
            thick = (i % _GRID_MAJOR == 0)
            col   = [0.30, 0.36, 0.30] if thick else [0.19, 0.24, 0.19]
            lw    = 2.0 if thick else 1.0
            # N–S line
            self._grid_lines.append(
                pybullet.addUserDebugLine(
                    [i, -_GRID_HALF, 0.005], [i,  _GRID_HALF, 0.005],
                    col, lineWidth=lw, physicsClientId=c,
                )
            )
            # E–W line
            self._grid_lines.append(
                pybullet.addUserDebugLine(
                    [-_GRID_HALF, i, 0.005], [_GRID_HALF, i, 0.005],
                    col, lineWidth=lw, physicsClientId=c,
                )
            )

        # Cardinal direction labels
        edge = _GRID_HALF + 3
        for label, pos in [
            ("N",  [0,  edge, 0.3]),
            ("S",  [0, -edge, 0.3]),
            ("E",  [ edge, 0, 0.3]),
            ("W",  [-edge, 0, 0.3]),
        ]:
            pybullet.addUserDebugText(
                label, pos, [0.50, 0.65, 0.50],
                textSize=1.4, physicsClientId=c,
            )

    def _draw_range_rings(self):
        c = self.client
        ring_pts = 36
        for r, bright in [(5, False), (10, True), (15, False), (20, False), (25, False)]:
            # 10 m ring = dome boundary, drawn brighter
            col = [0.00, 0.80, 0.20] if bright else [0.20, 0.30, 0.20]
            lw  = 2.5 if bright else 1.0
            pts = [
                (r * math.cos(2*math.pi*j/ring_pts),
                 r * math.sin(2*math.pi*j/ring_pts),
                 0.008)
                for j in range(ring_pts + 1)
            ]
            for j in range(ring_pts):
                self._ring_lines.append(
                    pybullet.addUserDebugLine(
                        pts[j], pts[j+1], col, lineWidth=lw,
                        physicsClientId=c,
                    )
                )
            # Range label at NE
            lx = r * math.cos(math.pi / 4) + 0.4
            ly = r * math.sin(math.pi / 4) + 0.4
            pybullet.addUserDebugText(
                f"{r}m", [lx, ly, 0.2],
                [0.45, 0.55, 0.45], textSize=0.9,
                physicsClientId=c,
            )

    def _draw_protected_assets(self):
        c = self.client
        # Small military-structure boxes at 3 positions inside dome
        for (bx, by) in [(2.0, 1.0), (-1.0, 2.2), (1.0, -2.0)]:
            bh = 0.30
            col = pybullet.createCollisionShape(
                pybullet.GEOM_BOX, halfExtents=[0.40, 0.40, bh],
                physicsClientId=c,
            )
            vis = pybullet.createVisualShape(
                pybullet.GEOM_BOX, halfExtents=[0.40, 0.40, bh],
                rgbaColor=[0.60, 0.50, 0.30, 1.0],
                physicsClientId=c,
            )
            pybullet.createMultiBody(
                0, col, vis, [bx, by, bh],
                physicsClientId=c,
            )

    def _setup_camera(self):
        pybullet.resetDebugVisualizerCamera(
            cameraDistance=30,
            cameraYaw=225,
            cameraPitch=-35,
            cameraTargetPosition=[3, 3, 3],
            physicsClientId=self.client,
        )

    # ------------------------------------------------------------------
    def draw_dome(self, center, radius, color=None):
        if color is None:
            color = [0, 1, 0]
        for lid in self._dome_lines:
            try:
                pybullet.removeUserDebugItem(lid, physicsClientId=self.client)
            except Exception:
                pass
        self._dome_lines.clear()

        cx, cy, cz = center
        lat_steps    = 4
        lon_steps    = 8
        pts_per_ring = 24

        # Latitude rings (upper hemisphere)
        for lat_i in range(lat_steps + 1):
            lat  = math.pi / 2 * lat_i / lat_steps
            ring = []
            for j in range(pts_per_ring + 1):
                lon = 2 * math.pi * j / pts_per_ring
                ring.append([
                    cx + radius * math.cos(lat) * math.cos(lon),
                    cy + radius * math.cos(lat) * math.sin(lon),
                    cz + radius * math.sin(lat),
                ])
            for j in range(pts_per_ring):
                lid = pybullet.addUserDebugLine(
                    ring[j], ring[j+1], color, physicsClientId=self.client
                )
                self._dome_lines.append(lid)

        # Longitude lines
        for lon_i in range(lon_steps):
            lon  = 2 * math.pi * lon_i / lon_steps
            prev = None
            for lat_i in range(lat_steps + 1):
                lat = math.pi / 2 * lat_i / lat_steps
                pt  = [
                    cx + radius * math.cos(lat) * math.cos(lon),
                    cy + radius * math.cos(lat) * math.sin(lon),
                    cz + radius * math.sin(lat),
                ]
                if prev is not None:
                    lid = pybullet.addUserDebugLine(
                        prev, pt, color, physicsClientId=self.client
                    )
                    self._dome_lines.append(lid)
                prev = pt

    # ------------------------------------------------------------------
    def step(self):
        pybullet.stepSimulation(physicsClientId=self.client)

    def reset(self):
        pybullet.resetSimulation(physicsClientId=self.client)
        self._dome_lines.clear()
        self._grid_lines.clear()
        self._ring_lines.clear()
        self._setup()

    def get_time(self):
        return pybullet.getPhysicsEngineParameters(
            physicsClientId=self.client
        )["fixedTimeStep"]
