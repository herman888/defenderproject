"""PyBullet world setup: gravity, ground plane, dome wireframe, reference grid."""

import math
import os
import pybullet
import pybullet_data

_TIMESTEP = 1.0 / 240.0


class PhysicsWorld:
    def __init__(self, gui=True):
        self._gui = gui
        mode = pybullet.GUI if gui else pybullet.DIRECT
        self.client = pybullet.connect(mode)
        pybullet.setAdditionalSearchPath(pybullet_data.getDataPath(), physicsClientId=self.client)
        self._dome_lines = []
        self._grid_lines = []
        self._setup()

    def _setup(self):
        pybullet.setGravity(0, 0, -9.81, physicsClientId=self.client)
        pybullet.setTimeStep(_TIMESTEP, physicsClientId=self.client)
        pybullet.loadURDF("plane.urdf", physicsClientId=self.client)

        if self._gui:
            pybullet.resetDebugVisualizerCamera(
                cameraDistance=35,
                cameraYaw=45,
                cameraPitch=-25,
                cameraTargetPosition=[5, 5, 4],
                physicsClientId=self.client,
            )
            pybullet.configureDebugVisualizer(
                pybullet.COV_ENABLE_RGB_BUFFER_PREVIEW, 0, physicsClientId=self.client
            )
            self._draw_grid()

    def _draw_grid(self):
        half = 10
        color = [0.25, 0.25, 0.25]
        for i in range(-half, half + 1):
            self._grid_lines.append(
                pybullet.addUserDebugLine([i, -half, 0.01], [i, half, 0.01], color, physicsClientId=self.client)
            )
            self._grid_lines.append(
                pybullet.addUserDebugLine([-half, i, 0.01], [half, i, 0.01], color, physicsClientId=self.client)
            )

    def draw_dome(self, center, radius, color=None):
        if color is None:
            color = [0, 1, 0]
        for line_id in self._dome_lines:
            pybullet.removeUserDebugItem(line_id, physicsClientId=self.client)
        self._dome_lines.clear()

        cx, cy, cz = center
        lat_steps = 8
        lon_steps = 16
        pts_per_ring = 64

        # Latitude rings (upper hemisphere only)
        for lat_i in range(lat_steps + 1):
            lat = math.pi / 2 * lat_i / lat_steps  # 0 to pi/2
            ring = []
            for j in range(pts_per_ring + 1):
                lon = 2 * math.pi * j / pts_per_ring
                x = cx + radius * math.cos(lat) * math.cos(lon)
                y = cy + radius * math.cos(lat) * math.sin(lon)
                z = cz + radius * math.sin(lat)
                ring.append([x, y, z])
            for j in range(pts_per_ring):
                lid = pybullet.addUserDebugLine(ring[j], ring[j + 1], color, physicsClientId=self.client)
                self._dome_lines.append(lid)

        # Longitude lines
        for lon_i in range(lon_steps):
            lon = 2 * math.pi * lon_i / lon_steps
            prev = None
            for lat_i in range(lat_steps + 1):
                lat = math.pi / 2 * lat_i / lat_steps
                x = cx + radius * math.cos(lat) * math.cos(lon)
                y = cy + radius * math.cos(lat) * math.sin(lon)
                z = cz + radius * math.sin(lat)
                pt = [x, y, z]
                if prev is not None:
                    lid = pybullet.addUserDebugLine(prev, pt, color, physicsClientId=self.client)
                    self._dome_lines.append(lid)
                prev = pt

    def step(self):
        pybullet.stepSimulation(physicsClientId=self.client)

    def reset(self):
        pybullet.resetSimulation(physicsClientId=self.client)
        self._dome_lines.clear()
        self._grid_lines.clear()
        self._setup()

    def get_time(self):
        return pybullet.getPhysicsEngineParameters(physicsClientId=self.client)["fixedTimeStep"]
