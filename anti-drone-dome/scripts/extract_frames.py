"""
Extract frames from captured MP4 clips at a target rate to data/extracted/.

Input:  A single .mp4 file OR a session folder under data/raw_captures/.
Output: data/extracted/<session>/<clip_name>/frame_%05d.jpg
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import cv2
import numpy as np

REPO_ROOT      = Path(__file__).resolve().parent.parent
DATA_RAW       = REPO_ROOT / "data" / "raw_captures"
DATA_EXTRACTED = REPO_ROOT / "data" / "extracted"

DEFAULT_EXTRACT_FPS  = 3.0   # frames per second to keep
DEFAULT_DIFF_THRESH  = 8.0   # mean-abs-diff below this → near-duplicate (skip)
JPEG_QUALITY         = 95


# ── duplicate detection ───────────────────────────────────────────────────────

def _is_near_duplicate(frame: np.ndarray, prev: np.ndarray | None, threshold: float) -> bool:
    if prev is None or threshold <= 0:
        return False
    if frame.shape != prev.shape:
        return False
    diff = cv2.absdiff(frame, prev)
    return float(diff.mean()) < threshold


# ── single clip extraction ────────────────────────────────────────────────────

def extract_clip(
    clip_path:      Path,
    out_dir:        Path,
    extract_fps:    float,
    dedup:          bool,
    diff_threshold: float,
) -> tuple[int, int]:
    """
    Extract frames from one clip. Returns (frames_kept, frames_skipped).
    """
    cap = cv2.VideoCapture(str(clip_path))
    if not cap.isOpened():
        print(f"  ERROR: Cannot open {clip_path.name}")
        return 0, 0

    source_fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    total      = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    keep_every = max(1, round(source_fps / extract_fps))

    out_dir.mkdir(parents=True, exist_ok=True)

    kept    = 0
    skipped = 0
    prev_kept: np.ndarray | None = None
    frame_idx = 0

    print(f"  {clip_path.name}: {source_fps:.0f} fps, {total} frames → keeping every {keep_every}th ({extract_fps:.1f} fps target)")

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        if frame_idx % keep_every == 0:
            if dedup and _is_near_duplicate(frame, prev_kept, diff_threshold):
                skipped += 1
            else:
                fname = out_dir / f"frame_{kept:05d}.jpg"
                cv2.imwrite(str(fname), frame, [cv2.IMWRITE_JPEG_QUALITY, JPEG_QUALITY])
                prev_kept = frame
                kept += 1

        frame_idx += 1

    cap.release()
    print(f"  → {kept} frames saved, {skipped} near-duplicates skipped")
    return kept, skipped


# ── batch mode ────────────────────────────────────────────────────────────────

def _resolve_clips(target: Path) -> list[tuple[Path, str, str]]:
    """
    Returns list of (clip_path, session_name, clip_stem) to process.
    Accepts either a single .mp4 or a session folder.
    """
    if target.is_file() and target.suffix.lower() == ".mp4":
        session = target.parent.name
        return [(target, session, target.stem)]

    if target.is_dir():
        clips = sorted(target.rglob("*.mp4"))
        if not clips:
            print(f"ERROR: No .mp4 files found in {target}")
            sys.exit(1)
        session = target.name
        return [(c, session, c.stem) for c in clips]

    print(f"ERROR: {target} is not an .mp4 file or a directory.")
    sys.exit(1)


# ── CLI ───────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Extract frames from capture clips for dataset labeling."
    )
    parser.add_argument("input",
                        help="Path to a single .mp4 clip or a session folder "
                             "(e.g. data/raw_captures/day_outdoor_01)")
    parser.add_argument("--fps",    type=float, default=DEFAULT_EXTRACT_FPS,
                        help=f"Target extraction rate in fps (default: {DEFAULT_EXTRACT_FPS}). "
                             "Lower = fewer near-duplicate frames, less labeling work.")
    parser.add_argument("--dedup",  action="store_true",
                        help="Skip near-duplicate frames (default: off). "
                             "Leave off for IR night footage where slow-moving drone = low diff.")
    parser.add_argument("--diff-threshold", type=float, default=DEFAULT_DIFF_THRESH,
                        help=f"Mean-abs-diff threshold for near-duplicate detection "
                             f"(default: {DEFAULT_DIFF_THRESH}). Only used with --dedup.")
    args = parser.parse_args()

    target = Path(args.input)
    if not target.is_absolute():
        # Try relative to raw captures dir first, then cwd
        candidate = DATA_RAW / target
        target = candidate if candidate.exists() else Path.cwd() / target

    clips = _resolve_clips(target)
    print(f"Found {len(clips)} clip(s) to process.\n")

    total_kept = total_skipped = 0

    for clip_path, session, stem in clips:
        out_dir = DATA_EXTRACTED / session / stem
        k, s = extract_clip(clip_path, out_dir, args.fps, args.dedup, args.diff_threshold)
        total_kept    += k
        total_skipped += s

    print(f"\n── Summary ──────────────────────────────────────────────")
    print(f"  Clips processed : {len(clips)}")
    print(f"  Frames kept     : {total_kept}")
    if args.dedup:
        print(f"  Frames skipped  : {total_skipped} (near-duplicates)")
    print(f"  Output root     : {DATA_EXTRACTED}")
    print(f"\nNext step: python scripts/auto_label.py {DATA_EXTRACTED / clips[0][1]}")


if __name__ == "__main__":
    main()
