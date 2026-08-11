"""Measure candidate-detector sensitivity to controlled target pixel width.

This is a synthetic-rescaling experiment.  It uses annotated source imagery but
does not claim to measure distant-camera performance or a held-out detector.
"""
from __future__ import annotations

import argparse
import csv
import random
import statistics
import sys
import time
from pathlib import Path

from bench_common import NOT_MEASURED, metadata, write_artifact

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

SCHEMA = "larp.pixel-floor.v1"
PATHS = ("full_frame_resize", "centre_crop", "native_tiles")


def root_path() -> Path:
    return Path(__file__).resolve().parent.parent


def iou(a, b) -> float:
    left, top = max(a[0], b[0]), max(a[1], b[1])
    right, bottom = min(a[2], b[2]), min(a[3], b[3])
    intersection = max(0, right - left) * max(0, bottom - top)
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - intersection
    return intersection / union if union else 0.0


def yolo_boxes(label_path: Path, width: int, height: int):
    for line in label_path.read_text(encoding="utf-8").splitlines():
        values = [float(value) for value in line.split()]
        if len(values) != 5:
            continue
        _, x, y, w, h = values
        yield ((x - w / 2) * width, (y - h / 2) * height, (x + w / 2) * width, (y + h / 2) * height)


def labelled_images(dataset: Path, minimum_width: int):
    import cv2
    pairs = []
    for image_path in sorted(dataset.rglob("images/*")):
        if image_path.suffix.lower() not in {".jpg", ".jpeg", ".png"}:
            continue
        label_path = image_path.parent.parent / "labels" / f"{image_path.stem}.txt"
        if not label_path.is_file():
            continue
        image = cv2.imread(str(image_path))
        if image is None:
            continue
        width, height = image.shape[1], image.shape[0]
        boxes = [box for box in yolo_boxes(label_path, width, height) if box[2] - box[0] >= minimum_width]
        if boxes:
            pairs.append((image_path, boxes[0]))
    return pairs


def synthetic_frame(source, box, background, target_width: int, canvas_size=(1920, 1080)):
    """Paste a padded annotated crop at centre, preserving known target geometry."""
    import cv2
    x1, y1, x2, y2 = map(int, box)
    padding = max(12, int(max(x2 - x1, y2 - y1) * .35))
    sx1, sy1 = max(0, x1-padding), max(0, y1-padding)
    sx2, sy2 = min(source.shape[1], x2+padding), min(source.shape[0], y2+padding)
    crop = source[sy1:sy2, sx1:sx2]
    scale = target_width / (x2 - x1)
    resized = cv2.resize(crop, (max(1, round(crop.shape[1]*scale)), max(1, round(crop.shape[0]*scale))))
    canvas = cv2.resize(background, canvas_size).copy()
    ox = (canvas_size[0] - resized.shape[1]) // 2
    oy = (canvas_size[1] - resized.shape[0]) // 2
    if ox < 0 or oy < 0:
        raise ValueError("scaled crop exceeds synthetic canvas")
    canvas[oy:oy+resized.shape[0], ox:ox+resized.shape[1]] = resized
    target = (ox + (x1-sx1)*scale, oy + (y1-sy1)*scale, ox + (x2-sx1)*scale, oy + (y2-sy1)*scale)
    return canvas, target


def detections(model, image):
    result = model.predict(source=image, imgsz=640, conf=.001, verbose=False)[0]
    boxes = result.boxes
    if boxes is None:
        return []
    return [(tuple(map(float, xyxy)), float(conf)) for xyxy, conf in zip(boxes.xyxy.cpu().numpy(), boxes.conf.cpu().numpy())]


