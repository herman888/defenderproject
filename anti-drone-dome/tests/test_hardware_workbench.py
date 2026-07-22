import csv
import json
import math
import os
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from hardware.profile import load_hardware_profile, validate_hardware_profile
from integration.mission_record import MissionRecorder
from integration.companion_link import (
    build_perception_packet,
    encode_perception_packet,
)
from integration.vision_model import (
    load_vision_model_manifest,
    lock_vision_model_artifact,
    resolve_inference_device,
)
from integration.vision_replay import build_recorded_replay_packet
from validation.flight_log import compare_flight_logs, load_flight_log
from validation.model_calibration import build_calibration_report
from validation.workbench import evaluate_readiness
from viz.acmi_writer import ACMIWriter


ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))


def test_reference_and_readonly_profiles_enforce_safe_defaults():
    reference = load_hardware_profile(
        os.path.join(ROOT, "hardware_profiles", "reference_sil.json")
    )
    readonly = load_hardware_profile(
        os.path.join(ROOT, "hardware_profiles", "larp_betaflight_readonly.json")
    )
    assert reference.mode == "sil"
    assert readonly.mode == "hardware_readonly"
    assert readonly.protocol == "msp"
    assert not reference.actuation_enabled
    assert not readonly.actuation_enabled

    unsafe = json.loads(json.dumps(readonly.data))
    unsafe["safety"]["actuation_enabled"] = True
    with pytest.raises(ValueError, match="cannot enable actuation"):
        validate_hardware_profile(unsafe)


def test_pi_companion_profile_and_perception_contract_are_readonly():
    profile = load_hardware_profile(
        os.path.join(ROOT, "hardware_profiles", "raspberry_pi5_companion.json")
    )
    assert profile.mode == "hardware_readonly"
    assert not profile.actuation_enabled
    assert profile.summary()["compute"]["board"] == "Raspberry Pi 5"
    packet = build_perception_packet(
        7,
        123456789,
        "camera_optical",
        (1280, 720),
        [{
            "class_id": 0,
            "label": "drone",
            "confidence": 0.85,
            "bbox_xyxy": [10, 20, 40, 60],
        }],
        model_id="test-model",
    )
    encoded = encode_perception_packet(packet)
    assert json.loads(encoded)["schema"] == "aegis.companion-perception.v1"
    with pytest.raises(ValueError, match="outside the image"):
        build_perception_packet(
            8,
            123456790,
            "camera_optical",
            (1280, 720),
            [{
                "class_id": 0,
                "label": "drone",
                "confidence": 0.85,
                "bbox_xyxy": [-1, 20, 40, 60],
            }],
        )


def test_vision_manifest_locks_and_verifies_exact_artifact(tmp_path):
    artifact = tmp_path / "detector.pt"
    artifact.write_bytes(b"deterministic-test-weights")
    manifest_path = tmp_path / "model.json"
    manifest_path.write_text(json.dumps({
        "schema": "aegis.vision-model.v1",
        "model_id": "test-detector",
        "task": "object-detection",
        "artifact": {
            "path": "missing.pt",
            "format": "pytorch",
            "size_bytes": None,
            "sha256": None,
        },
        "input": {"width": 640, "height": 640, "color_space": "BGR"},
        "classes": [{"id": 0, "label": "drone"}],
        "inference": {
            "backend": "ultralytics",
            "device": "auto",
            "quantization": "none",
            "confidence_threshold": 0.25,
            "iou_threshold": 0.7,
        },
    }), encoding="utf-8")

    with pytest.raises(ValueError, match="not checksum-locked"):
        load_vision_model_manifest(str(manifest_path), require_artifact=True)
    locked = lock_vision_model_artifact(str(manifest_path), str(artifact))
    assert locked["artifact"]["size_bytes"] == artifact.stat().st_size
    manifest = load_vision_model_manifest(
        str(manifest_path), require_artifact=True
    )
    assert manifest.locked_model_id.startswith("test-detector@sha256:")
    artifact.write_bytes(b"tampered")
    with pytest.raises(ValueError, match="size mismatch"):
        manifest.verify_artifact()


def test_recorded_replay_marks_relative_clock_and_never_actuates():
    packet = build_recorded_replay_packet(
        sequence=3,
        timestamp_ns=100_000_000,
        frame_name="clip.mp4:00000003",
        image_size=(640, 480),
        detections=[{
            "class_id": 0,
            "label": "drone",
            "confidence": 0.9,
            "bbox_xyxy": [10, 20, 30, 40],
        }],
        model_id="test@sha256:123456789abc",
    )
    assert packet["timestamp_clock"] == "recording-relative"
    assert packet["source"] == "recorded-media-replay"
    assert "actuation" not in packet
    assert resolve_inference_device("cpu") == "cpu"


