"""
PyBullet world setup: dark military ground, tactical grid, range rings,
protected-asset markers, dome wireframe, performance flags.
All dimensions scaled for a 200 m dome radius.
"""

import math
import numpy as np
import pybullet
import pybullet_data
from sim.geospatial import load_osm_features
from sim.terrain import load_elevation_grid

_TIMESTEP = 1.0 / 240.0

# Grid params — scaled for 200 m dome
_GRID_HALF  = 800   # grid extends ±800 m
_GRID_STEP  = 50    # minor grid spacing (m)
_GRID_MAJOR = 200   # major grid every 200 m (matches dome boundary)


class PhysicsWorld:
    def __init__(self, gui=True, site_config=None, render_backend="auto"):
        self._gui = gui
        self._site_config = site_config
        map_config = (site_config or {}).get("map", {})
        self._elevation_grid = load_elevation_grid(
            map_config.get("elevation_cache")
        )
        self.terrain_source = (
            self._elevation_grid.source.get("dataset", "ELEVATION GRID")
            if self._elevation_grid
            else "PROCEDURAL FALLBACK"
        )
        if render_backend not in {"auto", "opengl", "tiny"}:
            raise ValueError("render_backend must be auto, opengl, or tiny")
        use_opengl = gui or render_backend in {"auto", "opengl"}
        self.camera_renderer = (
            pybullet.ER_BULLET_HARDWARE_OPENGL
            if use_opengl
            else pybullet.ER_TINY_RENDERER
        )
        self.render_backend = (
            "PYBULLET OPENGL" if use_opengl else "PYBULLET TINY CPU"
        )
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
        # The terrain mesh below is both the visible and collidable ground.
        # Avoid a flat collision plane that would erase real valleys below origin.
        self._draw_terrain_relief()
        self._draw_land_cover()
        zone_vis = pybullet.createVisualShape(
            pybullet.GEOM_CYLINDER,
            radius=200.0,
            length=0.06,
            rgbaColor=[0.16, 0.42, 0.22, 0.16],
            physicsClientId=self.client,
        )
        pybullet.createMultiBody(
            0,
            baseVisualShapeIndex=zone_vis,
            basePosition=[0.0, 0.0, 0.035],
            physicsClientId=self.client,
        )

        self._draw_real_map()
        self._draw_protected_assets()
        if self._gui:
            self._draw_grid()
            self._draw_range_rings()
            self._draw_radar_station()
            self._setup_camera()

    @staticmethod
    def terrain_elevation(x, y):
        """Deterministic rolling relief with a flat protected-site footprint."""
        radius = math.hypot(float(x), float(y))
        blend = min(1.0, max(0.0, (radius - 220.0) / 700.0))
        blend = blend * blend * (3.0 - 2.0 * blend)
        ridge = (
            11.0
            + 7.0 * math.sin(float(x) / 210.0)
            + 5.0 * math.cos(float(y) / 260.0)
            + 3.5 * math.sin((float(x) + float(y)) / 155.0)
        )
        return max(0.0, ridge * blend)

    def elevation_at(self, x, y):
        """Return cached site elevation where available, else procedural relief."""
        if self._elevation_grid and self._elevation_grid.contains(x, y):
            return self._elevation_grid.elevation(x, y)
        return self.terrain_elevation(x, y)

    def _draw_terrain_relief(self):
        """Add real mesh relief so lighting and depth come from geometry."""
        extent = 1500.0
        cells = 40
        coordinates = np.linspace(-extent, extent, cells + 1)
        vertices = [
            [float(x), float(y), self.elevation_at(x, y) + 0.02]
            for y in coordinates
            for x in coordinates
        ]
        indices = []
        row = cells + 1
        for iy in range(cells):
            for ix in range(cells):
                lower_left = iy * row + ix
                lower_right = lower_left + 1
                upper_left = lower_left + row
                upper_right = upper_left + 1
                indices.extend(
                    [
                        lower_left, lower_right, upper_right,
                        lower_left, upper_right, upper_left,
                    ]
                )
        terrain_collision = pybullet.createCollisionShape(
            pybullet.GEOM_MESH,
            vertices=vertices,
            indices=indices,
            flags=pybullet.GEOM_FORCE_CONCAVE_TRIMESH,
            physicsClientId=self.client,
        )
        terrain_visual = pybullet.createVisualShape(
            pybullet.GEOM_MESH,
            vertices=vertices,
            indices=indices,
            rgbaColor=[0.20, 0.23, 0.18, 1.0],
            specularColor=[0.02, 0.02, 0.02],
            physicsClientId=self.client,
        )
        pybullet.createMultiBody(
            0,
            baseCollisionShapeIndex=terrain_collision,
            baseVisualShapeIndex=terrain_visual,
            physicsClientId=self.client,
        )

    def _draw_land_cover(self):
        """Layer deterministic field parcels over relief to expose scale and motion."""
        extent = 1260.0
        cell_size = 360.0
        gap = 10.0
        palette = (
            [0.24, 0.28, 0.17, 1.0],
            [0.31, 0.30, 0.18, 1.0],
            [0.19, 0.27, 0.20, 1.0],
            [0.28, 0.25, 0.17, 1.0],
        )
        for row, y0 in enumerate(np.arange(-extent, extent, cell_size)):
            for column, x0 in enumerate(np.arange(-extent, extent, cell_size)):
                x1 = min(x0 + cell_size - gap, extent)
                y1 = min(y0 + cell_size - gap, extent)
                center_x = (x0 + x1) * 0.5
                center_y = (y0 + y1) * 0.5
                if math.hypot(center_x, center_y) < 260.0:
                    continue
                vertices = [
                    [x0, y0, self.elevation_at(x0, y0) + 0.04],
                    [x1, y0, self.elevation_at(x1, y0) + 0.04],
                    [x1, y1, self.elevation_at(x1, y1) + 0.04],
                    [x0, y1, self.elevation_at(x0, y1) + 0.04],
                ]
                visual = pybullet.createVisualShape(
                    pybullet.GEOM_MESH,
                    vertices=vertices,
                    indices=[0, 1, 2, 0, 2, 3],
                    rgbaColor=palette[(row * 3 + column) % len(palette)],
                    specularColor=[0.01, 0.01, 0.01],
                    physicsClientId=self.client,
                )
                pybullet.createMultiBody(
                    0,
                    baseVisualShapeIndex=visual,
                    physicsClientId=self.client,
                )

    def _draw_real_map(self):
        if not self._site_config:
            return
        map_config = self._site_config.get("map", {})
        features = load_osm_features(
            map_config.get("osm_cache"),
            self._site_config["origin"],
            float(map_config.get("radius_m", 900.0)),
        )
        default_height = float(map_config.get("building_default_height_m", 8.0))
        for road in features["roads"]:
            for start, end in zip(road, road[1:]):
                dx = end[0] - start[0]
                dy = end[1] - start[1]
                length = math.hypot(dx, dy)
                if length < 0.5:
                    continue
                road_vis = pybullet.createVisualShape(
                    pybullet.GEOM_BOX,
                    halfExtents=[length / 2, 2.2, 0.025],
                    rgbaColor=[0.30, 0.31, 0.29, 1.0],
                    physicsClientId=self.client,
                )
                yaw = math.atan2(dy, dx)
                pybullet.createMultiBody(
                    0,
                    baseVisualShapeIndex=road_vis,
                    basePosition=[
                        (start[0] + end[0]) / 2,
                        (start[1] + end[1]) / 2,
                        self.elevation_at(
                            (start[0] + end[0]) / 2,
                            (start[1] + end[1]) / 2,
                        ) + 0.07,
                    ],
                    baseOrientation=pybullet.getQuaternionFromEuler([0, 0, yaw]),
                    physicsClientId=self.client,
                )
        for building in features["buildings"]:
            points = building["points"]
            xs = [point[0] for point in points]
            ys = [point[1] for point in points]
            width = max(max(xs) - min(xs), 1.0)
            depth = max(max(ys) - min(ys), 1.0)
            height = building["height_m"] or default_height
            center_x = (max(xs) + min(xs)) / 2
            center_y = (max(ys) + min(ys)) / 2
            center = [
                center_x,
                center_y,
                self.elevation_at(center_x, center_y) + height / 2,
            ]
            collision = pybullet.createCollisionShape(
                pybullet.GEOM_BOX,
                halfExtents=[width / 2, depth / 2, height / 2],
                physicsClientId=self.client,
            )
            shade = 0.28 + 0.06 * (
                abs(int(center[0] * 7 + center[1] * 11)) % 5
            ) / 4.0
            visual = pybullet.createVisualShape(
                pybullet.GEOM_BOX,
                halfExtents=[width / 2, depth / 2, height / 2],
                rgbaColor=[shade, shade * 1.02, shade * 0.97, 1.0],
                physicsClientId=self.client,
            )
            pybullet.createMultiBody(
                0, collision, visual, center, physicsClientId=self.client
            )
            roof = pybullet.createVisualShape(
                pybullet.GEOM_BOX,
                halfExtents=[width / 2 + 0.15, depth / 2 + 0.15, 0.12],
                rgbaColor=[shade * 0.72, shade * 0.74, shade * 0.70, 1.0],
                physicsClientId=self.client,
            )
            pybullet.createMultiBody(
                0,
                baseVisualShapeIndex=roof,
                basePosition=[
                    center_x,
                    center_y,
                    self.elevation_at(center_x, center_y) + height + 0.12,
                ],
                physicsClientId=self.client,
            )

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

    def capture_tactical_view(
        self,
        intruder_position=None,
        interceptor_position=None,
        intruder_velocity=None,
        interceptor_velocity=None,
        predicted_intercept=None,
        view_mode="overview",
        width=640,
        height=360,
        include_metadata=False,
    ):
        intruder = (
            np.asarray(intruder_position, dtype=float)
            if intruder_position is not None else None
        )
        interceptor = (
            np.asarray(interceptor_position, dtype=float)
            if interceptor_position is not None else None
        )

        if view_mode == "shahed" and intruder is not None:
            forward = self._camera_direction(
                intruder_velocity,
                -intruder,
            )
            lateral = np.cross(forward, np.asarray([0.0, 0.0, 1.0]))
            lateral /= max(float(np.linalg.norm(lateral)), 1e-6)
            eye = (
                intruder
                - forward * 12.0
                + lateral * 4.5
                + np.asarray([0.0, 0.0, 4.0])
            )
            focus = intruder + forward * 16.0
            fov = 36.0
        elif view_mode == "interceptor" and interceptor is not None:
            forward = self._camera_direction(
                interceptor_velocity,
                intruder - interceptor if intruder is not None else -interceptor,
            )
            eye = interceptor - forward * 12.0 + np.asarray([0.0, 0.0, 4.0])
            focus = interceptor + forward * 58.0
            fov = 48.0
        elif view_mode == "topdown":
            points = [p for p in (intruder, interceptor) if p is not None]
            focus = np.mean(points, axis=0) if points else np.zeros(3)
            focus[2] = 0.0
            separation = (
                float(np.linalg.norm(intruder - interceptor))
                if intruder is not None and interceptor is not None else 300.0
            )
            eye = focus + np.asarray([
                0.0,
                0.0,
                min(850.0, max(360.0, separation * 1.35)),
            ])
            fov = 48.0
        else:
            points = [p for p in (intruder, interceptor) if p is not None]
            if points:
                focus = np.mean(points, axis=0)
                focus[2] = max(20.0, min(120.0, focus[2] * 0.45))
            else:
                focus = np.asarray([0.0, 0.0, 45.0])
            separation = (
                float(np.linalg.norm(intruder - interceptor))
                if intruder is not None and interceptor is not None else 300.0
            )
            camera_distance = min(560.0, max(300.0, separation * 1.12))
            eye = focus + camera_distance * np.asarray([0.56, -0.72, 0.48])
            fov = 46.0

        view = pybullet.computeViewMatrix(
            cameraEyePosition=eye.tolist(),
            cameraTargetPosition=focus.tolist(),
            cameraUpVector=(
                [0.0, 1.0, 0.0]
                if view_mode == "topdown"
                else [0.0, 0.0, 1.0]
            ),
        )
        projection = pybullet.computeProjectionMatrixFOV(
            fov=fov,
            aspect=width / height,
            nearVal=1.0,
            farVal=2500.0,
        )
        image = pybullet.getCameraImage(
            width,
            height,
            viewMatrix=view,
            projectionMatrix=projection,
            renderer=self.camera_renderer,
            flags=pybullet.ER_NO_SEGMENTATION_MASK,
            lightDirection=[-0.45, -0.35, -1.0],
            lightColor=[1.0, 0.96, 0.88],
            lightDistance=1800.0,
            shadow=1,
            lightAmbientCoeff=0.38,
            lightDiffuseCoeff=0.62,
            lightSpecularCoeff=0.08,
            physicsClientId=self.client,
        )
        rgb = np.asarray(image[2], dtype=np.uint8).reshape(height, width, 4)[:, :, :3]
        depth = np.asarray(image[3], dtype=np.float32).reshape(height, width)
        rgb = self._grade_tactical_frame(rgb, depth)
        if not include_metadata:
            return rgb

        points = {
            "intruder": intruder,
            "interceptor": interceptor,
            "predicted_intercept": (
                np.asarray(predicted_intercept, dtype=float)
                if predicted_intercept is not None else None
            ),
        }
        return {
            "frame": rgb,
            "view_mode": view_mode,
            "screen_points": {
                name: self._project_to_screen(point, view, projection, width, height)
                for name, point in points.items()
                if point is not None
            },
        }

    @staticmethod
    def _camera_direction(preferred, fallback):
        direction = np.asarray(
            preferred if preferred is not None else fallback,
            dtype=float,
        )
        magnitude = float(np.linalg.norm(direction))
        if magnitude < 1e-6:
            return np.asarray([1.0, 0.0, 0.0])
        return direction / magnitude

    @staticmethod
    def _project_to_screen(point, view, projection, width, height):
        view_matrix = np.asarray(view, dtype=float).reshape((4, 4), order="F")
        projection_matrix = np.asarray(projection, dtype=float).reshape((4, 4), order="F")
        clip = projection_matrix @ view_matrix @ np.append(point, 1.0)
        if clip[3] <= 0.0:
            return None
        ndc = clip[:3] / clip[3]
        if np.any(np.abs(ndc[:2]) > 1.15) or not (-1.0 <= ndc[2] <= 1.0):
            return None
        return [
            float((ndc[0] + 1.0) * 0.5 * width),
            float((1.0 - ndc[1]) * 0.5 * height),
        ]

    @staticmethod
    def _grade_tactical_frame(rgb, depth):
        graded_float = np.clip(
            np.power(rgb.astype(np.float32) / 255.0, 0.92) * 255.0,
            0,
            255,
        )
        gradient_y, gradient_x = np.gradient(depth)
        relief = np.clip(
            1.0 - (gradient_x * 45.0 + gradient_y * 30.0),
            0.82,
            1.12,
        )
        graded_float *= relief[:, :, None]
        near, far = 1.0, 2500.0
        distance = far * near / np.maximum(
            far - (far - near) * depth,
            1e-6,
        )
        fog = np.clip((distance - 520.0) / 1350.0, 0.0, 0.52)
        atmosphere = np.asarray([116.0, 128.0, 136.0])
        graded_float = (
            graded_float * (1.0 - fog[:, :, None])
            + atmosphere * fog[:, :, None]
        )
        graded = np.clip(graded_float, 0, 255).astype(np.uint8)
        sky = depth >= 0.9999
        if np.any(sky):
            rows = np.linspace(0.0, 1.0, rgb.shape[0], dtype=np.float32)[:, None]
            top = np.asarray([34.0, 57.0, 78.0])
            horizon = np.asarray([137.0, 156.0, 166.0])
            gradient = top + (horizon - top) * rows[:, :, None]
            sky_rgb = np.broadcast_to(gradient, graded.shape)
            graded[sky] = sky_rgb[sky].astype(np.uint8)
        return graded

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
