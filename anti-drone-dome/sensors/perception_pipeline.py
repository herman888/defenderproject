"""Camera-agnostic capture → preprocess → detect → track → log pipeline.

Backends are selected solely in :class:`PipelineConfig`; detector and tracker
code never branch on operating system or camera transport.  The libcamera class
is deliberately a conforming stub until a Pi CSI camera is present.
"""
from __future__ import annotations

import platform
import time
from dataclasses import asdict, dataclass
from typing import Any, Callable, Protocol


@dataclass(frozen=True)
class CameraConfig:
    backend: str
    device: str | int
    width: int
    height: int
    fps: float
    fourcc: str = "MJPG"
    identity: str = "NOT MEASURED"
    fov_degrees: float | str = "NOT MEASURED"


@dataclass(frozen=True)
class PreprocessConfig:
    mode: str = "centre_crop"  # full_frame_resize, centre_crop, native_tiles
    crop_size: int = 640
    crop_centre: tuple[float, float] = (0.5, 0.5)
    tile_overlap: float = 0.2


@dataclass(frozen=True)
class PipelineConfig:
    camera: CameraConfig
    preprocess: PreprocessConfig
    model_sha256: str


class CaptureBackend(Protocol):
    name: str
    def open(self, config: CameraConfig) -> None: ...
    def read(self) -> Any: ...
    def close(self) -> None: ...


class OpenCVCaptureBackend:
    """DirectShow on Windows and V4L2 on Linux through one interface."""
    name = "opencv"

    def __init__(self, api_preference: int | None = None):
        self._api_preference = api_preference
        self._capture = None

    def open(self, config: CameraConfig) -> None:
        import cv2
        api = self._api_preference
        if api is None:
            api = cv2.CAP_DSHOW if platform.system() == "Windows" else cv2.CAP_V4L2
        self._capture = cv2.VideoCapture(config.device, api)
        if not self._capture.isOpened():
            raise RuntimeError(f"could not open {self.name} camera {config.device!r}")
        self._capture.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*config.fourcc))
        self._capture.set(cv2.CAP_PROP_FRAME_WIDTH, config.width)
        self._capture.set(cv2.CAP_PROP_FRAME_HEIGHT, config.height)
        self._capture.set(cv2.CAP_PROP_FPS, config.fps)
        self._capture.set(cv2.CAP_PROP_BUFFERSIZE, 1)

    def read(self) -> Any:
        if self._capture is None:
            raise RuntimeError("capture backend is not open")
        ok, frame = self._capture.read()
        if not ok or frame is None:
            raise RuntimeError("camera returned no frame")
        return frame

    def close(self) -> None:
        if self._capture is not None:
            self._capture.release()
            self._capture = None


class DirectShowCaptureBackend(OpenCVCaptureBackend):
    name = "directshow"


class V4L2CaptureBackend(OpenCVCaptureBackend):
    name = "v4l2"


class LibcameraCaptureBackend:
    """Interface-complete CSI backend placeholder; intentionally not runnable yet."""
    name = "libcamera"
    def open(self, config: CameraConfig) -> None:
        raise NotImplementedError("libcamera backend awaits Pi CSI camera qualification")
    def read(self) -> Any:
        raise RuntimeError("libcamera backend is not open")
    def close(self) -> None:
        return None


def capture_backend(name: str) -> CaptureBackend:
    choices = {"directshow": DirectShowCaptureBackend, "v4l2": V4L2CaptureBackend,
               "libcamera": LibcameraCaptureBackend}
    try:
        return choices[name]()
    except KeyError as exc:
        raise ValueError(f"unknown capture backend {name!r}; choose {sorted(choices)}") from exc


def preprocess(frame: Any, config: PreprocessConfig) -> list[tuple[Any, tuple[int, int]]]:
    """Return image regions with their native-frame origin for detection merge."""
    import cv2
    height, width = frame.shape[:2]
    size = config.crop_size
    if config.mode == "full_frame_resize":
        return [(cv2.resize(frame, (size, size)), (0, 0))]
    if config.mode == "centre_crop":
        x = round((width - size) * config.crop_centre[0]); y = round((height - size) * config.crop_centre[1])
        x, y = max(0, min(x, width-size)), max(0, min(y, height-size))
        return [(frame[y:y+size, x:x+size], (x, y))]
    if config.mode == "native_tiles":
        stride = max(1, round(size * (1 - config.tile_overlap)))
        return [(frame[y:y+size, x:x+size], (x, y))
                for y in range(0, height-size+1, stride) for x in range(0, width-size+1, stride)]
    raise ValueError(f"unknown preprocess mode {config.mode!r}")


class PerceptionPipeline:
    def __init__(self, config: PipelineConfig, detector: Callable[[Any], list[dict]], tracker: Callable[[list[dict]], Any]):
        self.config, self.detector, self.tracker = config, detector, tracker

    def process_frame(self, frame: Any) -> dict:
        started = time.perf_counter_ns()
        regions = preprocess(frame, self.config.preprocess); preprocessed = time.perf_counter_ns()
        detections = []
        for image, (x, y) in regions:
            for detection in self.detector(image):
                translated = dict(detection)
                if "bbox" in translated:
                    a, b, c, d = translated["bbox"]; translated["bbox"] = (a+x, b+y, c+x, d+y)
                detections.append(translated)
        detected = time.perf_counter_ns()
        track = self.tracker(detections); tracked = time.perf_counter_ns()
        return {"schema": "larp.perception-frame.v1", "camera": asdict(self.config.camera),
                "preprocess": asdict(self.config.preprocess), "model_sha256": self.config.model_sha256,
                "detections": detections, "track": track,
                "timestamps_ns": {"capture_complete": started, "preprocess_complete": preprocessed,
                                  "detection_complete": detected, "track_complete": tracked},
                "durations_ms": {"capture_to_detection": (detected-started)/1e6,
                                 "detection_to_track": (tracked-detected)/1e6}}
