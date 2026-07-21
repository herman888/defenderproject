"""Run a checksum-locked detector over recorded media and emit perception JSONL."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from integration.companion_link import encode_perception_packet
from integration.vision_model import (
    load_vision_model_manifest,
    resolve_inference_device,
)
from integration.vision_replay import (
    build_recorded_replay_packet,
    detections_from_ultralytics,
)


_IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".bmp"}


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _source_files(source: Path) -> list[Path]:
    if source.is_file():
        return [source]
    if source.is_dir():
        files = sorted(
            path for path in source.iterdir()
            if path.is_file() and path.suffix.lower() in _IMAGE_SUFFIXES
        )
        if not files:
            raise ValueError(f"recording directory contains no supported images: {source}")
        return files
    raise FileNotFoundError(f"recording source does not exist: {source}")


def _source_digest(files: list[Path]) -> str:
    digest = hashlib.sha256()
    for path in files:
        digest.update(path.name.encode("utf-8"))
        digest.update(_sha256_file(path).encode("ascii"))
    return digest.hexdigest()


def _iter_frames(source: Path, fps_override: float | None):
    import cv2

    if source.is_dir() or source.suffix.lower() in _IMAGE_SUFFIXES:
        files = _source_files(source)
        fps = fps_override or 30.0
        for sequence, path in enumerate(files):
            frame = cv2.imread(str(path))
            if frame is None:
                raise ValueError(f"OpenCV could not decode image: {path}")
            yield sequence, int(sequence * 1_000_000_000 / fps), path.name, frame
        return

    capture = cv2.VideoCapture(str(source))
    if not capture.isOpened():
        raise ValueError(f"OpenCV could not open video: {source}")
    fps = fps_override or float(capture.get(cv2.CAP_PROP_FPS))
    if fps <= 0:
        capture.release()
        raise ValueError("video FPS is unavailable; provide --fps")
    sequence = 0
    try:
        while True:
            ok, frame = capture.read()
            if not ok:
                break
            yield (
                sequence,
                int(sequence * 1_000_000_000 / fps),
                f"{source.name}:{sequence:08d}",
                frame,
            )
            sequence += 1
    finally:
        capture.release()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, help="Video, image, or image directory")
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--output", required=True, help="Perception JSONL output")
    parser.add_argument("--report", help="Replay report JSON path")
    parser.add_argument("--device", choices=("auto", "cpu", "cuda"))
    parser.add_argument("--fps", type=float, help="Override recording/image FPS")
    parser.add_argument("--max-frames", type=int)
    args = parser.parse_args()
    if args.fps is not None and args.fps <= 0:
        parser.error("--fps must be positive")
    if args.max_frames is not None and args.max_frames <= 0:
        parser.error("--max-frames must be positive")

    source = Path(args.input).resolve()
    source_files = _source_files(source)
    manifest = load_vision_model_manifest(args.manifest, require_artifact=True)
    inference = manifest.data["inference"]
    device_request = args.device or inference["device"]
    device = resolve_inference_device(device_request)

    from ultralytics import YOLO

    model = YOLO(manifest.artifact_path)
    class_labels = {
        item["id"]: item["label"] for item in manifest.data["classes"]
    }
    model_input = manifest.data["input"]
    output = Path(args.output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    started = time.perf_counter()
    frame_count = 0
    detection_count = 0
    with output.open("wb") as handle:
        for sequence, timestamp_ns, frame_name, frame in _iter_frames(
            source, args.fps
        ):
            if args.max_frames is not None and sequence >= args.max_frames:
                break
            result = model.predict(
                source=frame,
                conf=float(inference["confidence_threshold"]),
                iou=float(inference["iou_threshold"]),
                imgsz=(model_input["height"], model_input["width"]),
                device=device,
                verbose=False,
            )[0]
            detections = detections_from_ultralytics(result, class_labels)
            height, width = frame.shape[:2]
            packet = build_recorded_replay_packet(
                sequence=sequence,
                timestamp_ns=timestamp_ns,
                frame_name=frame_name,
                image_size=(width, height),
                detections=detections,
                model_id=manifest.locked_model_id,
            )
            handle.write(encode_perception_packet(packet) + b"\n")
            frame_count += 1
            detection_count += len(detections)
    elapsed = time.perf_counter() - started
    if frame_count == 0:
        raise ValueError("recording produced no decodable frames")

    report = {
        "schema": "aegis.vision-replay-report.v1",
        "source": str(source),
        "source_sha256": _source_digest(source_files),
        "model_id": manifest.locked_model_id,
        "backend": inference["backend"],
        "device": "cuda:0" if device == 0 else device,
        "frames": frame_count,
        "detections": detection_count,
        "elapsed_s": elapsed,
        "processing_rate_hz": frame_count / elapsed,
        "output": str(output),
        "output_sha256": _sha256_file(output),
        "performance_scope": "host recorded-media replay; not Pi or field performance",
        "actuation_enabled": False,
    }
    report_path = Path(args.report).resolve() if args.report else Path(
        str(output) + ".report.json"
    )
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
