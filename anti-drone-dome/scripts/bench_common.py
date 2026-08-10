"""Shared, portable evidence helpers for the Windows/Pi camera bench.

Only this module knows about host capture selection.  Measurement logic accepts a
backend object, allowing a Linux backend to be added without changing metrics.
"""
from __future__ import annotations

import json
import platform
import socket
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

NOT_MEASURED = "NOT MEASURED"
SCHEMA_VERSION = 1


def utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def git_commit(root: Path) -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
    except (OSError, subprocess.CalledProcessError):
        return "NOT AVAILABLE"


def package_versions(names: tuple[str, ...]) -> dict[str, str]:
    from importlib.metadata import PackageNotFoundError, version
    resolved = {}
    for name in names:
        try:
            resolved[name] = version(name)
        except PackageNotFoundError:
            resolved[name] = "NOT INSTALLED"
    return resolved


def metadata(root: Path, configuration: dict) -> dict:
    return {
        "schema_version": SCHEMA_VERSION,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "git_commit": git_commit(root),
        "host": {"hostname": socket.gethostname(), "os": platform.platform(), "python": sys.version},
        "resolved_packages": package_versions(("opencv-python", "psutil", "pyserial", "ultralytics", "torch")),
        "configuration": configuration,
    }


def write_artifact(root: Path, family: str, stem: str, data: dict) -> Path:
    directory = root / "artifacts" / family
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{stem}_{utc_stamp()}.json"
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def percentile(values: list[float], fraction: float):
    if not values:
        return NOT_MEASURED
    ordered = sorted(values)
    return ordered[round((len(ordered) - 1) * fraction)]


class CaptureBackend:
    """Small backend boundary used by all capture measurements."""
    name = "abstract"

    def open(self, device_index: int, width: int, height: int, fourcc: str, fps: float):
        raise NotImplementedError


class OpenCVCaptureBackend(CaptureBackend):
    """OpenCV capture implementation; DirectShow is isolated to this boundary."""
    name = "opencv-dshow" if platform.system() == "Windows" else "opencv"

    def open(self, device_index: int, width: int, height: int, fourcc: str, fps: float):
        import cv2
        api = cv2.CAP_DSHOW if platform.system() == "Windows" else cv2.CAP_ANY
        capture = cv2.VideoCapture(device_index, api)
        if not capture.isOpened():
            return capture
        capture.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*fourcc))
        capture.set(cv2.CAP_PROP_FRAME_WIDTH, width)
        capture.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
        capture.set(cv2.CAP_PROP_FPS, fps)
        return capture
