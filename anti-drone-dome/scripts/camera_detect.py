"""
Live InnoMaker USB camera + YOLO threat detection for Windows (DirectShow).

Input:  InnoMaker UVC cam at DirectShow index 1 (index 0 = built-in laptop cam).
Output: Live preview window with 'Threat' bounding boxes; press Q or Esc to quit.
"""

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

from drone_model import ensure_drone_weights  # noqa: E402

os.environ.setdefault("OPENCV_LOG_LEVEL", "ERROR")

INNOMAKER_INDEX  = 1      # 0 = built-in laptop camera, 1 = InnoMaker USB
_CONF_DEFAULT    = 0.25
_PREDICT_CONF    = 0.20
_PREDICT_WIDTH   = 640
_DETECT_EVERY    = 1      # run YOLO every frame — GPU is fast enough now
_THREAT_LABEL    = "Threat"
_BOX_THICK       = 2
_LABEL_SCALE     = 1.0
_LABEL_THICK     = 3


# ── camera ────────────────────────────────────────────────────────────────────

def _open_camera(index: int, width: int = 1280, height: int = 720) -> "cv2.VideoCapture":
    import cv2

    cap = cv2.VideoCapture(index, cv2.CAP_DSHOW)
    if not cap.isOpened():
        return cap

    cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
    cap.set(cv2.CAP_PROP_FRAME_WIDTH,  width)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
    cap.set(cv2.CAP_PROP_FPS, 60)
    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
    return cap


def _warmup(cap: "cv2.VideoCapture", seconds: float = 3.0) -> bool:
    """Drain stale frames and let IR-cut filter / auto-exposure settle."""
    import cv2

    print(f"Warming up camera ({seconds:.0f}s for IR-cut filter and auto-exposure)...", flush=True)
    n = int(seconds / 0.033)
    for _ in range(n):
        cap.read()
        cv2.waitKey(1)

    # Verify we're getting real frames
    for _ in range(20):
        ok, frame = cap.read()
        if ok and frame is not None and frame.size > 0:
            return True
        cv2.waitKey(30)
    return False


def _list_cameras(max_index: int = 5) -> None:
    import cv2

    print("Scanning camera indices 0–4 ...")
    found = False
    for i in range(max_index):
        cap = cv2.VideoCapture(i, cv2.CAP_DSHOW)
        if cap.isOpened():
            ok, _ = cap.read()
            w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            tag = "  <- InnoMaker (used by default)" if i == INNOMAKER_INDEX else ""
            print(f"  [{i}] {w}x{h}{tag}" if ok else f"  [{i}] opened but no frame")
            found = True
        cap.release()
    if not found:
        print("  No cameras found.")


def _frame_ok(frame) -> bool:
    return (
        frame is not None
        and frame.size > 0
        and len(frame.shape) >= 2
        and frame.shape[0] > 1
        and frame.shape[1] > 1
    )


# ── background frame grabber ──────────────────────────────────────────────────

class _FrameGrabber:
    """Read camera in a background thread so YOLO never blocks the live preview."""

    def __init__(self, cap):
        self._cap     = cap
        self._lock    = threading.Lock()
        self._frame   = None
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


# ── detection drawing ─────────────────────────────────────────────────────────

def _passes_threshold(conf: float, threshold: float) -> bool:
    return conf >= threshold


def _draw_box(out, x1: int, y1: int, x2: int, y2: int, conf: float, class_name: str) -> None:
    import cv2

    color = (0, 120, 255)
    label = f"{class_name}  {conf:.2f}"
    cv2.rectangle(out, (x1, y1), (x2, y2), color, _BOX_THICK)
    font = cv2.FONT_HERSHEY_SIMPLEX
    (tw, th), baseline = cv2.getTextSize(label, font, _LABEL_SCALE, _LABEL_THICK)
    ty = max(y1 - 6, th + 4)
    cv2.rectangle(out, (x1, ty - th - 4), (x1 + tw + 4, ty + baseline), color, -1)
    cv2.putText(out, label, (x1 + 2, ty), font, _LABEL_SCALE,
                (255, 255, 255), _LABEL_THICK, cv2.LINE_AA)


def _draw_threats(frame, coco_boxes, drone_boxes, scale_x: float, scale_y: float,
                  threshold: float, coco_names: dict, drone_names: dict):
    out = frame.copy()
    for boxes, names in ((coco_boxes, coco_names), (drone_boxes, drone_names)):
        if boxes is None:
            continue
        for box in boxes:
            conf = float(box.conf[0])
            if not _passes_threshold(conf, threshold):
                continue
            cls_id = int(box.cls[0])
            class_name = names.get(cls_id, _THREAT_LABEL)
            x1, y1, x2, y2 = box.xyxy[0].tolist()
            _draw_box(out,
                      int(x1 * scale_x), int(y1 * scale_y),
                      int(x2 * scale_x), int(y2 * scale_y),
                      conf, class_name)
    return out


# ── model loading ─────────────────────────────────────────────────────────────

def _load_models_async(coco_path: str, drone_path: Path):
    from ultralytics import YOLO

    holder: dict = {}
    done  = threading.Event()
    err: list[BaseException] = []

    def _run():
        try:
            holder["coco"]  = YOLO(coco_path)
            holder["drone"] = YOLO(str(drone_path))
        except BaseException as exc:
            err.append(exc)
        finally:
            done.set()

    threading.Thread(target=_run, daemon=True).start()
    return holder, done, err


