"""
Live InnoMaker camera + YOLO detection + ByteTrack multi-object tracker.

Input:  InnoMaker USB camera (DirectShow index 1) + YOLO drone weights.
Output: Live preview with track IDs, centroids, velocity (px/frame), age overlaid;
        same data printed to console at ~5 Hz.

Tracker: supervision ByteTrack (replaces norfair — see DEPENDENCY NOTE below).

DEPENDENCY NOTE — norfair is NOT used here:
  norfair 2.3.0 pins numpy<2.0.0 which has no Python 3.14 wheel and cannot be
  built from source on this machine (no C compiler). It is incompatible.
  supervision 0.29+ ships ByteTrack natively, installs clean on Python 3.14,
  and uses Kalman + IoU matching which is more robust for fast drones than
  norfair's plain Euclidean distance.

  Install: pip install supervision   (already done)

# TODO — guidance handoff (NOT implemented in this step):
#   When this tracker yields a stable track (age > GUIDANCE_MIN_AGE frames),
#   the bearing and elevation computed from centroid + camera intrinsics should
#   be handed to main.py's guidance loop via the same IPC queue used by the
#   dashboard (_ctrl_q / DataLink.send_track). Specifically:
#     1. Convert centroid (px) → bearing/elevation (deg) using camera FOV constants
#     2. Estimate 3-D range via radar_return["range"] fused from sensors/radar.py
#     3. Build a guidance_track dict matching the RadarNode output schema
#     4. Call broadcaster.send_track(guidance_track) → DataLink → interceptor
#   That integration lives in main.py _run_one_mission(), not here.
"""

from __future__ import annotations

import argparse
import sys
import threading
import time
from collections import defaultdict
from pathlib import Path

import numpy as np

_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

from drone_model import ensure_drone_weights  # noqa: E402

INNOMAKER_INDEX   = 1
_PREDICT_CONF     = 0.25
_PREDICT_WIDTH    = 640
_GUIDANCE_MIN_AGE = 8    # TODO: tracks older than this are stable enough for guidance handoff

import os
os.environ.setdefault("OPENCV_LOG_LEVEL", "ERROR")


# ── camera (same pattern as camera_detect.py) ─────────────────────────────────

def _open_camera(index: int, width: int = 1280, height: int = 720):
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


def _warmup(cap, seconds: float = 3.0) -> bool:
    import cv2
    print(f"Warming up camera ({seconds:.0f}s)...", flush=True)
    for _ in range(int(seconds / 0.033)):
        cap.read()
        cv2.waitKey(1)
    for _ in range(20):
        ok, frame = cap.read()
        if ok and frame is not None and frame.size > 0:
            return True
        cv2.waitKey(30)
    return False


# ── background frame grabber (reused from camera_detect.py) ───────────────────

def _frame_ok(frame) -> bool:
    return (frame is not None and frame.size > 0
            and len(frame.shape) >= 2 and frame.shape[0] > 1 and frame.shape[1] > 1)


class _FrameGrabber:
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


# ── tracker state ─────────────────────────────────────────────────────────────

class _TrackState:
    """Maintain per-track centroid history for velocity estimation."""

    def __init__(self) -> None:
        self._centroids: dict[int, list[tuple[float, float]]] = defaultdict(list)
        self._first_seen: dict[int, int] = {}
        self._frame_count = 0

    def update(self, track_id: int, cx: float, cy: float) -> None:
        history = self._centroids[track_id]
        history.append((cx, cy))
        if len(history) > 10:
            history.pop(0)
        if track_id not in self._first_seen:
            self._first_seen[track_id] = self._frame_count

    def velocity(self, track_id: int) -> tuple[float, float]:
        history = self._centroids.get(track_id, [])
        if len(history) < 2:
            return 0.0, 0.0
        dx = history[-1][0] - history[-2][0]
        dy = history[-1][1] - history[-2][1]
        return dx, dy

    def age(self, track_id: int) -> int:
        return self._frame_count - self._first_seen.get(track_id, self._frame_count)

    def tick(self) -> None:
        self._frame_count += 1


# ── overlay drawing ───────────────────────────────────────────────────────────

def _draw_track(frame, x1: int, y1: int, x2: int, y2: int,
                track_id: int, vx: float, vy: float, age: int) -> None:
    import cv2

    color  = (0, 200, 255)
    cx, cy = (x1 + x2) // 2, (y1 + y2) // 2

    cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
    cv2.circle(frame, (cx, cy), 4, color, -1)

    speed = (vx**2 + vy**2) ** 0.5
    label = f"T{track_id}  v={speed:.1f}px  age={age}f"
    cv2.putText(frame, label, (x1, max(y1 - 6, 12)),
                cv2.FONT_HERSHEY_SIMPLEX, 0.55, color, 2, cv2.LINE_AA)

    # Velocity arrow
    if speed > 1.0:
        scale = min(30.0 / max(speed, 1.0), 4.0)
        end   = (int(cx + vx * scale), int(cy + vy * scale))
        cv2.arrowedLine(frame, (cx, cy), end, (0, 255, 100), 2, tipLength=0.3)

    # TODO guidance handoff marker
    if age >= _GUIDANCE_MIN_AGE:
        cv2.putText(frame, "STABLE", (x1, y2 + 14),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 255, 0), 1, cv2.LINE_AA)


