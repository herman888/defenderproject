"""Versioned perception telemetry for an onboard companion computer."""

from __future__ import annotations

import json
import math


SCHEMA = "aegis.companion-perception.v1"


def build_perception_packet(
    sequence: int,
    timestamp_ns: int,
    frame_id: str,
    image_size: tuple[int, int],
    detections: list[dict],
    *,
    source: str = "innomaker-uvc",
    model_id: str | None = None,
    timestamp_clock: str | None = None,
) -> dict:
    if sequence < 0 or timestamp_ns < 0:
        raise ValueError("sequence and timestamp_ns must be non-negative")
    if not frame_id:
        raise ValueError("frame_id is required")
    width, height = (int(value) for value in image_size)
    if width <= 0 or height <= 0:
        raise ValueError("image dimensions must be positive")
    normalized = []
    for detection in detections:
        confidence = float(detection["confidence"])
        bbox = [float(value) for value in detection["bbox_xyxy"]]
        if len(bbox) != 4 or not all(math.isfinite(value) for value in bbox):
            raise ValueError("bbox_xyxy must contain four finite values")
        x1, y1, x2, y2 = bbox
        if not 0.0 <= confidence <= 1.0:
            raise ValueError("detection confidence must be in [0, 1]")
        if not (0.0 <= x1 < x2 <= width and 0.0 <= y1 < y2 <= height):
            raise ValueError("detection bounding box is outside the image")
        normalized.append({
            "class_id": int(detection["class_id"]),
            "label": str(detection["label"]),
            "confidence": confidence,
            "bbox_xyxy": bbox,
        })
    packet = {
        "schema": SCHEMA,
        "sequence": int(sequence),
        "timestamp_ns": int(timestamp_ns),
        "frame_id": frame_id,
        "source": source,
        "image": {"width": width, "height": height},
        "detections": normalized,
    }
    if model_id:
        packet["model_id"] = model_id
    if timestamp_clock:
        if timestamp_clock not in {"monotonic", "recording-relative", "ptp"}:
            raise ValueError("unsupported timestamp clock")
        packet["timestamp_clock"] = timestamp_clock
    return packet


def encode_perception_packet(packet: dict) -> bytes:
    if packet.get("schema") != SCHEMA:
        raise ValueError(f"companion packet schema must be {SCHEMA}")
    return json.dumps(
        packet, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")