# ── main ──────────────────────────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Live InnoMaker USB camera + YOLO drone threat detection (Windows)."
    )
    parser.add_argument("-d", "--device", type=int, default=INNOMAKER_INDEX,
                        help=f"Camera index (default: {INNOMAKER_INDEX} = InnoMaker USB). "
                             "Use --list to see available cameras.")
    parser.add_argument("--list",   action="store_true", help="List available cameras and exit.")
    parser.add_argument("--model",  default="yolov8n.pt",
                        help="COCO model for people/objects (default: yolov8n.pt).")
    parser.add_argument("--drone-only", action="store_true",
                        help="Run only the drone model — skip COCO general detection.")
    parser.add_argument("--conf",   type=float, default=_CONF_DEFAULT,
                        help=f"Display confidence threshold (default: {_CONF_DEFAULT}).")
    parser.add_argument("--width",  type=int, default=1280)
    parser.add_argument("--height", type=int, default=720)
    args = parser.parse_args()

    try:
        import cv2
    except ImportError:
        print("Install OpenCV: python -m pip install opencv-python", file=sys.stderr)
        return 1

    if args.list:
        _list_cameras()
        return 0

    print(f"Opening InnoMaker USB at DirectShow index {args.device} ...", flush=True)
    cap = _open_camera(args.device, args.width, args.height)
    if not cap.isOpened():
        print(f"ERROR: Cannot open camera at index {args.device}.")
        print("Is the InnoMaker plugged in? Run with --list to see available cameras.")
        return 1

    if not _warmup(cap):
        print("ERROR: Camera opened but no frames received. Unplug and replug the USB cable.")
        cap.release()
        return 1

    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    print(f"InnoMaker live: {w}x{h}  index={args.device}", flush=True)

    grabber = _FrameGrabber(cap)
    time.sleep(0.3)

    window = "InnoMaker — Threat Detection  |  Q to quit"
    cv2.namedWindow(window, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(window, min(w, 1280), min(h, 720))

    drone_weights              = ensure_drone_weights()
    model_holder, model_ready, model_err = _load_models_async(args.model, drone_weights)
    print("Loading YOLO models in background (preview starts immediately)...", flush=True)

    coco_model       = None
    drone_model      = None
    coco_names       = {}
    drone_names      = {}
    last_coco_boxes  = None
    last_drone_boxes = None
    scale_x = scale_y = 1.0
    frame_i  = 0

    n_frames    = 0
    fps_display = 0.0
    t_prev      = time.perf_counter()

    try:
        while True:
            frame = grabber.read()
            if frame is None:
                cv2.waitKey(30)
                continue

            display = frame.copy()

            # ── YOLO inference ────────────────────────────────────────────────
            if not model_ready.is_set():
                cv2.putText(display, "Loading YOLO...", (10, 60),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)
            elif model_err:
                cv2.putText(display, f"Model error: {model_err[0]}", (10, 60),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
            else:
                if coco_model is None:
                    coco_model  = model_holder.get("coco")
                    drone_model = model_holder.get("drone")
                    if coco_model is None or drone_model is None:
                        break
                    coco_names  = coco_model.names  if coco_model  else {}
                    drone_names = drone_model.names if drone_model else {}
                    print("YOLO ready — GTX 1650 inference active.", flush=True)

                if frame_i % _DETECT_EVERY == 0:
                    fh, fw  = frame.shape[:2]
                    scale   = _PREDICT_WIDTH / fw
                    small   = cv2.resize(frame, (_PREDICT_WIDTH, int(fh * scale)))
                    scale_x = fw / _PREDICT_WIDTH
                    scale_y = fh / small.shape[0]
                    try:
                        if not args.drone_only:
                            coco_res = coco_model.predict(source=small, conf=_PREDICT_CONF, verbose=False, device=0)
                            last_coco_boxes = coco_res[0].boxes
                        drone_res = drone_model.predict(source=small, conf=_PREDICT_CONF, verbose=False, device=0)
                        last_drone_boxes = drone_res[0].boxes
                    except Exception as exc:
                        print(f"Detection error: {exc}", file=sys.stderr)
                frame_i += 1

                if last_coco_boxes is not None or last_drone_boxes is not None:
                    display = _draw_threats(
                        frame, last_coco_boxes, last_drone_boxes,
                        scale_x, scale_y, args.conf,
                        coco_names, drone_names,
                    )

            # ── FPS overlay ───────────────────────────────────────────────────
            n_frames += 1
            t_now = time.perf_counter()
            if t_now - t_prev >= 0.5:
                fps_display = n_frames / (t_now - t_prev)
                n_frames    = 0
                t_prev      = t_now

            mode_label = "Drone Model [base]" if args.drone_only else "InnoMaker USB"
            cv2.putText(display,
                        f"{mode_label}  |  FPS {fps_display:.1f}  |  conf>={args.conf}",
                        (10, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2, cv2.LINE_AA)

            cv2.imshow(window, display)
            if cv2.waitKey(1) & 0xFF in (ord("q"), ord("Q"), 27):
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
    raise SystemExit(main())
