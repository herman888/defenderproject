"""Measure UVC capture behaviour without an inference/NPU dependency.

Results are host-and-camera specific.  A configuration that cannot be opened is
recorded as NOT MEASURED rather than substituted with an assumed value.
"""

from __future__ import annotations

import argparse
import json
import platform
import statistics
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

from measure_pipeline import NOT_MEASURED, git_commit


SCHEMA = "larp.camera-measurement.v1"
CONFIGURATIONS = (
    (1920, 1080, "MJPG", "1080p_mjpeg"),
    (1280, 720, "MJPG", "720p_mjpeg"),
    (1280, 720, "YUY2", "720p_yuy2"),
    (640, 480, "YUY2", "480p_yuy2"),
)


def percentile(values: list[float], fraction: float) -> float | str:
    if not values:
        return NOT_MEASURED
    ordered = sorted(values)
    index = min(len(ordered) - 1, round((len(ordered) - 1) * fraction))
    return ordered[index]


def enumerate_device(device: str) -> dict:
    """Capture platform-native enumeration output when the tool is available."""
    commands = []
    if platform.system() == "Linux":
        commands = [["v4l2-ctl", "--device", device, "--all"], ["v4l2-ctl", "--device", device, "--list-formats-ext"]]
    elif platform.system() == "Windows":
        commands = [["ffmpeg", "-hide_banner", "-list_options", "true", "-f", "dshow", "-i", f"video={device}"]]
    outputs = []
    for command in commands:
        try:
            result = subprocess.run(command, text=True, capture_output=True, timeout=15)
            outputs.append({"command": command, "returncode": result.returncode, "stdout": result.stdout, "stderr": result.stderr})
        except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
            outputs.append({"command": command, "result": NOT_MEASURED, "reason": str(exc)})
    return {"requested_device": device, "platform": platform.platform(), "enumeration": outputs or NOT_MEASURED}


def measure_config(cv2, device: int, config: tuple[int, int, str, str], frames: int) -> dict:
    width, height, fourcc, name = config
    capture = cv2.VideoCapture(device, cv2.CAP_DSHOW if platform.system() == "Windows" else cv2.CAP_ANY)
    record = {"name": name, "requested": {"width": width, "height": height, "pixel_format": fourcc}, "result": NOT_MEASURED}
    if not capture.isOpened():
        record["reason"] = "OpenCV could not open this device/configuration"
        return record
    try:
        capture.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*fourcc))
        capture.set(cv2.CAP_PROP_FRAME_WIDTH, width)
        capture.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
        advertised_fps = float(capture.get(cv2.CAP_PROP_FPS) or 0.0)
        intervals, decode_costs = [], []
        previous = None
        for _ in range(frames):
            started = time.perf_counter_ns()
            ok, frame = capture.read()
            ended = time.perf_counter_ns()
            if not ok or frame is None:
                continue
            if previous is not None:
                intervals.append((ended - previous) / 1_000_000)
            previous = ended
            decode_costs.append((ended - started) / 1_000_000)
        achieved_fps = 1000.0 / statistics.mean(intervals) if intervals else NOT_MEASURED
        record.update({
            "result": "MEASURED" if intervals else NOT_MEASURED,
            "actual": {"width": int(capture.get(cv2.CAP_PROP_FRAME_WIDTH)), "height": int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT)), "advertised_fps": advertised_fps},
            "achieved_fps": achieved_fps,
            "frame_interval_ms": {"p50": percentile(intervals, .50), "p95": percentile(intervals, .95), "p99": percentile(intervals, .99)},
            "capture_to_userspace_latency_ms": NOT_MEASURED,
            "cpu_utilization_percent": NOT_MEASURED,
            "decode_cost_ms": {"p50": percentile(decode_costs, .50), "p95": percentile(decode_costs, .95), "p99": percentile(decode_costs, .99)},
        })
        return record
    finally:
        capture.release()


def build_record(root: Path, device_name: str, device_index: int, frames: int) -> dict:
    return {"schema": SCHEMA, "created_utc": datetime.now(timezone.utc).isoformat(), "git_commit": git_commit(root), "host": {"platform": platform.platform(), "node": platform.node()}, "device": enumerate_device(device_name), "device_index": device_index, "frames_requested": frames, "configurations": []}


def summary_table(record: dict) -> str:
    rows = ["| Configuration | FPS | interval p50/p95/p99 ms | capture latency | CPU | decode p50/p95/p99 ms |", "| --- | --- | --- | --- | --- | --- |"]
    for item in record["configurations"]:
        interval = item.get("frame_interval_ms", {})
        decode = item.get("decode_cost_ms", {})
        rows.append(f"| {item['name']} | {item.get('achieved_fps', NOT_MEASURED)} | {interval.get('p50', NOT_MEASURED)} / {interval.get('p95', NOT_MEASURED)} / {interval.get('p99', NOT_MEASURED)} | {item.get('capture_to_userspace_latency_ms', NOT_MEASURED)} | {item.get('cpu_utilization_percent', NOT_MEASURED)} | {decode.get('p50', NOT_MEASURED)} / {decode.get('p95', NOT_MEASURED)} / {decode.get('p99', NOT_MEASURED)} |")
    return "\n".join(rows)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--device", default="InnoMaker U20CAM")
    parser.add_argument("--device-index", type=int, default=1)
    parser.add_argument("--frames", type=int, default=300)
    parser.add_argument("--output", default="reports/camera_measurement.json")
    args = parser.parse_args()
    if args.frames < 2:
        parser.error("--frames must be at least 2")
    root = Path(__file__).resolve().parent.parent
    record = build_record(root, args.device, args.device_index, args.frames)
    try:
        import cv2
    except ImportError:
        record["camera_runtime"] = NOT_MEASURED
        record["reason"] = "OpenCV is not installed"
    else:
        record["camera_runtime"] = cv2.__version__
        record["configurations"] = [measure_config(cv2, args.device_index, config, args.frames) for config in CONFIGURATIONS]
    output = Path(args.output)
    if not output.is_absolute():
        output = root / output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    print(summary_table(record))
    print(f"\nWrote {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
