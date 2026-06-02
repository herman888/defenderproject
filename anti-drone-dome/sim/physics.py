"""
PyBullet world setup: dark military ground, tactical grid, range rings,
protected-asset markers, dome wireframe, performance flags.
All dimensions scaled for a 200 m dome radius.
"""

import math
import pybullet
import pybullet_data

_TIMESTEP = 1.0 / 240.0

# Grid params — scaled for 200 m dome
_GRID_HALF  = 800   # grid extends ±800 m
_GRID_STEP  = 50    # minor grid spacing (m)
_GRID_MAJOR = 200   # major grid every 200 m (matches dome boundary)


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
            pybullet.configureDebugVisualizer(
                pybullet.COV_ENABLE_TINY_RENDERER, 0, physicsClientId=self.client
            )

        # ── Dark military terrain — no checkerboard ────────────────────
        ground_col = pybullet.createCollisionShape(
            pybullet.GEOM_BOX, halfExtents=[1500, 1500, 0.5],
            physicsClientId=self.client,
        )
        ground_vis = pybullet.createVisualShape(
            pybullet.GEOM_BOX, halfExtents=[1500, 1500, 0.5],
            rgbaColor=[0.12, 0.15, 0.12, 1.0],
            physicsClientId=self.client,
        )
        pybullet.createMultiBody(
            0, ground_col, ground_vis, [0, 0, -0.5],
            physicsClientId=self.client,
        )

        if self._gui:
            self._draw_grid()
            self._draw_range_rings()
            self._draw_protected_assets()
            self._draw_radar_station()
            self._setup_camera()

    # ------------------------------------------------------------------
    def _draw_grid(self):
        c = self.client
        for i in range(-_GRID_HALF, _GRID_HALF + 1, _GRID_STEP):
            thick = (i % _GRID_MAJOR == 0)
            col   = [0.28, 0.35, 0.28] if thick else [0.18, 0.22, 0.18]
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

        # Cardinal labels just outside dome boundary
        for label, pos in [
            ("N",  [0,   250, 2.0]),
            ("S",  [0,  -250, 2.0]),
            ("E",  [ 250, 0,  2.0]),
            ("W",  [-250, 0,  2.0]),
        ]:
            pybullet.addUserDebugText(
                label, pos, [0.50, 0.60, 0.50],
                textSize=1.2, physicsClientId=c,
            )

    def _draw_range_rings(self):
        c = self.client
        ring_pts = 64
        ring_specs = [
            (100, [0.00, 0.40, 0.10], 1.0, "100m"),
            (200, [0.00, 0.70, 0.15], 2.0, "200m ◄ DOME"),
            (400, [0.20, 0.30, 0.20], 1.0, "400m"),
            (600, [0.15, 0.22, 0.15], 0.8, "600m"),
        ]
        for r, col, lw, lbl in ring_specs:
            pts = [
                (r * math.cos(2*math.pi*j/ring_pts),
                 r * math.sin(2*math.pi*j/ring_pts),
                 0.01)
                for j in range(ring_pts + 1)
            ]
            for j in range(ring_pts):
                self._ring_lines.append(
                    pybullet.addUserDebugLine(
                        pts[j], pts[j+1], col, lineWidth=lw,
                        physicsClientId=c,
                    )
                )
            lx = r * math.cos(math.pi / 4) + 2.0
            ly = r * math.sin(math.pi / 4) + 2.0
            pybullet.addUserDebugText(
                lbl, [lx, ly, 1.0], col, textSize=1.0, physicsClientId=c,
            )

    def _draw_protected_assets(self):
        c = self.client
        for (bx, by) in [(30, 20), (-25, 30), (10, -35), (-30, -20)]:
            col = pybullet.createCollisionShape(
                pybullet.GEOM_BOX, halfExtents=[4, 6, 3],
                physicsClientId=c,
            )
            vis = pybullet.createVisualShape(
                pybullet.GEOM_BOX, halfExtents=[4, 6, 3],
                rgbaColor=[0.55, 0.50, 0.38, 1.0],
                physicsClientId=c,
            )
            pybullet.createMultiBody(0, col, vis, [bx, by, 3], physicsClientId=c)

    def _draw_radar_station(self):
        """10 m mast + 2 m dish visual at (0, -200, 0) — scale-appropriate supplement."""
        c = self.client
        mast_col = pybullet.createCollisionShape(
            pybullet.GEOM_CYLINDER, radius=0.3, height=10, physicsClientId=c,
        )
        mast_vis = pybullet.createVisualShape(
            pybullet.GEOM_CYLINDER, radius=0.3, length=10,
            rgbaColor=[0.4, 0.4, 0.45, 1.0], physicsClientId=c,
        )
        pybullet.createMultiBody(0, mast_col, mast_vis, [0, -200, 5], physicsClientId=c)

        dish_col = pybullet.createCollisionShape(
            pybullet.GEOM_CYLINDER, radius=2.0, height=0.3, physicsClientId=c,
        )
        dish_vis = pybullet.createVisualShape(
            pybullet.GEOM_CYLINDER, radius=2.0, length=0.3,
            rgbaColor=[0.5, 0.55, 0.5, 1.0], physicsClientId=c,
        )
        pybullet.createMultiBody(0, dish_col, dish_vis, [0, -200, 10.2], physicsClientId=c)

    def _setup_camera(self):
        pybullet.resetDebugVisualizerCamera(
            cameraDistance=600,
            cameraYaw=45,
            cameraPitch=-30,
            cameraTargetPosition=[0, 0, 0],
            physicsClientId=self.client,
        )

    # ------------------------------------------------------------------
    def draw_dome(self, center, radius, color=None):
        if color is None:
            color = [0.0, 0.6, 0.1]
        for lid in self._dome_lines:
            try:
                pybullet.removeUserDebugItem(lid, physicsClientId=self.client)
            except Exception:
                pass
        self._dome_lines.clear()

        cx, cy, cz = center
        lat_steps    = 8
        lon_steps    = 12
        pts_per_ring = 32

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