def run_path(model, image, target, path: str, overlap: float):
    import cv2
    started = time.perf_counter()
    if path == "full_frame_resize":
        prepared = cv2.resize(image, (640, 640))
        sx, sy = 640 / image.shape[1], 640 / image.shape[0]
        truth = (target[0]*sx, target[1]*sy, target[2]*sx, target[3]*sy)
        found = detections(model, prepared)
    elif path == "centre_crop":
        x, y = (image.shape[1]-640)//2, (image.shape[0]-640)//2
        prepared = image[y:y+640, x:x+640]
        truth = tuple((target[i] - (x if i % 2 == 0 else y)) for i in range(4))
        found = detections(model, prepared)
    else:
        stride = max(1, round(640 * (1-overlap)))
        found, truth = [], target
        for y in range(0, image.shape[0]-639, stride):
            for x in range(0, image.shape[1]-639, stride):
                for box, confidence in detections(model, image[y:y+640, x:x+640]):
                    found.append(((box[0]+x, box[1]+y, box[2]+x, box[3]+y), confidence))
    elapsed_ms = (time.perf_counter() - started) * 1000
    matches = [confidence for box, confidence in found if iou(box, truth) >= .5]
    return bool(matches), max(matches) if matches else 0.0, elapsed_ms


def threshold(rows, level: float):
    eligible = [row["target_width_px"] for row in rows if row["detection_rate"] >= level]
    return min(eligible) if eligible else NOT_MEASURED


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", default="data/public/shahed-ubivw")
    parser.add_argument("--model-manifest", default="models/vision/drone_detector_candidate.json")
    parser.add_argument("--widths", type=int, nargs="+", default=list(range(4, 65, 4)))
    parser.add_argument("--sources", type=int, default=20)
    parser.add_argument("--tile-overlap", type=float, default=.2)
    parser.add_argument("--seed", type=int, default=20260811)
    args = parser.parse_args()
    if not 0 <= args.tile_overlap < 1 or args.sources < 1 or any(width < 4 for width in args.widths):
        parser.error("invalid sweep configuration")
    root = root_path(); dataset = (root / args.dataset).resolve()
    from integration.vision_model import load_vision_model_manifest
    manifest = load_vision_model_manifest(str(root / args.model_manifest), require_artifact=True)
    candidates = labelled_images(dataset, minimum_width=max(args.widths))
    if not candidates:
        raise RuntimeError("no labelled source object is large enough for the requested sweep")
    rng = random.Random(args.seed); selected = rng.sample(candidates, min(args.sources, len(candidates)))
    import cv2
    from ultralytics import YOLO
    model = YOLO(manifest.artifact_path)
    rows = []
    for width in args.widths:
        outcomes = {path: [] for path in PATHS}
        for index, (image_path, box) in enumerate(selected):
            source = cv2.imread(str(image_path)); background = cv2.imread(str(selected[(index+1) % len(selected)][0]))
            image, truth = synthetic_frame(source, box, background, width)
            for path in PATHS:
                detected, confidence, elapsed = run_path(model, image, truth, path, args.tile_overlap)
                outcomes[path].append((detected, confidence, elapsed))
        for path, values in outcomes.items():
            rows.append({"target_width_px": width, "path": path, "samples": len(values), "detection_rate": sum(value[0] for value in values)/len(values), "mean_confidence": statistics.mean(value[1] for value in values), "mean_processing_ms": statistics.mean(value[2] for value in values)})
    record = {"schema": SCHEMA, **metadata(root, {"dataset": str(dataset), "model": manifest.locked_model_id, "widths_px": args.widths, "sources": len(selected), "tile_overlap": args.tile_overlap, "seed": args.seed}), "scope": "Measured on synthetic rescaled annotated imagery with a checksum-locked candidate model; not field detection performance.", "caveats": ["Rescaling lacks real low-signal sensor noise, atmospheric effects, and motion blur.", "Sky and clutter performance are not separated by this dataset.", "Candidate model is not held-out validated."], "results": rows, "pixel_floor": {path: {"detection_rate_50_percent_px": threshold([row for row in rows if row["path"] == path], .5), "detection_rate_90_percent_px": threshold([row for row in rows if row["path"] == path], .9)} for path in PATHS}}
    path = write_artifact(root, "vision", "pixel_floor", record)
    csv_path = path.with_suffix(".csv")
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=rows[0].keys()); writer.writeheader(); writer.writerows(rows)
    print(path); print(csv_path); return 0


if __name__ == "__main__": raise SystemExit(main())
