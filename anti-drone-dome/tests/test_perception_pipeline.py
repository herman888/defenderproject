import numpy as np
import pytest

from sensors.perception_pipeline import (CameraConfig, IoUTracker, LibcameraCaptureBackend,
    PerceptionPipeline, PipelineConfig, PreprocessConfig, capture_backend)


def test_backend_selection_is_config_only_and_libcamera_satisfies_interface():
    config = PipelineConfig(CameraConfig("libcamera", 0, 1920, 1080, 30), PreprocessConfig(), "0" * 64)
    assert isinstance(capture_backend(config.camera.backend), LibcameraCaptureBackend)
    with pytest.raises(NotImplementedError):
        capture_backend(config.camera.backend).open(config.camera)


def test_pipeline_logs_independent_stage_timestamps_without_backend_logic():
    config = PipelineConfig(CameraConfig("directshow", 1, 640, 480, 30, identity="InnoMaker"), PreprocessConfig(), "a" * 64)
    pipeline = PerceptionPipeline(config, lambda image: [{"bbox": (1, 2, 3, 4), "confidence": .8}], lambda hits: {"count": len(hits)})
    record = pipeline.process_frame(np.zeros((480, 640, 3), dtype=np.uint8))
    assert record["camera"]["identity"] == "InnoMaker"
    assert record["track"] == {"count": 1}
    assert set(record["timestamps_ns"]) == {"capture_complete", "preprocess_complete", "detection_complete", "track_complete"}


def test_iou_tracker_preserves_id_for_overlapping_detection():
    tracker = IoUTracker()
    first = tracker([{"bbox": (0, 0, 10, 10)}])[0]["tracker_id"]
    second = tracker([{"bbox": (1, 1, 11, 11)}])[0]["tracker_id"]
    assert first == second
