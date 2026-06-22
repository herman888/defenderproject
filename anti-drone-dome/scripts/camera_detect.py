#!/usr/bin/env python3
"""Live InnoMaker IR camera + YOLO threat detection (people, objects, drones)."""

from __future__ import annotations

import argparse
import os
import sys
import threading
import time
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

from camera_preview import (  # noqa: E402
    _avfoundation_video_devices,
    _frame_ok,
    _is_blocked_camera,
    _is_innomaker,
    innomaker_index,
    list_cameras,
    open_innomaker,
)
from drone_model import ensure_drone_weights  # noqa: E402

os.environ.setdefault("OPENCV_LOG_LEVEL", "ERROR")

_CONF_DEFAULT = 0.65
_PREDICT_CONF = 0.20
_PREDICT_WIDTH = 640
_DETECT_EVERY = 4
_THREAT_LABEL = "Threat"
_BOX_THICK = 2
_LABEL_SCALE = 1.0
_LABEL_THICK = 3


class _FrameGrabber:
    """Read camera in background so YOLO never blocks the live preview."""

    def __init__(self, cap):
        self._cap = cap
        self._lock = threading.Lock()
        self._frame = None
        self._running = True
        threading.Thread(target=self._loop, daemon=True).start()

    def _loop(self) -> None:
        import cv2

        while self._running:
            ok, frame = self._cap.read()
            if ok and _frame_ok(frame):
                with self._lock:
                    self._frame = frame
            else:
                cv2.waitKey(5)

    def read(self):
        with self._lock:
            return None if self._frame is None else self._frame.copy()

    def stop(self) -> None:
        self._running = False


def _passes_threshold(conf: float, threshold: float) -> bool:
    return conf >= threshold


def _draw_box(out, x1: int, y1: int, x2: int, y2: int):
    import cv2

    color = (0, 120, 255)
    cv2.rectangle(out, (x1, y1), (x2, y2), color, _BOX_THICK)
    font = cv2.FONT_HERSHEY_SIMPLEX
    (tw, th), baseline = cv2.getTextSize(_THREAT_LABEL, font, _LABEL_SCALE, _LABEL_THICK)
    ty = max(y1 - 6, th + 4)
    cv2.rectangle(out, (x1, ty - th - 4), (x1 + tw + 4, ty + baseline), color, -1)
    cv2.putText(out, _THREAT_LABEL, (x1 + 2, ty), font, _LABEL_SCALE, (255, 255, 255), _LABEL_THICK, cv2.LINE_AA)


def _draw_threats(frame, coco_boxes, drone_boxes, scale_x: float, scale_y: float, threshold: float):
    out = frame.copy()
    if coco_boxes is not None:
        for box in coco_boxes:
            conf = float(box.conf[0])
            if not _passes_threshold(conf, threshold):
                continue
            x1, y1, x2, y2 = box.xyxy[0].tolist()
            _draw_box(out, int(x1 * scale_x), int(y1 * scale_y), int(x2 * scale_x), int(y2 * scale_y))
    if drone_boxes is not None:
        for box in drone_boxes:
            conf = float(box.conf[0])
            if not _passes_threshold(conf, threshold):
                continue
            x1, y1, x2, y2 = box.xyxy[0].tolist()
            _draw_box(out, int(x1 * scale_x), int(y1 * scale_y), int(x2 * scale_x), int(y2 * scale_y))
    return out


def _load_models_async(coco_path: str, drone_path: Path):
    from ultralytics import YOLO

    holder: dict = {}
    done = threading.Event()
    err: list[BaseException] = []

    def _run():
        try:
            holder["coco"] = YOLO(coco_path)
            holder["drone"] = YOLO(str(drone_path))
        except BaseException as exc:
            err.append(exc)
        finally:
            done.set()

    threading.Thread(target=_run, daemon=True).start()
    return holder, done, err


