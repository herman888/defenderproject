"""
Convert Anti-UAV RGB+IR paired dataset (ZhaoJ9014) to YOLO format.

Input:  data/public_raw/anti-uav/  (manually downloaded from Google Drive / Baidu sagx)
Output: data/public/anti-uav-rgb/  and  data/public/anti-uav-ir/  in YOLO format.

Expected source layout:
  anti-uav/
    train/
      <seq_name>/
        visible/          ← RGB frames  (or .avi)
        infrared/         ← IR frames   (or .avi)
        IR_label.json     ← {"exist": [1,0,...], "gt_rect": [[x,y,w,h],...]}
        RGB_label.json    ← same format for visible channel
    test/
      ...

Annotation format:
  gt_rect: [x, y, w, h]  — top-left pixel + width/height (Anti-UAV challenge standard).
  exist  : 1 = UAV visible, 0 = UAV absent (write empty .txt — hard negative).
  If your download uses [x1,y1,x2,y2] instead, pass --bbox-format xyxy.

Both RGB and IR channels are converted independently into separate output folders
so they can be merged selectively (e.g. add IR only for night-mode training).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import cv2

REPO_ROOT = Path(__file__).resolve().parent.parent
RAW_DIR   = REPO_ROOT / "data" / "public_raw" / "anti-uav"
CLASS_ID  = 0   # drone


def _to_yolo(bbox: list, iw: int, ih: int, fmt: str) -> str:
    if fmt == "xywh":
        x, y, w, h = [float(v) for v in bbox]
        cx = (x + w / 2) / iw
        cy = (y + h / 2) / ih
        nw = w / iw
        nh = h / ih
    else:  # xyxy
        x1, y1, x2, y2 = [float(v) for v in bbox]
        cx = (x1 + x2) / 2 / iw
        cy = (y1 + y2) / 2 / ih
        nw = (x2 - x1) / iw
        nh = (y2 - y1) / ih
    # Clamp to [0, 1]
    cx = max(0.0, min(1.0, cx))
    cy = max(0.0, min(1.0, cy))
    nw = max(0.0, min(1.0, nw))
    nh = max(0.0, min(1.0, nh))
    return f"{CLASS_ID} {cx:.6f} {cy:.6f} {nw:.6f} {nh:.6f}"


def _frames_from_dir(folder: Path) -> list[Path]:
    for sub in ("visible", "infrared", "imgs", "img", "rgb", "ir", "frames", ""):
        d = folder / sub if sub else folder
        if d.is_dir():
            frames = sorted(d.glob("*.jpg")) + sorted(d.glob("*.png"))
            if frames:
                return frames
    return []


def _video_in(folder: Path) -> Path | None:
    for sub in ("visible", "infrared", ""):
        d = folder / sub if sub else folder
        if d.is_dir():
            v = next(d.glob("*.avi"), None) or next(d.glob("*.mp4"), None)
            if v:
                return v
    return next(folder.glob("*.avi"), None) or next(folder.glob("*.mp4"), None)


def _convert_channel(
    seq_dir:    Path,
    ann_json:   Path,
    out_imgs:   Path,
    out_lbls:   Path,
    channel:    str,       # "rgb" or "ir"
    bbox_fmt:   str,
    dry_run:    bool,
) -> tuple[int, int]:
    """Convert one channel of one sequence. Returns (drone_frames, bg_frames)."""

    if not ann_json.exists():
        return 0, 0

    with ann_json.open() as f:
        ann = json.load(f)

    exists  = ann.get("exist",   [])
    gt_rect = ann.get("gt_rect", ann.get("get_rect", []))

    # Locate frames / video
    chan_aliases = {
        "rgb": ("visible", "rgb", "RGB", "color"),
        "ir":  ("infrared", "ir", "IR", "thermal"),
    }
    frame_paths: list[Path] | None = None
    video: Path | None = None

    for alias in chan_aliases.get(channel, [channel]):
        sub = seq_dir / alias
        if sub.is_dir():
            frames = sorted(sub.glob("*.jpg")) + sorted(sub.glob("*.png"))
            if frames:
                frame_paths = frames
                break
            vid = next(sub.glob("*.avi"), None) or next(sub.glob("*.mp4"), None)
            if vid:
                video = vid
                break

    if frame_paths is None and video is None:
        return 0, 0

    seq_name    = f"{seq_dir.name}_{channel}"
    drone_cnt   = bg_cnt = 0

    if not dry_run:
        out_imgs.mkdir(parents=True, exist_ok=True)
        out_lbls.mkdir(parents=True, exist_ok=True)

    def _process(i: int, frame: "cv2.Mat") -> None:
        nonlocal drone_cnt, bg_cnt
        ih, iw = frame.shape[:2]
        stem   = f"{seq_name}_{i:05d}"
        ex     = exists[i] if i < len(exists) else 0
        rect   = gt_rect[i] if i < len(gt_rect) else []

        if not dry_run:
            cv2.imwrite(str(out_imgs / (stem + ".jpg")), frame,
                        [cv2.IMWRITE_JPEG_QUALITY, 95])

        if ex and rect and len(rect) == 4 and any(float(v) > 0 for v in rect):
            label = _to_yolo(rect, iw, ih, bbox_fmt)
            if not dry_run:
                (out_lbls / (stem + ".txt")).write_text(label)
            drone_cnt += 1
        else:
            if not dry_run:
                (out_lbls / (stem + ".txt")).write_text("")
            bg_cnt += 1

    if frame_paths is not None:
        for i, fp in enumerate(frame_paths):
            if i >= len(exists):
                break
            img = cv2.imread(str(fp))
            if img is None:
                continue
            _process(i, img)
    else:
        cap = cv2.VideoCapture(str(video))
        i   = 0
        while True:
            ret, frame = cap.read()
            if not ret or i >= len(exists):
                break
            _process(i, frame)
            i += 1
        cap.release()

    return drone_cnt, bg_cnt


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Convert Anti-UAV RGB+IR dataset to YOLO format."
    )
    parser.add_argument("--input",    default=str(RAW_DIR),
                        help=f"Source dataset root (default: {RAW_DIR})")
    parser.add_argument("--output",   default=str(REPO_ROOT / "data" / "public"),
                        help="Parent output dir. RGB-><out>/anti-uav-rgb, IR-><out>/anti-uav-ir")
    parser.add_argument("--channels", nargs="+", choices=["rgb", "ir"], default=["rgb", "ir"],
                        help="Which channels to convert (default: rgb ir)")
    parser.add_argument("--splits",   nargs="+", default=["train", "test"])
    parser.add_argument("--bbox-format", choices=["xywh", "xyxy"], default="xywh",
                        help="Bounding box format in source JSON (default: xywh)")
    parser.add_argument("--dry-run",  action="store_true")
    args = parser.parse_args()

    src     = Path(args.input)
    out_par = Path(args.output)

    if not src.exists():
        print(f"ERROR: Source not found: {src}")
        print("Download Anti-UAV from Google Drive (link in README) or Baidu Drive (password: sagx):")
        print("  https://github.com/ZhaoJ9014/Anti-UAV")
        print(f"Extract to: {src}")
        sys.exit(1)

    totals: dict[str, tuple[int, int]] = {ch: (0, 0) for ch in args.channels}

    for split in args.splits:
        split_dir = src / split
        if not split_dir.exists():
            print(f"Split '{split}' not found — skipping")
            continue

        seqs = [d for d in split_dir.iterdir() if d.is_dir()]
        print(f"\nSplit '{split}': {len(seqs)} sequences")

        for seq in sorted(seqs):
            for ch in args.channels:
                ann_candidates = [
                    seq / f"{ch.upper()}_label.json",
                    seq / f"{ch}_label.json",
                    seq / "IR_label.json"  if ch == "ir"  else seq / "RGB_label.json",
                    seq / "label.json",
                ]
                ann = next((a for a in ann_candidates if a.exists()), None)
                if ann is None:
                    continue

                out_name = f"anti-uav-{ch}"
                out_imgs = out_par / out_name / "images"
                out_lbls = out_par / out_name / "labels"

                d, b = _convert_channel(seq, ann, out_imgs, out_lbls, ch, args.bbox_format, args.dry_run)
                prev_d, prev_b = totals[ch]
                totals[ch] = (prev_d + d, prev_b + b)

                if d + b > 0:
                    print(f"  {seq.name:<35} [{ch}]  drone={d:4d}  bg={b:4d}")

    # Write data.yaml per channel
    if not args.dry_run:
        import yaml
        for ch in args.channels:
            out_name = f"anti-uav-{ch}"
            dst = out_par / out_name
            if dst.exists():
                (dst / "data.yaml").write_text(yaml.dump({
                    "path":  str(dst),
                    "train": "images",
                    "val":   "images",
                    "nc":    1,
                    "names": ["drone"],
                }))

    print(f"\n── Anti-UAV conversion complete {'(DRY RUN)' if args.dry_run else ''} ──")
    for ch in args.channels:
        d, b = totals[ch]
        print(f"  [{ch.upper()}]  drone frames: {d:5d}  background: {b:5d}"
              f"  → data/public/anti-uav-{ch}/")
    print(f"\nNOTE: If boxes look wrong, re-run with --bbox-format xyxy")
    print(f"Next: python scripts/merge_datasets.py --datasets data/public/anti-uav-ir ...")


if __name__ == "__main__":
    main()
