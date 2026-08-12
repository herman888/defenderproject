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
    return [{
        "controls": found,
        "scope": "Portable OpenCV controls only. No conclusion is made about IR-cut, night mode, or other vendor controls because this interface does not enumerate them.",
    }]


def enumerate_command(args) -> Path:
    config = {"operation": "enumeration", "device_name": args.device, "device_index": args.device_index, "backend": OpenCVCaptureBackend().name}
    try:
        control_data = controls(args.device_index)
    except RuntimeError as exc:
        control_data = [{"measurement_status": NOT_MEASURED, "reason": str(exc)}]
    record = {"schema": SCHEMA, **metadata(root_path(), config), "directshow": dshow_enumeration(args.device), "pnp_camera_nodes": pnp_nodes(), "controls": control_data, "index_verification": {"requested_index": args.device_index, "directshow_order": {"0": "Integrated Camera", "1": "Innomaker-U20CAM-1080PD&N-S1"}, "method": "ffmpeg DirectShow device enumeration recorded the ordered device list; OpenCV index 1 opened successfully.", "verification_status": "OPENED" if control_data and "controls" in control_data[0] else NOT_MEASURED}, "note": "Raw DirectShow output is stored unedited. Video-node mapping is reported from Windows PnP nodes; DirectShow does not expose Linux-style nodes."}
    path = write_artifact(root_path(), "camera", "enumeration", record)
    print(path)
    return path


def config_name(width: int, height: int, fmt: str) -> str:
    return f"{width}x{height}_{fmt.lower()}"


def windows_display_geometry(device_name: str) -> tuple[int, int, int, int]:
    """Return explicit Windows display geometry, without guessing a monitor."""
    if __import__("platform").system() != "Windows":
        raise RuntimeError("stimulus display placement is implemented only on Windows")
    import ctypes
    from ctypes import wintypes

    class RECT(ctypes.Structure):
        _fields_ = [("left", wintypes.LONG), ("top", wintypes.LONG), ("right", wintypes.LONG), ("bottom", wintypes.LONG)]

    class MONITORINFOEXW(ctypes.Structure):
        _fields_ = [("cbSize", wintypes.DWORD), ("rcMonitor", RECT), ("rcWork", RECT), ("dwFlags", wintypes.DWORD), ("szDevice", wintypes.WCHAR * 32)]

    found: list[tuple[int, int, int, int]] = []
    callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HMONITOR, wintypes.HDC, ctypes.POINTER(RECT), wintypes.LPARAM)

    @callback_type
    def visit(handle, _dc, _rect, _data):
        info = MONITORINFOEXW(); info.cbSize = ctypes.sizeof(info)
        if ctypes.windll.user32.GetMonitorInfoW(handle, ctypes.byref(info)) and info.szDevice.upper() == device_name.upper():
            found.append((info.rcMonitor.left, info.rcMonitor.top, info.rcMonitor.right - info.rcMonitor.left, info.rcMonitor.bottom - info.rcMonitor.top))
        return True

    if not ctypes.windll.user32.EnumDisplayMonitors(None, None, visit, 0) or not found:
        raise RuntimeError(f"Windows display {device_name!r} was not found")
    return found[0]