def main() -> int:
    parser = argparse.ArgumentParser(description="InnoMaker IR + YOLO threat detection")
    parser.add_argument("-d", "--device", type=int, default=None, help="Force camera index")
    parser.add_argument("--list", action="store_true", help="List cameras")
    parser.add_argument("--model", default="yolov8n.pt", help="COCO model for people/objects")
    parser.add_argument("--conf", type=float, default=_CONF_DEFAULT, help="Threat threshold (default 65%%)")
    args = parser.parse_args()

    try:
        import cv2
    except ImportError:
        print("Install OpenCV: python3 -m pip install opencv-python", file=sys.stderr)
        return 1

    if args.list:
        av = _avfoundation_video_devices()
        if av:
            print("Cameras (InnoMaker USB is used automatically):")
            inno = innomaker_index()
            for idx, name in av:
                if _is_innomaker(name):
                    mark = "  <- USED"
                elif _is_blocked_camera(name):
                    mark = "  (blocked)"
                else:
                    mark = ""
                print(f"  {idx}: {name}{mark}")
        return 0

    print("Connecting to InnoMaker USB (cable only, no wireless)...", flush=True)
    cap, device = open_innomaker()
    if cap is None or not cap.isOpened():
        print("InnoMaker not found. Plug in USB cable, close other camera apps, retry.")
        return 1

    from camera_preview import _device_name

    cam_name = _device_name(device)
    if not _is_innomaker(cam_name):
        print(f"Wrong camera ({cam_name}). Expected InnoMaker USB.", flush=True)
        cap.release()
        return 1

    grabber = _FrameGrabber(cap)
    time.sleep(0.5)
    test = grabber.read()
    if test is None:
        print("No video from InnoMaker. Unplug USB 5 sec, replug, run again.", flush=True)
        grabber.stop()
        cap.release()
        return 1

    w, h = test.shape[1], test.shape[0]
    print(f"Live video: {cam_name} index {device} ({w}x{h}) br={test.mean():.0f}", flush=True)

    window = "InnoMaker - Threat detection"
    cv2.namedWindow(window, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(window, min(w, 1280), min(h, 720))

    drone_weights = ensure_drone_weights()
    model_holder, model_ready, model_err = _load_models_async(args.model, drone_weights)
    print("Loading YOLO models (video keeps playing)...", flush=True)

    t_prev = time.perf_counter()
    n_frames = 0
    fps_display = 0.0
    coco_model = None
    drone_model = None
    last_coco_boxes = None
    last_drone_boxes = None
    scale_x = scale_y = 1.0
    frame_i = 0

    try:
        while True:
            frame = grabber.read()
            if frame is None:
                cv2.waitKey(30)
                continue

            display = frame.copy()

            if not model_ready.is_set():
                cv2.putText(display, "Loading YOLO...", (10, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)
            elif model_err:
                cv2.putText(display, f"Model error: {model_err[0]}", (10, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
            else:
                if coco_model is None:
                    coco_model = model_holder.get("coco")
                    drone_model = model_holder.get("drone")
                    if coco_model is None or drone_model is None:
                        break
                    print("YOLO ready.", flush=True)

                if frame_i % _DETECT_EVERY == 0:
                    fh, fw = frame.shape[:2]
                    scale = _PREDICT_WIDTH / fw
                    small = cv2.resize(frame, (_PREDICT_WIDTH, int(fh * scale)))
                    scale_x = fw / _PREDICT_WIDTH
                    scale_y = fh / small.shape[0]
                    try:
                        coco_res = coco_model.predict(source=small, conf=_PREDICT_CONF, verbose=False)
                        drone_res = drone_model.predict(source=small, conf=_PREDICT_CONF, verbose=False)
                        last_coco_boxes = coco_res[0].boxes
                        last_drone_boxes = drone_res[0].boxes
                    except Exception as exc:
                        print(f"Detection error: {exc}", file=sys.stderr)
                frame_i += 1

                if last_coco_boxes is not None or last_drone_boxes is not None:
                    display = _draw_threats(
                        frame, last_coco_boxes, last_drone_boxes, scale_x, scale_y, args.conf
                    )

            n_frames += 1
            t_now = time.perf_counter()
            if t_now - t_prev >= 0.5:
                fps_display = n_frames / (t_now - t_prev)
                n_frames = 0
                t_prev = t_now

            cv2.putText(
                display,
                f"InnoMaker USB | FPS {fps_display:.1f}",
                (10, 28),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.8,
                (0, 255, 0),
                2,
                cv2.LINE_AA,
            )
            cv2.imshow(window, display)
            key = cv2.waitKey(1) & 0xFF
            if key in (ord("q"), ord("Q"), 27):
                break
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    finally:
        grabber.stop()
        cap.release()
        cv2.destroyAllWindows()
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        raise SystemExit(0)
