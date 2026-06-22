"""
Record timestamped MP4 clips from InnoMaker USB camera to data/raw_captures/.

Input:  InnoMaker UVC cam (Windows DirectShow index 1, MJPEG, 1280x720 default).
Output: data/raw_captures/<session>/<timestamp>.mp4 + sidecar .json per clip.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path

import cv2

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR  = REPO_ROOT / "data" / "raw_captures"

INNOMAKER_INDEX = 1   # 0 = built-in laptop camera, 1 = InnoMaker USB


# ── camera ────────────────────────────────────────────────────────────────────

def _open_camera(width: int, height: int) -> cv2.VideoCapture:
    cap = cv2.VideoCapture(INNOMAKER_INDEX, cv2.CAP_DSHOW)
    if not cap.isOpened():
        print(f"ERROR: Cannot open camera at index {INNOMAKER_INDEX}. Is the InnoMaker plugged in?")
        sys.exit(1)

    cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
    cap.set(cv2.CAP_PROP_FRAME_WIDTH,  width)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
    cap.set(cv2.CAP_PROP_FPS, 60)
    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

    print(f"Warming up camera — allowing IR-Cut filter and auto-exposure to settle (3 s)...")
    for _ in range(90):
        cap.read()
        time.sleep(0.033)

    actual_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    actual_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    actual_fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    print(f"Camera ready: {actual_w}x{actual_h} @ {actual_fps:.0f} fps")
    return cap


def _measure_fps(cap: cv2.VideoCapture, n: int = 30) -> float:
    t0 = time.perf_counter()
    for _ in range(n):
        cap.read()
    return n / (time.perf_counter() - t0)


# ── recording ─────────────────────────────────────────────────────────────────

def _countdown(seconds: int) -> None:
    for i in range(seconds, 0, -1):
        print(f"  Recording in {i}...", flush=True)
        time.sleep(1)
    print("  *** RECORDING — press Ctrl+C to stop early ***\n", flush=True)


def record_clip(
    cap:          cv2.VideoCapture,
    out_path:     Path,
    duration_s:   float,
    fps:          float,
    mode:         str,
    notes:        str = "",
) -> Path:
    out_path.parent.mkdir(parents=True, exist_ok=True)

    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(str(out_path), fourcc, fps, (w, h))
    if not writer.isOpened():
        print("ERROR: VideoWriter failed to open. Check codec / path.")
        sys.exit(1)

    total_frames = int(duration_s * fps)
    written = 0
    t_start = time.perf_counter()

    try:
        while written < total_frames:
            ret, frame = cap.read()
            if not ret or frame is None:
                print("WARNING: dropped frame", flush=True)
                continue
            writer.write(frame)
            written += 1
            elapsed = time.perf_counter() - t_start
            remaining = duration_s - elapsed
            if written % int(fps) == 0:
                print(f"  {elapsed:.0f}s elapsed, {max(0, remaining):.0f}s remaining, {written} frames", flush=True)
    except KeyboardInterrupt:
        print("\nRecording stopped early by user.")

    writer.release()
    actual_fps = written / max(time.perf_counter() - t_start, 0.001)
    print(f"Saved {written} frames → {out_path.name}  (actual {actual_fps:.1f} fps)")

    sidecar = out_path.with_suffix(".json")
    sidecar.write_text(json.dumps({
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "mode":      mode,
        "resolution": [w, h],
        "fps":        round(actual_fps, 2),
        "duration_s": round(written / max(actual_fps, 1), 2),
        "frames":     written,
        "notes":      notes,
    }, indent=2))
    print(f"Sidecar  → {sidecar.name}")
    return out_path


# ── CLI ───────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Record InnoMaker USB camera clips for drone detection dataset."
    )
    parser.add_argument("session",               help="Session name (e.g. day_outdoor_01)")
    parser.add_argument("--mode",      choices=["day", "ir"], default="day",
                        help="Lighting mode tag: 'day' (color) or 'ir' (night IR). "
                             "The IR-cut filter switches automatically — this is bookkeeping only.")
    parser.add_argument("--duration",  type=float, default=30.0,
                        help="Clip length in seconds (default: 30)")
    parser.add_argument("--resolution", default="1280x720",
                        help="WxH, e.g. 1920x1080 or 1280x720 (default: 1280x720)")
    parser.add_argument("--clips",     type=int,   default=1,
                        help="Number of consecutive clips to record (default: 1)")
    parser.add_argument("--countdown", type=int,   default=5,
                        help="Countdown seconds before each clip (default: 5)")
    parser.add_argument("--notes",     default="",
                        help="Free-text notes written to sidecar JSON")
    args = parser.parse_args()

    try:
        w, h = (int(x) for x in args.resolution.lower().split("x"))
    except ValueError:
        print(f"ERROR: Invalid resolution '{args.resolution}'. Use WxH e.g. 1280x720.")
        sys.exit(1)

    session_dir = DATA_DIR / args.session
    session_dir.mkdir(parents=True, exist_ok=True)

    cap = _open_camera(w, h)
    fps = _measure_fps(cap)
    print(f"Measured camera FPS: {fps:.1f}")

    for clip_idx in range(args.clips):
        ts        = datetime.now().strftime("%Y%m%d_%H%M%S")
        clip_name = f"{ts}_{args.mode}.mp4"
        out_path  = session_dir / clip_name

        print(f"\n── Clip {clip_idx + 1}/{args.clips}: {clip_name} ──")
        if args.countdown > 0:
            _countdown(args.countdown)

        record_clip(cap, out_path, args.duration, fps, args.mode, args.notes)

    cap.release()
    print(f"\nDone. {args.clips} clip(s) saved to {session_dir}")


if __name__ == "__main__":
    main()
