"""Deterministic packet generation for recorded camera replay."""

from __future__ import annotations

from integration.companion_link import build_perception_packet


def detections_from_ultralytics(result, class_labels: dict[int, str]) -> list[dict]:
    detections = []
    for box in result.boxes:
        class_id = int(box.cls[0])
        if class_id not in class_labels:
            raise ValueError(f"model emitted undeclared class id {class_id}")
        detections.append({
            "class_id": class_id,
            "label": class_labels[class_id],
            "confidence": float(box.conf[0]),
            "bbox_xyxy": [float(value) for value in box.xyxy[0].tolist()],
        })
    return detections


def build_recorded_replay_packet(
    *,
    sequence: int,
    timestamp_ns: int,
    frame_name: str,
    image_size: tuple[int, int],
    detections: list[dict],
    model_id: str,
) -> dict:
    return build_perception_packet(
        sequence,
        timestamp_ns,
        frame_name,
        image_size,
        detections,
        source="recorded-media-replay",
        model_id=model_id,
        timestamp_clock="recording-relative",
    )
