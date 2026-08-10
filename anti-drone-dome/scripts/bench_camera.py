"""Windows-first camera evidence bench; no Pi, NPU, or V4L2 dependency."""
from __future__ import annotations

import argparse
import json
import math
import queue
import random
import re
import statistics
import subprocess
import threading
import time
from pathlib import Path

from bench_common import NOT_MEASURED, OpenCVCaptureBackend, metadata, percentile, write_artifact

SCHEMA = "larp.camera-bench.v1"
# The YUY2 720p entry is intentionally 10 fps: that is the advertised mode
# exposed by this UVC device, not an assumed 30 fps setting.
REQUIRED_MODES = ((1920, 1080, "MJPG", 30.0), (1280, 720, "MJPG", 30.0), (1280, 720, "YUY2", 10.0), (640, 480, "YUY2", 30.0), (1280, 800, "MJPG", 30.0))
CONTROL_PROPERTIES = ("BRIGHTNESS", "CONTRAST", "SATURATION", "HUE", "GAIN", "EXPOSURE", "AUTO_EXPOSURE", "AUTO_WB", "WB_TEMPERATURE", "BACKLIGHT", "SHARPNESS", "GAMMA", "ZOOM", "FOCUS", "AUTOFOCUS")


def root_path() -> Path:
    return Path(__file__).resolve().parent.parent


def ffmpeg(command: list[str]) -> dict:
    try:
        run = subprocess.run(command, text=True, capture_output=True, timeout=30)
        return {"command": command, "returncode": run.returncode, "stdout": run.stdout, "stderr": run.stderr}
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"command": command, "result": NOT_MEASURED, "reason": str(exc)}


def dshow_enumeration(device: str) -> dict:
    # Both untouched stderr streams are evidence: ffmpeg sends DirectShow output there.
    return {"devices_raw": ffmpeg(["ffmpeg", "-hide_banner", "-list_devices", "true", "-f", "dshow", "-i", "dummy"]), "options_raw": ffmpeg(["ffmpeg", "-hide_banner", "-list_options", "true", "-f", "dshow", "-i", f"video={device}"])}


def pnp_nodes() -> object:
    command = "Get-PnpDevice -PresentOnly | Where-Object {$_.Class -in 'Camera','Image'} | Select-Object Status,Class,FriendlyName,InstanceId | ConvertTo-Json -Compress"
    try:
        result = subprocess.run(["powershell", "-NoProfile", "-Command", command], text=True, capture_output=True, timeout=20, check=True)
        return json.loads(result.stdout)
    except (OSError, subprocess.CalledProcessError, json.JSONDecodeError, subprocess.TimeoutExpired) as exc:
        return {"result": NOT_MEASURED, "reason": str(exc)}


def controls(device_index: int) -> list[dict]:
    """Report every portable OpenCV control. DirectShow does not expose ranges via ffmpeg.

    Explicitly preserving this limitation is preferable to inventing driver ranges.
    """
    import cv2
    capture = OpenCVCaptureBackend().open(device_index, 640, 480, "YUY2", 30.0)
    if not capture.isOpened():
        capture.release()
        raise RuntimeError(
            f"DirectShow index {device_index} did not open; do not infer camera controls from a dead handle"
        )
    found = []
    try:
        for name in CONTROL_PROPERTIES:
            prop = getattr(cv2, f"CAP_PROP_{name}", None)
            if prop is None:
                continue
            value = capture.get(prop) if capture.isOpened() else None
            found.append({"name": name, "opencv_property": prop, "current_value": value if value is not None and value >= 0 else NOT_MEASURED, "range": NOT_MEASURED, "step": NOT_MEASURED, "default": NOT_MEASURED, "discovery_limit": "OpenCV/DirectShow interface does not expose IAMCameraControl range/default metadata."})
    finally:
        capture.release()
    names = " ".join(item["name"].lower() for item in found)
    special = {}
    for key in ("ir-cut", "night mode", "backlight", "exposure mode", "auto exposure priority"):
        special[key] = "PRESENT" if key.replace(" ", "_") in names else "NOT MEASURED VIA OPENCV/DIRECTSHOW"
    return [{"controls": found, "special_controls": special}]


