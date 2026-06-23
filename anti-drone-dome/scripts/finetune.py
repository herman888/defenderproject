"""
Fine-tune yolo11n_drone.pt on data/merged/data.yaml using the ultralytics Python API.

Input:  data/merged/data.yaml (output of merge_datasets.py) + models/yolo11n_drone.pt.
Output: models/finetuned/<run_name>/weights/best.pt; prints mAP50, mAP50-95, P, R after training.
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

REPO_ROOT  = Path(__file__).resolve().parent.parent
MODELS_DIR = REPO_ROOT / "models"
DATA_YAML  = REPO_ROOT / "data" / "merged" / "data.yaml"

# GTX 1650 (4 GB VRAM) safe defaults at imgsz=640
_DEFAULT_BATCH   = 8
_DEFAULT_EPOCHS  = 100
_DEFAULT_PATIENCE = 15
_DEFAULT_IMGSZ   = 640
_DEFAULT_WORKERS = 4


def _ensure_base_weights() -> Path:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from drone_model import ensure_drone_weights
    return ensure_drone_weights()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Fine-tune yolo11n_drone.pt on the merged drone dataset."
    )
    parser.add_argument("--data",    default=str(DATA_YAML),
                        help=f"Path to data.yaml (default: {DATA_YAML})")
    parser.add_argument("--weights", default=None,
                        help="Base checkpoint. Default: models/yolo11n_drone.pt "
                             "(downloaded if missing).")
    parser.add_argument("--name",    default=None,
                        help="Run name for output folder under models/finetuned/. "
                             "Default: finetune_YYYYMMDD_HHMMSS")
    parser.add_argument("--epochs",  type=int,   default=_DEFAULT_EPOCHS)
    parser.add_argument("--batch",   type=int,   default=_DEFAULT_BATCH,
                        help=f"Batch size (default: {_DEFAULT_BATCH}). "
                             "Reduce to 4 if you see CUDA out-of-memory.")
    parser.add_argument("--imgsz",   type=int,   default=_DEFAULT_IMGSZ)
    parser.add_argument("--patience", type=int,  default=_DEFAULT_PATIENCE,
                        help="Early-stopping patience in epochs (default: 15).")
    parser.add_argument("--device",  default="0",
                        help="Training device: '0' for GPU, 'cpu' for CPU (default: '0')")
    parser.add_argument("--resume",  default=None,
                        help="Path to a checkpoint to resume training from.")
    args = parser.parse_args()

    data_path = Path(args.data)
    if not data_path.exists():
        print(f"ERROR: data.yaml not found at {data_path}")
        print("Run python scripts/merge_datasets.py first.")
        sys.exit(1)

    weights_path = Path(args.resume) if args.resume else (
        Path(args.weights) if args.weights else _ensure_base_weights()
    )
    if not weights_path.exists():
        print(f"ERROR: weights not found at {weights_path}")
        sys.exit(1)

    run_name = args.name or f"finetune_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    out_dir  = MODELS_DIR / "finetuned"
    out_dir.mkdir(parents=True, exist_ok=True)

    # ── Augmentation notes ────────────────────────────────────────────────────
    # ultralytics 8.x augmentation params available:
    #   mosaic=1.0      — mosaic (already default; key for small-object robustness)
    #   scale=0.9       — scale jitter 0-1 (default 0.5; increased for size variety)
    #   degrees=10.0    — rotation ±10° (default 0.0; drones appear at any angle)
    #   translate=0.2   — translation fraction (default 0.1)
    #   fliplr=0.5      — horizontal flip (default 0.5)
    #   flipud=0.1      — vertical flip (low — sky-background drones rarely upside-down)
    #   mixup=0.05      — MixUp (small value; helps with background diversity)
    #   copy_paste=0.1  — paste drone crops onto new backgrounds (small-object boost)
    #   hsv_h/s/v       — colour jitter (helps day↔IR domain gap somewhat)
    #
    # MOTION BLUR: ultralytics 8.x does NOT have a built-in motion-blur augmentation
    # parameter. Fast-moving drones will show blur in real footage that the model
    # won't see during training. Workaround options (not implemented here):
    #   1. albumentations MotionBlur applied as a custom transform in a wrapper
    #   2. Capture intentionally blurred frames during data collection (pan camera)
    #   3. Use ultralytics v9+ if/when it adds blur augmentation natively
    # ─────────────────────────────────────────────────────────────────────────

    from ultralytics import YOLO

    print(f"Loading base checkpoint: {weights_path.name}")
    model = YOLO(str(weights_path))

    print(f"""
── Training config ──────────────────────────────────────────────
  Base weights : {weights_path}
  Data         : {data_path}
  Run name     : {run_name}
  Device       : {args.device}
  imgsz        : {args.imgsz}
  batch        : {args.batch}
  epochs       : {args.epochs}  (early stop patience={args.patience})
  Output       : {out_dir / run_name}
─────────────────────────────────────────────────────────────────
""")

    results = model.train(
        data         = str(data_path),
        epochs       = args.epochs,
        patience     = args.patience,
        imgsz        = args.imgsz,
        batch        = args.batch,
        device       = args.device,
        workers      = _DEFAULT_WORKERS,
        project      = str(out_dir),
        name         = run_name,
        exist_ok     = True,
        resume       = bool(args.resume),
        # Augmentation tuned for small aerial objects + day/IR domain gap
        mosaic       = 1.0,
        scale        = 0.9,
        degrees      = 10.0,
        translate    = 0.2,
        fliplr       = 0.5,
        flipud       = 0.1,
        mixup        = 0.05,
        copy_paste   = 0.1,
        hsv_h        = 0.015,
        hsv_s        = 0.7,
        hsv_v        = 0.4,
        # Keep cache in RAM (16 GB available) to speed up epoch iterations
        cache        = True,
        # Optimiser
        optimizer    = "AdamW",
        lr0          = 0.001,
        weight_decay = 0.0005,
        warmup_epochs = 3,
    )

    best_pt = Path(results.save_dir) / "weights" / "best.pt"
    print(f"\nBest weights saved to: {best_pt}")

    # ── Validation on best checkpoint ─────────────────────────────────────────
    print("\n── Validation results (best.pt) ─────────────────────────────")
    best_model = YOLO(str(best_pt))
    metrics    = best_model.val(data=str(data_path), device=args.device, verbose=False)

    box = metrics.box
    print(f"  mAP50        : {box.map50:.4f}")
    print(f"  mAP50-95     : {box.map:.4f}")
    print(f"  Precision    : {box.mp:.4f}")
    print(f"  Recall       : {box.mr:.4f}")
    print("─────────────────────────────────────────────────────────────")

    print(f"""
── Done ─────────────────────────────────────────────────────────
  Fine-tuned model : {best_pt}
  To test on live camera:
    python scripts/camera_detect.py --model {best_pt}
─────────────────────────────────────────────────────────────────
""")


if __name__ == "__main__":
    main()
