#!/usr/bin/env python3
"""Live USB camera preview (InnoMaker / any UVC cam). Press Q or Esc to quit."""

from __future__ import annotations

import argparse
import platform
import re
import subprocess
import sys
import time
from dataclasses import dataclass


@dataclass(frozen=True)
class CameraInfo:
    index: int
    width: int
    height: int
    name: str = ""

    @property
    def pixels(self) -> int:
        return self.width * self.height

    @property
    def label(self) -> str:
        tag = self.name or f"index {self.index}"
        kind = "USB / external" if _looks_external(self) else "built-in"
        return f"{self.index}: {tag} ({self.width}x{self.height}, {kind})"


def _looks_external(info: CameraInfo) -> bool:
    name = info.name.lower()
    if any(k in name for k in ("facetime", "iphone", "continuity", "built-in", "isight")):
        return False
    if any(k in name for k in ("innomaker", "usb", "uvc", "webcam", "logitech", "elgato")):
        return True
    return info.index != 0


def _is_innomaker(name: str) -> bool:
    return "innomaker" in name.lower()


def _is_blocked_camera(name: str) -> bool:
    """Built-in, iPhone Continuity, Desk View, wireless — never use these."""
    n = name.lower()
    blocked = (
        "facetime", "iphone", "continuity", "isight", "built-in",
        "desk view", "wireless", "camo", "ndi", "epoccam", "ivcam",
    )
    return any(k in n for k in blocked)


def _is_builtin_name(name: str) -> bool:
    return _is_blocked_camera(name)


def _device_name(index: int) -> str:
    for idx, name in _avfoundation_video_devices():
        if idx == index:
            return name
    names = _mac_camera_names()
    return names[index] if index < len(names) else f"index {index}"


def _mac_camera_names() -> list[str]:
    if platform.system() != "Darwin":
        return []
    try:
        out = subprocess.check_output(
            ["system_profiler", "SPCameraDataType"],
            text=True,
            stderr=subprocess.DEVNULL,
            timeout=8,
        )
    except (OSError, subprocess.SubprocessError):
        return []
    names: list[str] = []
    for line in out.splitlines():
        m = re.match(r"^\s{4}([^:]+):\s*$", line)
        if m:
            names.append(m.group(1).strip())
    return names


def _avfoundation_video_devices() -> list[tuple[int, str]]:
    """OpenCV/AVFoundation camera index → device name (via ffmpeg list)."""
    try:
        proc = subprocess.run(
            ["ffmpeg", "-f", "avfoundation", "-list_devices", "true", "-i", ""],
            capture_output=True,
            text=True,
            timeout=12,
        )
        out = proc.stderr + proc.stdout
    except (OSError, subprocess.SubprocessError):
        return []

    devices: list[tuple[int, str]] = []
    in_video = False
    for line in out.splitlines():
        if "AVFoundation video devices" in line:
            in_video = True
            continue
        if in_video and "AVFoundation audio devices" in line:
            break
        m = re.search(r"\[(\d+)\]\s*(.+)", line)
        if in_video and m and "Capture screen" not in m.group(2):
            devices.append((int(m.group(1)), m.group(2).strip()))
    return devices


def innomaker_index() -> int | None:
    """OpenCV index for InnoMaker (AVFoundation order, usually 1 on Mac)."""
    for idx, name in _avfoundation_video_devices():
        if _is_innomaker(name):
            return idx
    for i, name in enumerate(_mac_camera_names()):
        if _is_innomaker(name):
            return i
    return None


def _innomaker_indices_from_profiler() -> list[int]:
    idx = innomaker_index()
    return [idx] if idx is not None else [1]


def _tune_innomaker(cap) -> None:
    """Minimal USB settings — avoid exposure tweaks that can zero-out the IR feed."""
    import cv2

    try:
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
    except cv2.error:
        pass