def test_mission_recorder_writes_hashed_manifest(tmp_path):
    profile = load_hardware_profile(
        os.path.join(ROOT, "hardware_profiles", "reference_sil.json")
    )
    recorder = MissionRecorder(
        str(tmp_path),
        mission={"pattern": "direct"},
        hardware_profile=profile.summary(),
    )
    recorder.record_snapshot({
        "mission_time": 1.0,
        "dome_status": "TRACKING",
        "intruder_pos": (1.0, 2.0, 3.0),
        "interceptor_pos": (0.0, 0.0, 1.0),
        "radar_return": {"detected": True},
        "fused_track": {"source": "RADAR"},
        "events": [{"time": 1.0, "type": "RADAR_ACQUIRE", "message": "Track"}],
        "camera_frame": np.zeros((720, 1280, 3), dtype=np.uint8),
    })
    recorder.finalize({"result": "INTERCEPTED"})
    loaded = json.loads(open(recorder.manifest_path, encoding="utf-8").read())
    assert loaded["result"]["result"] == "INTERCEPTED"
    assert loaded["sample_count"] == 1
    assert loaded["event_count"] == 1
    assert loaded["artifacts"]["telemetry"]["sha256"]
    assert loaded["artifacts"]["events"]["sha256"]
    telemetry = open(recorder.telemetry_path, encoding="utf-8").read()
    assert "camera_frame" not in telemetry
    assert os.path.getsize(recorder.telemetry_path) < 10_000


def test_ned_named_columns_convert_to_enu_and_align(tmp_path):
    path = tmp_path / "ned.csv"
    with open(path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle, fieldnames=["time_s", "north_m", "east_m", "down_m"]
        )
        writer.writeheader()
        writer.writerows([
            {"time_s": 0, "north_m": 10, "east_m": 20, "down_m": -5},
            {"time_s": 1, "north_m": 11, "east_m": 22, "down_m": -6},
            {"time_s": 2, "north_m": 12, "east_m": 24, "down_m": -7},
        ])
    loaded = load_flight_log(str(path), frame="NED")
    assert np.allclose(loaded["position_enu_m"][0], [20, 10, 5])
    comparison = compare_flight_logs(loaded, loaded)
    assert comparison["trajectory_rmse_m"] == pytest.approx(0.0)
    assert comparison["estimated_candidate_time_offset_s"] == pytest.approx(0.0)
    assert comparison["velocity_rmse_mps"] == pytest.approx(0.0)
    assert comparison["axis_bias_m"] == {
        "east": pytest.approx(0.0),
        "north": pytest.approx(0.0),
        "up": pytest.approx(0.0),
    }


def test_airframe_calibration_is_bounded_and_never_mutates_profile(tmp_path):
    reference = {
        "time_s": np.asarray([0.0, 1.0, 2.0]),
        "position_enu_m": np.asarray(
            [[0.0, 0.0, 0.0], [10.0, 0.0, 0.0], [20.0, 0.0, 0.0]]
        ),
    }
    simulation = {
        "time_s": np.asarray([0.0, 1.0, 2.0]),
        "position_enu_m": np.asarray(
            [[0.0, 0.0, 0.0], [5.0, 0.0, 0.0], [10.0, 0.0, 0.0]]
        ),
    }
    report = build_calibration_report(
        "interceptor.reference-v1", reference, simulation
    )
    assert report["recommendations"]["propulsion_force_scale"] == 1.2
    assert report["validation_status"] == "candidate-only"
    assert report["review_required"]
    assert not report["automatic_profile_mutation"]


def test_readiness_reports_lab_inputs_without_authorizing_actuation():
    profile = load_hardware_profile(
        os.path.join(ROOT, "hardware_profiles", "larp_betaflight_readonly.json")
    )
    readiness = evaluate_readiness(profile)
    required_failures = [
        item for item in readiness if item["required"] and not item["passed"]
    ]
    assert required_failures
    assert not profile.actuation_enabled
    assert any(
        "placeholder" in item["detail"].lower() for item in required_failures
    )
    assert any(
        "calibration" in item["detail"].lower() for item in required_failures
    )


def test_acmi_uses_current_format_and_latitude_scaled_longitude(tmp_path):
    writer = ACMIWriter(str(tmp_path))
    try:
        lat, lon, altitude = writer._to_latlon(111111.0, 0.0, 42.0)
        expected_delta = 1.0 / math.cos(math.radians(writer._REF_LAT))
        assert lat == pytest.approx(writer._REF_LAT)
        assert lon == pytest.approx(writer._REF_LON + expected_delta)
        assert altitude == 42.0
    finally:
        path = writer.filepath
        writer.close()
    content = open(path, encoding="utf-8").read()
    assert "FileType=text/acmi/tacview" in content
    assert "FileVersion=2.2" in content
    assert "ReferenceTime=2024-" not in content
