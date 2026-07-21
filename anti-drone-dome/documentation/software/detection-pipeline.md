# Detection pipeline

Capture → extract frames → auto-label → Roboflow correct → merge → fine-tune YOLO.

This page is the website source of truth for the capture-to-training workflow.

---

## Hardware used for training / live detect

| Component | Details |
|-----------|---------|
| Camera | InnoMaker U20CAM-1080PD&N-S1 (USB 2.0 UVC) |
| Resolution | 1280×720 default, up to 1920×1080 |
| Vision | Day (color) + Night (IR) via IR-Cut |
| GPU (lab PC) | GTX 1650 4 GB — CUDA 12.6 (Windows path) |

---

## Models

| Model | Purpose |
|-------|---------|
| `yolov8n.pt` | COCO general objects |
| `yolo11n_drone.pt` | Baseline single-class drone detector (HuggingFace) |
| `models/finetuned/.../best.pt` | Fine-tuned on your footage |

---

## Scripts

| Script | What it does |
|--------|--------------|
| `test_camera.py` | Live preview + FPS |
| `scripts/capture_session.py` | Record MP4 + sidecar JSON |
| `scripts/extract_frames.py` | Frames at ~3 fps |
| `scripts/auto_label.py` | YOLO auto-labels |
| `scripts/merge_datasets.py` | Merge train/val splits |
| `scripts/finetune.py` | Fine-tune drone detector |
| `scripts/camera_detect.py` | Live threat overlay |

---

## Step 0 — Baseline (no training)

```bash
cd anti-drone-dome
python scripts/camera_detect.py
# or
bash run_camera_detect.sh
```

Fine-tuned model:

```bash
python scripts/camera_detect.py --model models/finetuned/<run>/weights/best.pt
```

---

## Step 1 — Capture

```bash
python scripts/capture_session.py day_outdoor_01 --mode day --duration 60 --clips 3
python scripts/capture_session.py ir_outdoor_01 --mode ir --duration 60 --clips 3
```

Output: `data/raw_captures/<session>/...mp4` + `.json`.

Tips: vary distance/angle; include empty frames (hard negatives); leave `--dedup` off for IR extract.

---

## Step 2 — Extract frames

```bash
python scripts/extract_frames.py day_outdoor_01
python scripts/extract_frames.py day_outdoor_01 --fps 3 --dedup   # day only
```

---

## Step 3 — Auto-label

```bash
python scripts/auto_label.py data/extracted/day_outdoor_01
```

Review `review_queue.txt` (conf 0.15–0.50) first in Roboflow.

---

## Step 4 — Correct in Roboflow

1. New Object Detection project — class `drone` (optional: `fpv_drone`, `loitering_munition`)
2. Upload `data/extracted/...`
3. Fix labels → Export YOLOv8 → unzip to `data/labeled/<session>/`

---

## Step 5 — Merge

```bash
python scripts/merge_datasets.py \
  --datasets data/labeled/day_outdoor_01 data/labeled/ir_outdoor_01
```

Canonical classes: `0 drone`, `1 fpv_drone`, `2 loitering_munition`.

---

## Step 6 — Fine-tune

```bash
python scripts/finetune.py --name larp_v1
python scripts/camera_detect.py --model models/finetuned/larp_v1/weights/best.pt
```

Defaults target GTX 1650 (`batch=8`, `imgsz=640`, mosaic + scale jitter).

---

## Quick reference

```bash
python scripts/camera_detect.py
python scripts/capture_session.py day_outdoor_01 --mode day --duration 60 --clips 3
python scripts/extract_frames.py day_outdoor_01
python scripts/auto_label.py data/extracted/day_outdoor_01
# Roboflow → data/labeled/
python scripts/merge_datasets.py --datasets data/labeled/day_outdoor_01
python scripts/finetune.py --name larp_v1
```

Keep dataset manifests and evaluation results with each trained model so a
deployed detector remains traceable to its source data.