# ── main ──────────────────────────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Live InnoMaker + YOLO + ByteTrack drone tracker (Windows)."
    )
    parser.add_argument("-d", "--device", type=int, default=INNOMAKER_INDEX)
    parser.add_argument("--model",  default=None,
                        help="YOLO weights path. Default: models/yolo11n_drone.pt")
    parser.add_argument("--conf",   type=float, default=_PREDICT_CONF)
    parser.add_argument("--width",  type=int,   default=1280)
    parser.add_argument("--height", type=int,   default=720)
    args = parser.parse_args()

    try:
        import cv2
        import supervision as sv
        from ultralytics import YOLO
    except ImportError as exc:
        print(f"Missing dependency: {exc}")
        print("Run: pip install supervision ultralytics opencv-python")
        return 1

    # ── camera ────────────────────────────────────────────────────────────────
    cap = _open_camera(args.device, args.width, args.height)
    if not cap.isOpened():
        print(f"ERROR: Cannot open camera at index {args.device}.")
        return 1
    if not _warmup(cap):
        print("ERROR: No frames from camera.")
        cap.release()
        return 1

    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    print(f"Camera: {w}x{h}  index={args.device}", flush=True)

    # ── model ─────────────────────────────────────────────────────────────────
    weights = Path(args.model) if args.model else ensure_drone_weights()
    print(f"Loading YOLO: {weights.name} ...", flush=True)
    model = YOLO(str(weights))
    print("YOLO ready.", flush=True)

    # ── tracker ───────────────────────────────────────────────────────────────
    tracker     = sv.ByteTrack()
    track_state = _TrackState()

    grabber = _FrameGrabber(cap)
    time.sleep(0.3)

    window = "InnoMaker — ByteTrack Drone Tracker  |  Q to quit"
    cv2.namedWindow(window, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(window, min(w, 1280), min(h, 720))

    n_frames    = 0
    fps_display = 0.0
    t_prev      = time.perf_counter()
    t_log       = time.perf_counter()

    print("\nTracking started. Console log at ~5 Hz.\n")

    try:
        while True:
            frame = grabber.read()
            if frame is None:
                cv2.waitKey(10)
                continue

            display = frame.copy()

            # ── YOLO inference ────────────────────────────────────────────────
            scale    = _PREDICT_WIDTH / w
            small    = cv2.resize(frame, (_PREDICT_WIDTH, int(h * scale)))
            scale_x  = w / _PREDICT_WIDTH
            scale_y  = h / small.shape[0]

            results  = model.predict(source=small, conf=args.conf,
                                     verbose=False, device=0)
            boxes    = results[0].boxes

            # ── Build supervision Detections ──────────────────────────────────
            if boxes is not None and len(boxes) > 0:
                xyxy  = boxes.xyxy.cpu().numpy()
                # Scale back to full frame coordinates
                xyxy[:, [0, 2]] *= scale_x
                xyxy[:, [1, 3]] *= scale_y
                confs      = boxes.conf.cpu().numpy()
                class_ids  = boxes.cls.cpu().numpy().astype(int)
                detections = sv.Detections(xyxy=xyxy, confidence=confs, class_id=class_ids)
            else:
                detections = sv.Detections.empty()

            # ── ByteTrack update ──────────────────────────────────────────────
            tracked = tracker.update_with_detections(detections)
            track_state.tick()

            # ── Draw + log ────────────────────────────────────────────────────
            active_tracks = []
            for i in range(len(tracked)):
                tid = int(tracked.tracker_id[i])
                x1, y1, x2, y2 = tracked.xyxy[i].astype(int)
                cx = (x1 + x2) / 2.0
                cy = (y1 + y2) / 2.0

                track_state.update(tid, cx, cy)
                vx, vy = track_state.velocity(tid)
                age    = track_state.age(tid)

                _draw_track(display, x1, y1, x2, y2, tid, vx, vy, age)
                active_tracks.append((tid, cx, cy, vx, vy, age))

                # TODO: when age >= _GUIDANCE_MIN_AGE, this track is stable.
                # Hand off bearing/elevation to main.py APN guidance here.
                # See module docstring for integration steps.

            # Console log ~5 Hz
            if active_tracks and time.perf_counter() - t_log >= 0.2:
                t_log = time.perf_counter()
                for tid, cx, cy, vx, vy, age in active_tracks:
                    speed = (vx**2 + vy**2) ** 0.5
                    stable = " [STABLE — ready for guidance handoff]" if age >= _GUIDANCE_MIN_AGE else ""
                    print(f"  T{tid:<3}  ctr=({cx:6.1f},{cy:6.1f})  "
                          f"v=({vx:+5.1f},{vy:+5.1f}) {speed:4.1f}px/f  "
                          f"age={age:3d}f{stable}", flush=True)

            # ── FPS overlay ───────────────────────────────────────────────────
            n_frames += 1
            t_now = time.perf_counter()
            if t_now - t_prev >= 0.5:
                fps_display = n_frames / (t_now - t_prev)
                n_frames    = 0
                t_prev      = t_now

            cv2.putText(display,
                        f"ByteTrack  |  FPS {fps_display:.1f}  |  "
                        f"tracks={len(active_tracks)}",
                        (10, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.8,
                        (0, 255, 0), 2, cv2.LINE_AA)

            cv2.imshow(window, display)
            if cv2.waitKey(1) & 0xFF in (ord("q"), ord("Q"), 27):
                break

    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        import traceback; traceback.print_exc()
        return 1
    finally:
        grabber.stop()
        cap.release()
        cv2.destroyAllWindows()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