def _open_capture(index: int, width: int = 0, height: int = 0):
    import cv2

    cap = cv2.VideoCapture(index, cv2.CAP_AVFOUNDATION)
    if not cap.isOpened():
        cap = cv2.VideoCapture(index)
    if not cap.isOpened():
        return cap

    if width > 0:
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
    if height > 0:
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
    if _is_innomaker(_device_name(index)):
        _tune_innomaker(cap)
    return cap


def _frame_ok(frame) -> bool:
    """True if camera returned a valid image buffer (IR can be all-black but connected)."""
    return (
        frame is not None
        and frame.size > 0
        and len(frame.shape) >= 2
        and frame.shape[0] > 1
        and frame.shape[1] > 1
    )


def read_frame(cap, retries: int = 25):
    """Read a non-blank frame from the camera."""
    import cv2

    for _ in range(retries):
        ok, frame = cap.read()
        if ok and _frame_ok(frame):
            return frame
        cv2.waitKey(40)
    return None


def _warmup_reads(cap, max_reads: int = 90) -> bool:
    """Wait for InnoMaker USB to deliver a real frame (can take 10+ seconds)."""
    import cv2

    # Discard stale buffers from idle open.
    for _ in range(8):
        cap.read()
        cv2.waitKey(30)

    for i in range(max_reads):
        ok, frame = cap.read()
        if ok and _frame_ok(frame) and (int(frame.max()) > 0 or float(frame.mean()) > 2.0):
            return True
        if i in (20, 40, 60, 80, 100):
            print(f"  waiting for USB video... ({i}/{max_reads})", flush=True)
        cv2.waitKey(80)
    return False


def open_innomaker(width: int = 0, height: int = 0):
    """
    Open ONLY the InnoMaker USB camera (plugged in via cable).
    Ignores FaceTime, iPhone Continuity, Desk View, and all wireless cameras.
    Returns (cap, index) or (None, None).
    """
    import cv2

    av_devices = _avfoundation_video_devices()
    inno_only = [(idx, name) for idx, name in av_devices if _is_innomaker(name)]

    if not inno_only:
        print("InnoMaker USB not found. Plug the camera in with a USB cable.", flush=True)
        print("(Ignoring built-in / iPhone / wireless cameras)", flush=True)
        if av_devices:
            print("Cameras on this Mac:", flush=True)
            for idx, name in av_devices:
                tag = "blocked" if _is_blocked_camera(name) else "ignored"
                print(f"  [{idx}] {name}  ({tag})", flush=True)
        return None, None

    # Native first (worked at 1920x1080 before); then explicit sizes.
    if width > 0 and height > 0:
        sizes = [(width, height, f"{width}x{height}")]
    else:
        sizes = [
            (0, 0, "native"),
            (1920, 1080, "1920x1080"),
            (1280, 720, "1280x720"),
        ]

    for idx, label in inno_only:
        print(f"Opening InnoMaker USB at index {idx}: {label}", flush=True)
        for w, h, size_label in sizes:
            for attempt in range(1, 3):
                print(f"  attempt {attempt}/2 @ {size_label}...", flush=True)
                cap = _open_capture(idx, w, h)
                if not cap.isOpened():
                    time.sleep(0.5)
                    continue
                time.sleep(1.0)
                if _warmup_reads(cap):
                    fw = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
                    fh = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
                    ok, frame = cap.read()
                    brightness = f"{frame.mean():.0f}" if ok and frame is not None else "?"
                    print(
                        f"InnoMaker USB live: index {idx}, {fw}x{fh}, brightness={brightness}",
                        flush=True,
                    )
                    return cap, idx
                cap.release()
                time.sleep(0.8)

    print("InnoMaker detected but no video yet.", flush=True)
    print("Fix: unplug USB 5 sec & replug, close other camera apps, run again.", flush=True)
    return None, None


