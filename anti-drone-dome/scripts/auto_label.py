"""
Auto-label extracted frames with yolo11n_drone.pt; write YOLO .txt labels.

Input:  Folder of .jpg frames (output of extract_frames.py).
Output: YOLO-format .txt label alongside each image; review_queue.txt for uncertain detections.

Label format: <class_id> <cx> <cy> <w> <h>  (all values normalised 0-1, one box per line).
Empty .txt written for frames with zero detections (useful as hard-negative background examples).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT  = Path(__file__).resolve().parent.parent
MODELS_DIR = REPO_ROOT / "models"

# Detection thresholds
CONF_FLOOR   = 0.15   # include everything above this — over-inclusive by design
CONF_REVIEW  = 0.50   # detections below this go into review_queue.txt
CLASS_ID     = 0      # single-class model: drone = 0


def _ensure_weights() -> Path:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from drone_model import ensure_drone_weights
    return ensure_drone_weights()


def _label_lines(boxes) -> list[str]:
    lines = []
    for box in boxes:
        cx, cy, bw, bh = box.xywhn[0].tolist()
        lines.append(f"{CLASS_ID} {cx:.6f} {cy:.6f} {bw:.6f} {bh:.6f}")
    return lines


def auto_label(
    frames_dir: Path,
    weights:    Path,
    device:     str,
) -> None:
    from ultralytics import YOLO

    images = sorted(frames_dir.rglob("*.jpg")) + sorted(frames_dir.rglob("*.png"))
    if not images:
        print(f"ERROR: No .jpg/.png images found under {frames_dir}")
        sys.exit(1)

    print(f"Loading model: {weights.name}  device={device}")
    model = YOLO(str(weights))

    review_queue_path = frames_dir / "review_queue.txt"
    review_entries: list[str] = []

    total          = len(images)
    with_detects   = 0
    in_review      = 0

    print(f"Labeling {total} frames at conf≥{CONF_FLOOR} ...\n")

    for i, img_path in enumerate(images):
        results = model.predict(
            source=str(img_path),
            conf=CONF_FLOOR,
            verbose=False,
            device=device,
        )
        boxes = results[0].boxes

        # Filter to boxes above floor confidence
        kept_boxes   = [b for b in boxes if float(b.conf[0]) >= CONF_FLOOR]
        review_boxes = [b for b in kept_boxes if float(b.conf[0]) < CONF_REVIEW]

        label_path = img_path.with_suffix(".txt")

        if kept_boxes:
            label_path.write_text("\n".join(_label_lines(kept_boxes)))
            with_detects += 1
        else:
            label_path.write_text("")   # hard-negative background example

        if review_boxes:
            review_entries.append(str(img_path))
            in_review += 1

        if (i + 1) % 50 == 0 or (i + 1) == total:
            print(f"  [{i + 1}/{total}]  detections so far: {with_detects}  review: {in_review}")

    review_queue_path.write_text("\n".join(review_entries))

    # ── Summary ───────────────────────────────────────────────────────────────
    print(f"""
── Auto-label complete ──────────────────────────────────────────
  Total frames        : {total}
  Frames with detects : {with_detects}  ({100 * with_detects / max(total, 1):.1f}%)
  Frames no detects   : {total - with_detects}  (written as empty .txt background examples)
  In review queue     : {in_review}  (conf {CONF_FLOOR}–{CONF_REVIEW}, most likely wrong)
  Review queue file   : {review_queue_path}
─────────────────────────────────────────────────────────────────

── NEXT STEP: Correct labels in Roboflow ────────────────────────
1. Go to app.roboflow.com and create a new project (Object Detection, class: drone).
2. Upload the entire folder:  {frames_dir}
   Roboflow will import the .txt labels automatically (YOLO format).
3. Open the Annotate tab.  Filter by the paths listed in review_queue.txt
   to review only the uncertain detections first — fix or delete bad boxes.
4. For frames with zero auto-detections that actually contain a drone,
   add boxes manually (these are the most valuable hard-negative corrections).
5. Export → YOLOv8 format → download the zip.
6. Unzip to:  {REPO_ROOT / "data" / "labeled" / frames_dir.parent.name}
7. Run:  python scripts/merge_datasets.py --datasets data/labeled/<session>
─────────────────────────────────────────────────────────────────
""")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Auto-label frames with yolo11n_drone.pt; write YOLO .txt labels + review queue."
    )
    parser.add_argument("frames_dir",
                        help="Folder of extracted frames (output of extract_frames.py). "
                             "Can be a session folder or a single clip subfolder.")
    parser.add_argument("--weights", default=None,
                        help="Path to YOLO weights. Default: models/yolo11n_drone.pt "
                             "(downloaded automatically on first run).")
    parser.add_argument("--device",  default="0",
                        help="Inference device: '0' for GPU, 'cpu' for CPU (default: '0')")
    args = parser.parse_args()

    frames_dir = Path(args.frames_dir)
    if not frames_dir.is_absolute():
        candidate = REPO_ROOT / "data" / "extracted" / frames_dir
        frames_dir = candidate if candidate.exists() else Path.cwd() / frames_dir

    if not frames_dir.exists():
        print(f"ERROR: frames directory not found: {frames_dir}")
        sys.exit(1)

    weights = Path(args.weights) if args.weights else _ensure_weights()
    if not weights.exists():
        print(f"ERROR: weights not found at {weights}")
        sys.exit(1)

    auto_label(frames_dir, weights, args.device)


if __name__ == "__main__":
    main()