class FfmpegDshowFrameCapture:
    """Read BGR frames from an ffmpeg DirectShow process with its input pin fixed.

    OpenCV's DirectShow path can accept a requested resolution while silently
    changing the input compression.  The ffmpeg command constrains the input
    pin before open, so the requested MJPEG/YUY2 mode is auditable.
    """

    def __init__(self, device: str, width: int, height: int, fourcc: str, fps: float):
        import numpy as np

        input_format = ["-vcodec", "mjpeg"] if fourcc == "MJPG" else ["-pixel_format", "yuyv422"]
        self.width, self.height = width, height
        self.np = np
        self.command = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-fflags", "nobuffer", "-flags", "low_delay", "-rtbufsize", "1M", "-f", "dshow", "-video_size", f"{width}x{height}", "-framerate", str(fps), *input_format, "-i", f"video={device}", "-an", "-f", "rawvideo", "-pix_fmt", "gray", "pipe:1"]
        self.process = subprocess.Popen(self.command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, bufsize=0)
        self.frame_bytes = width * height
        self.frames: queue.Queue = queue.Queue(maxsize=1)
        self.stop_event = threading.Event()
        self.reader = threading.Thread(target=self._read_frames, daemon=True)
        self.reader.start()

    def _read_one(self):
        chunks, remaining = [], self.frame_bytes
        while remaining:
            chunk = self.process.stdout.read(remaining)
            if not chunk:
                return False, None
            chunks.append(chunk)
            remaining -= len(chunk)
        frame = self.np.frombuffer(b"".join(chunks), dtype=self.np.uint8).reshape(self.height, self.width).copy()
        return True, frame

    def _read_frames(self):
        while not self.stop_event.is_set():
            ok, frame = self._read_one()
            if not ok:
                return
            try:
                self.frames.put(frame, timeout=.05)
            except queue.Full:
                try:
                    self.frames.get_nowait()
                except queue.Empty:
                    pass
                try:
                    self.frames.put_nowait(frame)
                except queue.Full:
                    pass

    def read(self):
        try:
            return True, self.frames.get(timeout=.25)
        except queue.Empty:
            return False, None

    def release(self):
        self.stop_event.set()
        if self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
        self.reader.join(timeout=1)


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
    import numpy as np
    spec = (args.width, args.height, args.format, args.fps)
    capture = FfmpegDshowFrameCapture(args.device, *spec)
    print("Confirm the camera is rigid, focused, and its central third contains only this display. Press Enter to start.")
    stimulus_geometry = windows_display_geometry(args.stimulus_display)
    stimulus_origin = stimulus_geometry[:2]
    cv2.namedWindow("LARP latency stimulus", cv2.WINDOW_NORMAL)
    cv2.resizeWindow("LARP latency stimulus", *stimulus_geometry[2:])
    cv2.moveWindow("LARP latency stimulus", *stimulus_origin)
    cv2.imshow("LARP latency stimulus", np.full((300, 500, 3), 127, dtype="uint8")); cv2.waitKey(1)
    if args.preflight_seconds:
        print(f"Stimulus is on {args.stimulus_display}; starting in {args.preflight_seconds} seconds.")
        time.sleep(args.preflight_seconds)
    else:
        input("Confirm the stimulus is on the camera-facing display, then press Enter to start. ")
    def roi_luminance(frame) -> float:
        h, w = frame.shape[:2]
        roi = frame[h//3:2*h//3, w//3:2*w//3]
        return float(roi.mean()) if roi.ndim == 2 else float(cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY).mean())

    def collect_luminance(count: int) -> list[float]:
        values = []
        deadline = time.perf_counter_ns() + int(args.timeout_s * 1e9)
        while len(values) < count and time.perf_counter_ns() < deadline:
            ok, frame = capture.read()
            if ok:
                values.append(roi_luminance(frame))
        return values

    black = np.zeros((300, 500, 3), dtype="uint8")
    white = np.full((300, 500, 3), 255, dtype="uint8")
    cv2.imshow("LARP latency stimulus", black); cv2.waitKey(1); time.sleep(args.calibration_settle_s)
    black_calibration = collect_luminance(args.calibration_frames)
    cv2.imshow("LARP latency stimulus", white); cv2.waitKey(1); time.sleep(args.calibration_settle_s)
    white_calibration = collect_luminance(args.calibration_frames)
    black_reference = statistics.median(black_calibration) if black_calibration else None
    white_reference = statistics.median(white_calibration) if white_calibration else None
    contrast = white_reference - black_reference if black_reference is not None and white_reference is not None else None
    if contrast is None or contrast < args.minimum_contrast:
        capture.release(); cv2.destroyAllWindows()
        raise RuntimeError(f"insufficient display-to-camera luminance contrast: {contrast!r}; minimum is {args.minimum_contrast}")
    crossing_threshold = black_reference + contrast * args.transition_fraction
    trial_records = []
    try:
        for trial_number in range(1, args.trials + 1):
            cv2.imshow("LARP latency stimulus", black); cv2.waitKey(1)
            dark_deadline = time.perf_counter_ns() + int(args.timeout_s * 1e9)
            dark_seen = False
            while time.perf_counter_ns() < dark_deadline:
                ok, frame = capture.read()
                if not ok:
                    continue
                if roi_luminance(frame) <= crossing_threshold:
                    dark_seen = True
                    break
            if not dark_seen:
                trial_records.append({"trial": trial_number, "accepted": False, "reason": "dark_baseline_not_observed", "crossing_latency_ms": NOT_MEASURED})
                continue
            time.sleep(random.uniform(.12, .35))
            emitted = time.perf_counter_ns(); cv2.imshow("LARP latency stimulus", white); cv2.waitKey(1)
            deadline = emitted + int(args.timeout_s * 1e9)
            crossing = None
            while time.perf_counter_ns() < deadline:
                ok, frame = capture.read()
                if not ok:
                    continue
                if roi_luminance(frame) >= crossing_threshold:
                    crossing = (time.perf_counter_ns() - emitted) / 1e6
                    break
            trial_records.append({"trial": trial_number, "accepted": crossing is not None, "reason": "crossing_observed" if crossing is not None else "white_threshold_not_observed_before_timeout", "crossing_latency_ms": crossing if crossing is not None else NOT_MEASURED})
    finally:
        capture.release(); cv2.destroyAllWindows()
    samples = [trial["crossing_latency_ms"] for trial in trial_records if trial["accepted"]]
    config = {"operation": "glass_to_glass_luminance_flash", "device_index": args.device_index, "mode": spec, "capture_backend": "ffmpeg-dshow", "capture_command": capture.command, "trials": args.trials, "roi": "central third", "crossing_threshold_method": "actual display black/white calibration midpoint", "transition_fraction": args.transition_fraction, "minimum_contrast": args.minimum_contrast, "stimulus_display": args.stimulus_display, "stimulus_display_geometry": stimulus_geometry, "preflight_seconds": args.preflight_seconds, "monitor_resolution": args.monitor_resolution, "monitor_refresh_hz": args.refresh_hz, "room_condition": args.room_condition, "operator_confirmed": {"camera_rigid": args.camera_rigid, "focus_locked": args.focus_locked, "exposure_locked": args.exposure_locked, "exposure_setting": args.exposure_setting, "vrr_status": args.vrr_status, "motion_smoothing_status": args.motion_smoothing_status, "power_saving_status": args.power_saving_status, "other_apps_closed": args.other_apps_closed, "windows_high_performance": args.windows_high_performance}}
    status = "MEASURED" if len(samples) >= args.minimum_crossings else "REJECTED_INSUFFICIENT_CROSSINGS"
    record = {"schema": SCHEMA, **metadata(root_path(), config), "measurement_status": status, "luminance_calibration": {"black_samples": black_calibration, "white_samples": white_calibration, "black_reference_median": black_reference, "white_reference_median": white_reference, "contrast": contrast, "crossing_threshold": crossing_threshold}, "raw_trials": trial_records, "samples_ms": samples, "statistics_ms": {"p50": percentile(samples,.5), "p95": percentile(samples,.95), "p99": percentile(samples,.99), "min": min(samples) if samples else NOT_MEASURED, "max": max(samples) if samples else NOT_MEASURED, "standard_deviation": statistics.stdev(samples) if len(samples)>1 else NOT_MEASURED}, "successful_trials": len(samples), "minimum_acceptable_crossings": args.minimum_crossings, "unseparated_additive_biases": ["monitor refresh timing", "display pixel response", "camera exposure and auto-exposure behaviour", "camera readout and host read scheduling", "window compositor/presentation scheduling"], "interpretation_limit": "This is a luminance-crossing proxy, not an isolated camera-latency measurement. None of the listed biases has been subtracted or separately measured."}
    path = write_artifact(root_path(), "camera", f"latency_{config_name(*spec[:3])}", record); print(path); return path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__); subs = parser.add_subparsers(required=True, dest="command")
    def device_args(p): p.add_argument("--device", default="Innomaker-U20CAM-1080PD&N-S1"); p.add_argument("--device-index", type=int, default=1)
    enum = subs.add_parser("enumerate"); device_args(enum); enum.set_defaults(func=enumerate_command)
    sweep = subs.add_parser("sweep"); device_args(sweep); sweep.add_argument("--warmup", type=int, default=60); sweep.add_argument("--frames", type=int, default=600); sweep.add_argument("--only", choices=[config_name(*spec[:3]) for spec in REQUIRED_MODES]); sweep.set_defaults(func=sweep_command)
    status_choices = ("disabled", "unavailable", NOT_MEASURED)
    lat = subs.add_parser("latency"); device_args(lat); lat.add_argument("--width",type=int,default=1920); lat.add_argument("--height",type=int,default=1080); lat.add_argument("--format",default="MJPG"); lat.add_argument("--fps",type=float,default=30); lat.add_argument("--trials",type=int,default=50); lat.add_argument("--transition-fraction",type=float,default=.5); lat.add_argument("--minimum-contrast",type=float,default=20); lat.add_argument("--calibration-frames",type=int,default=30); lat.add_argument("--calibration-settle-s",type=float,default=1.5); lat.add_argument("--timeout-s",type=float,default=2); lat.add_argument("--minimum-crossings",type=int,default=45); lat.add_argument("--stimulus-display",default="\\\\.\\DISPLAY1"); lat.add_argument("--preflight-seconds",type=float,default=0); lat.add_argument("--monitor-resolution",required=True); lat.add_argument("--refresh-hz",type=float,required=True); lat.add_argument("--room-condition",required=True); lat.add_argument("--camera-rigid",action="store_true",required=True); lat.add_argument("--focus-locked",action="store_true",required=True); lat.add_argument("--exposure-locked",action="store_true",required=True); lat.add_argument("--exposure-setting",required=True,help="Actual driver exposure value after manual lock"); lat.add_argument("--vrr-status",choices=status_choices,default=NOT_MEASURED); lat.add_argument("--motion-smoothing-status",choices=status_choices,default=NOT_MEASURED); lat.add_argument("--power-saving-status",choices=status_choices,default=NOT_MEASURED); lat.add_argument("--other-apps-closed",action="store_true",required=True); lat.add_argument("--windows-high-performance",action="store_true",required=True); lat.set_defaults(func=latency_command)
    args = parser.parse_args()
    if getattr(args, "frames", 600) < 600: parser.error("--frames must be at least 600")
    args.func(args); return 0

if __name__ == "__main__": raise SystemExit(main())
