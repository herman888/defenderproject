"""
Convert DUT Anti-UAV dataset to YOLO format (images/ + labels/).

Input:  data/public_raw/dut-anti-uav/  (manually downloaded from Google Drive)
Output: data/public/dut-anti-uav/  with images/ and labels/ in YOLO format.

Expected source layout (one or both modalities):
  dut-anti-uav/
    train/
      <seq_name>/
        imgs/          ← frame images  (or video.avi)
        IR_label.json  ← {"exist": [1,0,...], "gt_rect": [[x,y,w,h],...]}
    test/
      ...

Annotation format assumed:
  gt_rect entries are [x, y, w, h] with x,y = top-left corner in pixels.
  exist = 1 means UAV is present; exist = 0 = no UAV (frame kept as background example).
  Use --bbox-format xyxy if your download uses upper-left/lower-right corners instead.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

import cv2

REPO_ROOT  = Path(__file__).resolve().parent.parent
RAW_DIR    = REPO_ROOT / "data" / "public_raw" / "dut-anti-uav"
OUT_DIR    = REPO_ROOT / "data" / "public" / "dut-anti-uav"
CLASS_ID   = 0   # single class: drone


def _to_yolo_xywh(bbox: list, img_w: int, img_h: int, fmt: str) -> tuple[float, float, float, float]:
    if fmt == "xywh":
        x, y, w, h = bbox
        cx = (x + w / 2) / img_w
        cy = (y + h / 2) / img_h
        nw = w / img_w
        nh = h / img_h
    else:   # xyxy
        x1, y1, x2, y2 = bbox
        cx = (x1 + x2) / 2 / img_w
        cy = (y1 + y2) / 2 / img_h
        nw = (x2 - x1) / img_w
        nh = (y2 - y1) / img_h
    return cx, cy, nw, nh


def _convert_sequence(
    seq_dir:  Path,
    out_imgs: Path,
    out_lbls: Path,
    bbox_fmt: str,
    dry_run:  bool,
) -> tuple[int, int]:
    """Convert one sequence. Returns (frames_with_drone, frames_background)."""

    # Find annotation file
    ann_file = next(seq_dir.glob("*.json"), None)
    if ann_file is None:
        print(f"  WARNING: no .json annotation in {seq_dir.name} — skipping")
        return 0, 0

    with ann_file.open() as f:
        ann = json.load(f)

    exists  = ann.get("exist",   ann.get("exists", []))
    gt_rect = ann.get("gt_rect", ann.get("get_rect", []))

    if not exists:
        print(f"  WARNING: empty 'exist' array in {ann_file.name} — skipping")
        return 0, 0

    # Find frame source: images folder or video file
    imgs_dir = next((seq_dir / d for d in ("imgs", "img", "images", "frames")
                     if (seq_dir / d).is_dir()), None)
    video    = next(seq_dir.glob("*.avi"), None) or next(seq_dir.glob("*.mp4"), None)

    if imgs_dir:
        frame_paths = sorted(imgs_dir.glob("*.jpg")) + sorted(imgs_dir.glob("*.png"))
    elif video:
        frame_paths = None   # will extract from video
    else:
        print(f"  WARNING: no images or video in {seq_dir.name} — skipping")
        return 0, 0

    seq_name = seq_dir.name
    with_drone = background = 0

    if frame_paths is not None:
        # Image-based sequence
        for i, (ex, rect) in enumerate(zip(exists, gt_rect)):
            if i >= len(frame_paths):
                break
            img_path = frame_paths[i]
            stem     = f"{seq_name}_{i:05d}"

            if not dry_run:
                out_imgs.mkdir(parents=True, exist_ok=True)
                out_lbls.mkdir(parents=True, exist_ok=True)
                shutil.copy2(img_path, out_imgs / (stem + img_path.suffix))

            if ex and rect and len(rect) == 4 and any(v > 0 for v in rect):
                img = cv2.imread(str(img_path))
                ih, iw = img.shape[:2] if img is not None else (720, 1280)
                cx, cy, nw, nh = _to_yolo_xywh(rect, iw, ih, bbox_fmt)
                label = f"{CLASS_ID} {cx:.6f} {cy:.6f} {nw:.6f} {nh:.6f}"
                if not dry_run:
                    (out_lbls / (stem + ".txt")).write_text(label)
                with_drone += 1
            else:
                if not dry_run:
                    (out_lbls / (stem + ".txt")).write_text("")
                background += 1
    else:
        # Video-based sequence
        cap = cv2.VideoCapture(str(video))
        i   = 0
        while True:
            ret, frame = cap.read()
            if not ret or i >= len(exists):
                break
            ex   = exists[i]
            rect = gt_rect[i] if i < len(gt_rect) else []
            stem = f"{seq_name}_{i:05d}"
            ih, iw = frame.shape[:2]

            if not dry_run:
                out_imgs.mkdir(parents=True, exist_ok=True)
                out_lbls.mkdir(parents=True, exist_ok=True)
                cv2.imwrite(str(out_imgs / (stem + ".jpg")), frame,
                            [cv2.IMWRITE_JPEG_QUALITY, 95])

            if ex and rect and len(rect) == 4 and any(v > 0 for v in rect):
                cx, cy, nw, nh = _to_yolo_xywh(rect, iw, ih, bbox_fmt)
                label = f"{CLASS_ID} {cx:.6f} {cy:.6f} {nw:.6f} {nh:.6f}"
                if not dry_run:
                    (out_lbls / (stem + ".txt")).write_text(label)
                with_drone += 1
            else:
                if not dry_run:
                    (out_lbls / (stem + ".txt")).write_text("")
                background += 1
            i += 1
        cap.release()

    return with_drone, background


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Convert DUT Anti-UAV dataset to YOLO format."
    )
    parser.add_argument("--input",  default=str(RAW_DIR),
                        help=f"Source dataset root (default: {RAW_DIR})")
    parser.add_argument("--output", default=str(OUT_DIR),
                        help=f"Output root (default: {OUT_DIR})")
    parser.add_argument("--bbox-format", choices=["xywh", "xyxy"], default="xywh",
                        help="Bounding box format in source JSON. "
                             "xywh = top-left + width/height (default). "
                             "xyxy = top-left + bottom-right corners.")
    parser.add_argument("--splits", nargs="+", default=["train", "test"],
                        help="Split folders to process (default: train test)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Count frames and print plan without writing files.")
    args = parser.parse_args()

    src = Path(args.input)
    dst = Path(args.output)

    if not src.exists():
        print(f"ERROR: Source not found: {src}")
        print("Download DUT Anti-UAV from the Google Drive link in the README:")
        print("  https://github.com/wangdongdut/DUT-Anti-UAV")
        print(f"Then extract to: {src}")
        sys.exit(1)

    total_drone = total_bg = total_seqs = 0

    for split in args.splits:
        split_dir = src / split
        if not split_dir.exists():
            print(f"  Split '{split}' not found in {src} — skipping")
            continue

        seqs = [d for d in split_dir.iterdir() if d.is_dir()]
        print(f"\nSplit '{split}': {len(seqs)} sequences")

        out_imgs = dst / "images"
        out_lbls = dst / "labels"

        for seq in sorted(seqs):
            wd, bg = _convert_sequence(seq, out_imgs, out_lbls, args.bbox_format, args.dry_run)
            total_drone += wd
            total_bg    += bg
            total_seqs  += 1
            print(f"  {seq.name:<40}  drone={wd:4d}  bg={bg:4d}")

    # Write data.yaml
    if not args.dry_run:
        import yaml
        (dst / "data.yaml").write_text(yaml.dump({
            "path":  str(dst),
            "train": "images",
            "val":   "images",
            "nc":    1,
            "names": ["drone"],
        }))
        (dst / "classes.txt").write_text("drone\n")

    print(f"""
── DUT Anti-UAV conversion complete {'(DRY RUN)' if args.dry_run else ''} ──
  Sequences   : {total_seqs}
  Drone frames: {total_drone}
  Background  : {total_bg}
  Output      : {dst}

NOTE: If bounding boxes look wrong, re-run with --bbox-format xyxy
      (some DUT releases use upper-left/lower-right corners instead of xywh).
Next: python scripts/merge_datasets.py --datasets {dst} ...
""")


if __name__ == "__main__":
    main()