def enumerate_command(args) -> Path:
    config = {"operation": "enumeration", "device_name": args.device, "device_index": args.device_index, "backend": OpenCVCaptureBackend().name}
    try:
        control_data = controls(args.device_index)
    except RuntimeError as exc:
        control_data = [{"measurement_status": NOT_MEASURED, "reason": str(exc)}]
    record = {"schema": SCHEMA, **metadata(root_path(), config), "directshow": dshow_enumeration(args.device), "pnp_camera_nodes": pnp_nodes(), "controls": control_data, "index_verification": {"requested_index": args.device_index, "expected_mapping": "DirectShow device order is recorded in devices_raw; this host maps index 1 to the second listed camera, Innomaker.", "verification_status": "OPENED" if control_data and "controls" in control_data[0] else NOT_MEASURED}, "note": "Raw DirectShow output is stored unedited. Video-node mapping is reported from Windows PnP nodes; DirectShow does not expose Linux-style nodes."}
    path = write_artifact(root_path(), "camera", "enumeration", record)
    print(path)
    return path


def config_name(width: int, height: int, fmt: str) -> str:
    return f"{width}x{height}_{fmt.lower()}"


def measure_mode(device_index: int, spec: tuple[int, int, str, float], warmup: int, frames: int) -> dict:
    """Read frames from a DirectShow-configured ffmpeg pipe.

    OpenCV applies format properties after opening a DirectShow device on this
    host, which can silently leave it in the default YUY2/5 fps mode.  ffmpeg
    configures the pin before it opens, so the requested mode is auditable.
    """
    import psutil
    width, height, fourcc, fps = spec
    input_format = ["-vcodec", "mjpeg"] if fourcc == "MJPG" else ["-pixel_format", "yuyv422"]
    command = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-f", "dshow", "-video_size", f"{width}x{height}", "-framerate", str(fps), *input_format, "-i", "video=Innomaker-U20CAM-1080PD&N-S1", "-an", "-f", "rawvideo", "-pix_fmt", "gray", "pipe:1"]
    record = {"requested": {"width": width, "height": height, "pixel_format": fourcc, "advertised_fps": fps}, "backend": "ffmpeg-dshow", "backend_command": command}
    pipe = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    process = psutil.Process()
    psutil.cpu_percent(None); process.cpu_percent(None)
    try:
        frame_bytes = width * height
        def read_frame():
            chunks, remaining = [], frame_bytes
            while remaining:
                chunk = pipe.stdout.read(remaining)
                if not chunk:
                    return False
                chunks.append(chunk); remaining -= len(chunk)
            return True
        for _ in range(warmup):
            if not read_frame():
                break
        stamps, costs, sequence = [], [], []
        for number in range(frames):
            before = time.perf_counter_ns(); ok = read_frame(); after = time.perf_counter_ns()
            if not ok:
                continue
            stamps.append(after); costs.append((after - before) / 1e6); sequence.append(number)
        intervals = [(right - left) / 1e6 for left, right in zip(stamps, stamps[1:])]
        return {**record, "measurement_status": "MEASURED" if intervals else NOT_MEASURED, "actual": {"width": width, "height": height, "reported_fps": fps}, "frames": {"warmup_discarded": warmup, "requested": frames, "received": len(stamps), "dropped_or_duplicated": NOT_MEASURED, "backend_limit": "DirectShow/ffmpeg exposes neither device sequence nor drop counter."}, "achieved_mean_fps": 1000.0 / statistics.mean(intervals) if intervals else NOT_MEASURED, "frame_interval_ms": {"p50": percentile(intervals, .5), "p95": percentile(intervals, .95), "p99": percentile(intervals, .99), "min": min(intervals) if intervals else NOT_MEASURED, "max": max(intervals) if intervals else NOT_MEASURED}, "cpu_utilization_percent": {"python_process": process.cpu_percent(None), "system": psutil.cpu_percent(None)}, "read_call_cost_ms": {"p50": percentile(costs, .5), "p95": percentile(costs, .95), "p99": percentile(costs, .99), "scope": "combined device capture, pipe transfer, and MJPEG decode when applicable; separation NOT MEASURED"}}
    finally:
        pipe.terminate()
        try: pipe.wait(timeout=5)
        except subprocess.TimeoutExpired: pipe.kill()


