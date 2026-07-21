"""Validated detector manifests and inference-device selection."""

from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import dataclass


SCHEMA = "aegis.vision-model.v1"
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_DEVICES = {"auto", "cpu", "cuda"}
_QUANTIZATION = {"none", "fp16", "int8"}


def _sha256(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_vision_model_manifest(data: dict) -> None:
    if data.get("schema") != SCHEMA:
        raise ValueError(f"vision model schema must be {SCHEMA}")
    for key in ("model_id", "task", "artifact", "input", "classes", "inference"):
        if key not in data:
            raise ValueError(f"vision model manifest missing {key}")
    if not isinstance(data["model_id"], str) or not data["model_id"]:
        raise ValueError("model_id must be a non-empty string")
    if data["task"] != "object-detection":
        raise ValueError("only object-detection manifests are supported")

    artifact = data["artifact"]
    if not isinstance(artifact, dict):
        raise ValueError("artifact must be an object")
    for key in ("path", "format"):
        if not isinstance(artifact.get(key), str) or not artifact[key]:
            raise ValueError(f"artifact.{key} must be a non-empty string")
    sha256 = artifact.get("sha256")
    if sha256 is not None and (
        not isinstance(sha256, str) or not _SHA256.fullmatch(sha256)
    ):
        raise ValueError("artifact.sha256 must be null or 64 lowercase hex characters")
    size_bytes = artifact.get("size_bytes")
    if size_bytes is not None and (
        not isinstance(size_bytes, int) or isinstance(size_bytes, bool)
        or size_bytes <= 0
    ):
        raise ValueError("artifact.size_bytes must be null or a positive integer")

    model_input = data["input"]
    if not isinstance(model_input, dict):
        raise ValueError("input must be an object")
    for key in ("width", "height"):
        value = model_input.get(key)
        if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
            raise ValueError(f"input.{key} must be a positive integer")
    if model_input.get("color_space") not in {"RGB", "BGR"}:
        raise ValueError("input.color_space must be RGB or BGR")

    classes = data["classes"]
    if not isinstance(classes, list) or not classes:
        raise ValueError("classes must be a non-empty list")
    class_ids = set()
    labels = set()
    for item in classes:
        if not isinstance(item, dict):
            raise ValueError("each class must be an object")
        class_id = item.get("id")
        label = item.get("label")
        if not isinstance(class_id, int) or isinstance(class_id, bool) or class_id < 0:
            raise ValueError("class id must be a non-negative integer")
        if not isinstance(label, str) or not label:
            raise ValueError("class label must be a non-empty string")
        if class_id in class_ids or label in labels:
            raise ValueError("class ids and labels must be unique")
        class_ids.add(class_id)
        labels.add(label)

    inference = data["inference"]
    if not isinstance(inference, dict):
        raise ValueError("inference must be an object")
    if inference.get("backend") != "ultralytics":
        raise ValueError("only the ultralytics inference backend is supported")
    if inference.get("device") not in _DEVICES:
        raise ValueError("inference.device must be auto, cpu, or cuda")
    if inference.get("quantization") not in _QUANTIZATION:
        raise ValueError("inference.quantization must be none, fp16, or int8")
    for key in ("confidence_threshold", "iou_threshold"):
        value = inference.get(key)
        if (
            not isinstance(value, (int, float))
            or isinstance(value, bool)
            or not 0.0 <= float(value) <= 1.0
        ):
            raise ValueError(f"inference.{key} must be in [0, 1]")


@dataclass(frozen=True)
class VisionModelManifest:
    path: str
    data: dict

    @property
    def model_id(self) -> str:
        return self.data["model_id"]

    @property
    def artifact_path(self) -> str:
        return os.path.abspath(os.path.join(
            os.path.dirname(self.path), self.data["artifact"]["path"]
        ))

    @property
    def locked_model_id(self) -> str:
        digest = self.data["artifact"].get("sha256")
        if not digest:
            raise ValueError("model artifact is not checksum-locked")
        return f"{self.model_id}@sha256:{digest[:12]}"

    def verify_artifact(self) -> None:
        artifact = self.data["artifact"]
        expected_hash = artifact.get("sha256")
        if not expected_hash:
            raise ValueError("model artifact is not checksum-locked")
        if not os.path.isfile(self.artifact_path):
            raise FileNotFoundError(
                f"model artifact does not exist: {self.artifact_path}"
            )
        expected_size = artifact.get("size_bytes")
        actual_size = os.path.getsize(self.artifact_path)
        if expected_size is not None and actual_size != expected_size:
            raise ValueError(
                f"model artifact size mismatch: expected {expected_size}, "
                f"found {actual_size}"
            )
        actual_hash = _sha256(self.artifact_path)
        if actual_hash != expected_hash:
            raise ValueError(
                f"model artifact checksum mismatch: expected {expected_hash}, "
                f"found {actual_hash}"
            )


def load_vision_model_manifest(
    path: str, *, require_artifact: bool = False
) -> VisionModelManifest:
    absolute_path = os.path.abspath(path)
    with open(absolute_path, encoding="utf-8") as handle:
        data = json.load(handle)
    validate_vision_model_manifest(data)
    manifest = VisionModelManifest(path=absolute_path, data=data)
    if require_artifact:
        manifest.verify_artifact()
    return manifest


def lock_vision_model_artifact(manifest_path: str, artifact_path: str) -> dict:
    manifest_path = os.path.abspath(manifest_path)
    artifact_path = os.path.abspath(artifact_path)
    if not os.path.isfile(artifact_path):
        raise FileNotFoundError(f"model artifact does not exist: {artifact_path}")
    with open(manifest_path, encoding="utf-8") as handle:
        data = json.load(handle)
    validate_vision_model_manifest(data)
    data["artifact"]["path"] = os.path.relpath(
        artifact_path, os.path.dirname(manifest_path)
    ).replace("\\", "/")
    data["artifact"]["size_bytes"] = os.path.getsize(artifact_path)
    data["artifact"]["sha256"] = _sha256(artifact_path)
    validate_vision_model_manifest(data)
    temporary_path = manifest_path + ".tmp"
    with open(temporary_path, "w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2)
        handle.write("\n")
    os.replace(temporary_path, manifest_path)
    return data


def resolve_inference_device(requested: str):
    if requested not in _DEVICES:
        raise ValueError("inference device must be auto, cpu, or cuda")
    if requested == "cpu":
        return "cpu"
    try:
        import torch
    except ImportError as exc:
        if requested == "cuda":
            raise RuntimeError(
                "CUDA inference requires a CUDA-enabled PyTorch installation"
            ) from exc
        return "cpu"
    if torch.cuda.is_available():
        return 0
    if requested == "cuda":
        raise RuntimeError(
            "CUDA was requested, but this PyTorch runtime cannot access CUDA"
        )
    return "cpu"