def _probe_device(index: int, name: str = "", retries: int = 12, warmup_s: float = 0.15) -> CameraInfo | None:
    cap = _open_capture(index)
    if not cap.isOpened():
        return None
    if warmup_s > 0:
        time.sleep(warmup_s)
    import cv2

    for _ in range(retries):
        ok, frame = cap.read()
        if ok and _frame_ok(frame):
            w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            cap.release()
            return CameraInfo(index=index, width=w, height=h, name=name)
        cv2.waitKey(40)
    cap.release()
    return None


def _max_camera_index() -> int:
    names = _mac_camera_names()
    return max(len(names), 3) if names else 3


def _list_devices(max_index: int | None = None) -> list[int]:
    return [c.index for c in list_cameras(max_index)]


def list_cameras(max_index: int | None = None) -> list[CameraInfo]:
    names = _mac_camera_names()
    limit = max_index if max_index is not None else _max_camera_index()
    found: list[CameraInfo] = []
    for i in range(limit):
        name = names[i] if i < len(names) else ""
        info = _probe_device(i, name=name, retries=15, warmup_s=0.3)
        if info is not None:
            found.append(info)
    return found


def resolve_device(explicit: int | None, use_builtin: bool) -> int | None:
    if explicit is not None:
        return explicit
    if use_builtin:
        cameras = list_cameras()
        return cameras[0].index if cameras else None
    idx = innomaker_index()
    return idx if idx is not None else 1


def pick_usb_camera(max_index: int | None = None) -> CameraInfo | None:
    cap, idx = open_innomaker()
    if cap is not None and idx is not None:
        w = int(cap.get(3))
        h = int(cap.get(4))
        names = _mac_camera_names()
        name = names[idx] if idx < len(names) else "InnoMaker"
        cap.release()
        return CameraInfo(index=idx, width=w, height=h, name=name)
    cameras = list_cameras(max_index)
    externals = [c for c in cameras if _looks_external(c)]
    return externals[0] if externals else (cameras[0] if cameras else None)


def main() -> int:
    parser = argparse.ArgumentParser(description="USB camera live preview")
    parser.add_argument("-d", "--device", type=int, default=None, help="Camera index (default: InnoMaker)")
    parser.add_argument("--builtin", action="store_true", help="Use built-in laptop camera")
    parser.add_argument("--list", action="store_true", help="List cameras")
    parser.add_argument("--width", type=int, default=0, help="Frame width (0 = default)")
    parser.add_argument("--height", type=int, default=0, help="Frame height (0 = default)")
    args = parser.parse_args()

    try:
        import cv2
    except ImportError:
        print("OpenCV not installed. Run: python3 -m pip install opencv-python", file=sys.stderr)
        return 1

    if args.list:
        cameras = list_cameras()
        if not cameras:
            print("No cameras responded. Check USB and Camera permissions.")
            return 1
        inno = innomaker_index()
        for cam in cameras:
            mark = "  ← InnoMaker" if inno is not None and cam.index == inno else ""
            print(cam.label + mark)
        return 0

    cap = None
    device = args.device
    if args.builtin or (device is not None and device != innomaker_index()):
        device = device if device is not None else 0
        cap = _open_capture(device, args.width, args.height)
        if not cap.isOpened():
            print(f"Could not open camera {device}.")
            return 1
    else:
        cap, device = open_innomaker(
            args.width or 1280,
            args.height or 720,
        )
        if cap is None:
            print("InnoMaker not found. Plug in USB and retry.")
            return 1

    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    print(f"Camera {device} — {w}x{h}. Press Q or Esc to quit.")

    window = "InnoMaker preview"
    cv2.namedWindow(window, cv2.WINDOW_NORMAL)
    try:
        while True:
            frame = read_frame(cap)
            if frame is None:
                print("Lost frame.")
                break
            cv2.imshow(window, frame)
            key = cv2.waitKey(1) & 0xFF
            if key in (ord("q"), ord("Q"), 27):
                break
    finally:
        cap.release()
        cv2.destroyAllWindows()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
