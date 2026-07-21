"""Rendered electro-optical sensor using PyBullet RGB/depth/segmentation."""

import math

import numpy as np
import pybullet


class RenderedCameraSensor:
    def __init__(
        self,
        physics_client,
        position=(0.0, 0.0, 12.0),
        width=160,
        height=120,
        fov_deg=50.0,
        max_range_m=1200.0,
        position_noise_std_m=1.5,
        dropout_probability=0.03,
        model_path=None,
        model_device=None,
        renderer=pybullet.ER_TINY_RENDERER,
        seed=None,
    ):
        self.client = physics_client
        self.position = np.asarray(position, dtype=float)
        self.width = int(width)
        self.height = int(height)
        self.fov_deg = float(fov_deg)
        self.max_range_m = float(max_range_m)
        self.position_noise_std_m = float(position_noise_std_m)
        self.dropout_probability = float(dropout_probability)
        self.model_device = model_device
        self.renderer = renderer
        self._model = None
        if model_path:
            from ultralytics import YOLO

            self._model = YOLO(model_path)
        self._rng = np.random.default_rng(seed)
        self._last_position = None
        self._last_time = None

    def observe(self, target_body_id, cue_position, timestamp):
        cue = np.asarray(cue_position, dtype=float)
        delta = cue - self.position
        distance = float(np.linalg.norm(delta))
        if distance < 0.5 or distance > self.max_range_m:
            return {"detected": False, "source": "camera"}
        if self._rng.random() < self.dropout_probability:
            return {"detected": False, "source": "camera", "dropped": True}

        view = pybullet.computeViewMatrix(
            cameraEyePosition=self.position.tolist(),
            cameraTargetPosition=cue.tolist(),
            cameraUpVector=[0.0, 0.0, 1.0],
        )
        projection = pybullet.computeProjectionMatrixFOV(
            fov=self.fov_deg,
            aspect=self.width / self.height,
            nearVal=0.5,
            farVal=self.max_range_m,
        )
        image = pybullet.getCameraImage(
            self.width,
            self.height,
            viewMatrix=view,
            projectionMatrix=projection,
            renderer=self.renderer,
            flags=pybullet.ER_SEGMENTATION_MASK_OBJECT_AND_LINKINDEX,
            physicsClientId=self.client,
        )
        depth = np.asarray(image[3], dtype=float).reshape(self.height, self.width)
        if self._model is None:
            segmentation = np.asarray(image[4], dtype=np.int64).reshape(
                self.height, self.width
            )
            object_ids = segmentation & ((1 << 24) - 1)
            pixels = np.argwhere(object_ids == int(target_body_id))
            if len(pixels) == 0:
                return {"detected": False, "source": "camera"}
            row, col = np.median(pixels, axis=0)
            row = int(round(row))
            col = int(round(col))
            pixel_count = int(len(pixels))
            model_confidence = None
            source = "camera_segmentation"
        else:
            rgb = np.asarray(image[2], dtype=np.uint8).reshape(
                self.height, self.width, 4
            )[:, :, :3]
            predict_options = {
                "conf": 0.15,
                "imgsz": max(self.width, self.height),
                "verbose": False,
            }
            if self.model_device is not None:
                predict_options["device"] = self.model_device
            result = self._model.predict(rgb, **predict_options)[0]
            if result.boxes is None or len(result.boxes) == 0:
                return {"detected": False, "source": "camera_yolo"}
            confidences = result.boxes.conf.detach().cpu().numpy()
            best = int(np.argmax(confidences))
            x1, y1, x2, y2 = (
                result.boxes.xyxy[best].detach().cpu().numpy().tolist()
            )
            col = int(round((x1 + x2) / 2.0))
            row = int(round((y1 + y2) / 2.0))
            col = max(0, min(self.width - 1, col))
            row = max(0, min(self.height - 1, row))
            pixel_count = max(1, int((x2 - x1) * (y2 - y1)))
            model_confidence = float(confidences[best])
            source = "camera_yolo"
        world_position = self._unproject(col, row, depth[row, col], view, projection)
        world_position += self._rng.normal(0.0, self.position_noise_std_m, 3)

        velocity = np.zeros(3)
        if self._last_position is not None and self._last_time is not None:
            dt = max(float(timestamp) - self._last_time, 1e-3)
            velocity = (world_position - self._last_position) / dt
        self._last_position = world_position.copy()
        self._last_time = float(timestamp)

        relative = world_position - self.position
        horizontal = math.hypot(relative[0], relative[1])
        pixel_fraction = pixel_count / float(self.width * self.height)
        confidence = (
            model_confidence
            if model_confidence is not None
            else min(1.0, 0.35 + 12.0 * math.sqrt(pixel_fraction))
        )
        return {
            "detected": True,
            "source": source,
            "position_estimate": tuple(world_position),
            "velocity": tuple(velocity),
            "acceleration": (0.0, 0.0, 0.0),
            "range": float(np.linalg.norm(relative)),
            "bearing_deg": math.degrees(math.atan2(relative[1], relative[0])) % 360.0,
            "elevation_deg": math.degrees(math.atan2(relative[2], horizontal)),
            "confidence": confidence,
            "pixel_count": pixel_count,
        }

    def _unproject(self, col, row, depth, view, projection):
        view_matrix = np.asarray(view, dtype=float).reshape((4, 4), order="F")
        projection_matrix = np.asarray(projection, dtype=float).reshape(
            (4, 4), order="F"
        )
        clip = np.asarray([
            2.0 * (col + 0.5) / self.width - 1.0,
            1.0 - 2.0 * (row + 0.5) / self.height,
            2.0 * depth - 1.0,
            1.0,
        ])
        world = np.linalg.inv(projection_matrix @ view_matrix) @ clip
        return world[:3] / world[3]