def sweep_command(args) -> list[Path]:
    specs = list(REQUIRED_MODES)
    if args.only:
        specs = [spec for spec in specs if config_name(*spec[:3]) == args.only]
    paths = []
    for spec in specs:
        config = {"operation": "throughput_sweep", "device_name": args.device, "device_index": args.device_index, "requested_mode": spec, "warmup_frames": args.warmup, "measurement_frames": args.frames}
        record = {"schema": SCHEMA, **metadata(root_path(), config), "mode": measure_mode(args.device_index, spec, args.warmup, args.frames)}
        paths.append(write_artifact(root_path(), "camera", f"throughput_{config_name(*spec[:3])}", record))
    print("\n".join(map(str, paths)))
    return paths


def latency_command(args) -> Path:
    import cv2
    spec = (args.width, args.height, args.format, args.fps)
    capture = OpenCVCaptureBackend().open(args.device_index, *spec)
    if not capture.isOpened():
        raise RuntimeError("camera could not open requested latency mode")
    print("Point the camera at this display so the central ROI sees the fullscreen field; focus it, then press Enter.")
    cv2.namedWindow("LARP latency stimulus", cv2.WINDOW_NORMAL); cv2.setWindowProperty("LARP latency stimulus", cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)
    cv2.imshow("LARP latency stimulus", __import__("numpy").full((300, 500, 3), 127, dtype="uint8")); cv2.waitKey(1); input()
    samples = []
    try:
        for _ in range(args.trials):
            cv2.imshow("LARP latency stimulus", __import__("numpy").zeros((300, 500, 3), dtype="uint8")); cv2.waitKey(1); time.sleep(random.uniform(.12, .35))
            white = __import__("numpy").full((300, 500, 3), 255, dtype="uint8")
            emitted = time.perf_counter_ns(); cv2.imshow("LARP latency stimulus", white); cv2.waitKey(1)
            deadline = emitted + int(args.timeout_s * 1e9)
            while time.perf_counter_ns() < deadline:
                ok, frame = capture.read()
                if not ok: continue
                h, w = frame.shape[:2]; roi = frame[h//3:2*h//3, w//3:2*w//3]
                if float(cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY).mean()) >= args.threshold:
                    samples.append((time.perf_counter_ns() - emitted) / 1e6); break
    finally:
        capture.release(); cv2.destroyAllWindows()
    config = {"operation": "glass_to_glass_luminance_flash", "device_index": args.device_index, "mode": spec, "trials": args.trials, "roi": "central third", "threshold": args.threshold}
    record = {"schema": SCHEMA, **metadata(root_path(), config), "measurement_status": "MEASURED" if samples else NOT_MEASURED, "samples_ms": samples, "statistics_ms": {"p50": percentile(samples,.5), "p95": percentile(samples,.95), "p99": percentile(samples,.99), "min": min(samples) if samples else NOT_MEASURED, "max": max(samples) if samples else NOT_MEASURED, "standard_deviation": statistics.stdev(samples) if len(samples)>1 else NOT_MEASURED}, "known_additive_bias": "Display refresh interval is not separable and has not been subtracted.", "successful_trials": len(samples)}
    path = write_artifact(root_path(), "camera", f"latency_{config_name(*spec[:3])}", record); print(path); return path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__); subs = parser.add_subparsers(required=True, dest="command")
    def device_args(p): p.add_argument("--device", default="Innomaker-U20CAM-1080PD&N-S1"); p.add_argument("--device-index", type=int, default=1)
    enum = subs.add_parser("enumerate"); device_args(enum); enum.set_defaults(func=enumerate_command)
    sweep = subs.add_parser("sweep"); device_args(sweep); sweep.add_argument("--warmup", type=int, default=60); sweep.add_argument("--frames", type=int, default=600); sweep.add_argument("--only", choices=[config_name(*spec[:3]) for spec in REQUIRED_MODES]); sweep.set_defaults(func=sweep_command)
    lat = subs.add_parser("latency"); device_args(lat); lat.add_argument("--width",type=int,default=1920); lat.add_argument("--height",type=int,default=1080); lat.add_argument("--format",default="MJPG"); lat.add_argument("--fps",type=float,default=30); lat.add_argument("--trials",type=int,default=50); lat.add_argument("--threshold",type=float,default=180); lat.add_argument("--timeout-s",type=float,default=2); lat.set_defaults(func=latency_command)
    args = parser.parse_args()
    if getattr(args, "frames", 600) < 600: parser.error("--frames must be at least 600")
    args.func(args); return 0

if __name__ == "__main__": raise SystemExit(main())
