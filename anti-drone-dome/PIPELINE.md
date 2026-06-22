# Drone Detection — Capture-to-Fine-Tune Pipeline

Project LARP | Anti-Drone Dome

---

## Hardware

| Component | Details |
|-----------|---------|
| Camera | InnoMaker U20CAM-1080PD&N-S1 (USB 2.0 UVC) |
| Resolution | 1280×720 default, capable of 1920×1080 |
| Vision | Day (color) + Night (IR) via automatic IR-Cut filter |
| IR LEDs | Onboard — no external illumination needed at night |
| Windows index | 1 (index 0 = built-in laptop camera) |
| GPU | NVIDIA GeForce GTX 1650 — 4 GB VRAM, CUDA 12.6 |
| CPU | Intel i5-9300HF — 4 cores / 8 threads |
| RAM | 16 GB |
| OS | Windows 11, Python 3.14.2 |

---

## Pre-trained Models

| Model | Source | Purpose |
|-------|--------|---------|
| `yolov8n.pt` | Ultralytics (COCO 80-class) | People, vehicles, general objects |
| `yolo11n_drone.pt` | HuggingFace `marie-kjelberg/drone-detector` | Single-class drone detector (baseline) |
| `models/finetuned/.../best.pt` | Output of `finetune.py` | Fine-tuned on your own footage |

Both pre-trained weights download automatically on first use.

---

## Scripts

| Script | What it does |
|--------|-------------|
| `test_camera.py` | Live InnoMaker preview with FPS counter |
| `scripts/capture_session.py` | Record timestamped MP4 clips + sidecar JSON |
| `scripts/extract_frames.py` | Pull frames from clips at 3 fps |
| `scripts/auto_label.py` | Auto-label frames with `yolo11n_drone.pt`; write YOLO `.txt` files |
| `scripts/merge_datasets.py` | Merge multiple YOLO datasets into one train/val split |
| `scripts/finetune.py` | Fine-tune `yolo11n_drone.pt` on merged dataset |
| `scripts/camera_detect.py` | Live InnoMaker feed with YOLO threat detection overlay |
| `scripts/drone_model.py` | Downloads `yolo11n_drone.pt` from HuggingFace |

---

## Step 0 — Use the pre-trained model right now

No data collection needed. This is your **baseline** to beat.

```
cd "c:\Users\aclie\Documents\Side Projects\defender_project\defenderproject\anti-drone-dome"
python scripts/camera_detect.py
```

Downloads `yolo11n_drone.pt` on first run, then opens the InnoMaker feed with live "Threat" bounding boxes.

To use a specific model:
```
python scripts/camera_detect.py --model models/finetuned/<run>/weights/best.pt
```

---

## Step 1 — Capture footage

Point the InnoMaker at your practice quadcopter and record.

```
# Day session — 3 clips of 60 seconds, 5-second countdown before each
python scripts/capture_session.py day_outdoor_01 --mode day --duration 60 --clips 3

# Night / IR session
python scripts/capture_session.py ir_outdoor_01 --mode ir --duration 60 --clips 3

# Higher resolution
python scripts/capture_session.py day_outdoor_01 --mode day --resolution 1920x1080 --duration 30
```

**Output:** `data/raw_captures/<session>/<timestamp>_<mode>.mp4` + sidecar `.json` per clip.

The `.json` sidecar contains:
```json
{
  "timestamp": "2026-06-22T11:40:21",
  "mode": "day",
  "resolution": [1280, 720],
  "fps": 60.0,
  "duration_s": 60.0,
  "frames": 3600,
  "notes": ""
}
```

Fill in `notes` manually after recording if needed.

**Tips:**
- Fly the quad at different distances, angles, and altitudes
- Include frames where the quad is not present — these become hard-negative background examples
- For IR sessions, record at dusk or in darkness so the IR LEDs activate

---

## Step 2 — Extract frames

Pulls individual JPEG frames from clips at a target rate. Default 3 fps avoids flooding the labeling queue with near-duplicate frames.

```
# Extract at 3 fps (default)
python scripts/extract_frames.py day_outdoor_01

# Extract at 5 fps
python scripts/extract_frames.py day_outdoor_01 --fps 5

# Skip near-duplicate frames (good for fast day footage, BAD for slow IR footage)
python scripts/extract_frames.py day_outdoor_01 --fps 3 --dedup

# Adjust duplicate sensitivity (lower = more aggressive skipping)
python scripts/extract_frames.py day_outdoor_01 --fps 3 --dedup --diff-threshold 5.0
```

**Output:** `data/extracted/<session>/<clip_name>/frame_00000.jpg` ...

> **IR footage note:** Leave `--dedup` off for night sessions. A slow-hovering quad against a static sky produces very low frame-diff values, so dedup will incorrectly skip valid frames.

---

## Step 3 — Auto-label

Runs `yolo11n_drone.pt` over every extracted frame at a low confidence threshold (0.15) to generate candidate labels. Over-inclusive by design — you want candidates to review, not a clean final set.

```
python scripts/auto_label.py data/extracted/day_outdoor_01
python scripts/auto_label.py data/extracted/ir_outdoor_01

# Force CPU if GPU gives issues
python scripts/auto_label.py data/extracted/day_outdoor_01 --device cpu
```

**Output per frame:**
- `frame_00000.txt` — YOLO format label (`0 cx cy w h`, normalised 0–1)
- Empty `.txt` for frames with zero detections (hard-negative background examples — do not delete)
- `review_queue.txt` — paths of frames with detections between conf 0.15–0.50 (most likely wrong)

**Summary printed at end:**
```
Total frames        : 540
Frames with detects : 312  (57.8%)
Frames no detects   : 228  (written as empty .txt background examples)
In review queue     : 89   (conf 0.15–0.50, most likely wrong)
```

---

## Step 4 — Correct labels in Roboflow

No custom GUI needed — Roboflow handles this.

1. Go to **app.roboflow.com** → New Project → Object Detection
   - Class name: `drone` (add `fpv_drone`, `loitering_munition` if needed)

2. Upload the extracted folder:
   ```
   data/extracted/day_outdoor_01/
   ```
   Roboflow imports the `.txt` labels automatically (YOLO format).

3. Open **Annotate** tab:
   - Open `review_queue.txt` and work through those paths first — they are the most likely to be wrong
   - Fix or delete bad boxes
   - Add missing boxes on frames where the auto-labeler missed the drone entirely
   - Frames with empty `.txt` that actually contain a drone are the most valuable to label manually

4. Export → **YOLOv8 format** → Download zip

5. Unzip to:
   ```
   data/labeled/day_outdoor_01/
   data/labeled/ir_outdoor_01/
   ```
   Each folder should contain `images/`, `labels/`, and `data.yaml`.

---

## Step 5 — Merge datasets

Combines your labeled sessions and any public Anti-UAV datasets into one unified train/val split.

```
# Just your own footage
python scripts/merge_datasets.py \
  --datasets data/labeled/day_outdoor_01 data/labeled/ir_outdoor_01

# Add a public dataset
python scripts/merge_datasets.py \
  --datasets data/labeled/day_outdoor_01 data/labeled/ir_outdoor_01 data/labeled/anti_uav_public

# Custom val split (default 15%)
python scripts/merge_datasets.py \
  --datasets data/labeled/day_outdoor_01 --val-split 0.20
```

**Class name conflicts:**
If a public dataset uses different names (e.g. `uav`, `quadrotor`), the script stops and prints them. Re-run with `--map`:

```
python scripts/merge_datasets.py \
  --datasets data/labeled/anti_uav_public \
  --map "uav=drone" "quadrotor=fpv_drone" "shahed=loitering_munition"
```

**Canonical class list:**
| ID | Name |
|----|------|
| 0 | `drone` — generic quad / consumer drone |
| 1 | `fpv_drone` — fast FPV / attack drone |
| 2 | `loitering_munition` — Shahed-class fixed-wing |

**Output:** `data/merged/` with `images/train`, `images/val`, `labels/train`, `labels/val`, `data.yaml`.

Class distribution printed for sanity-check before training:
```
Class distribution (train):
  [0] drone                   843 boxes
  [1] fpv_drone               201 boxes
  [2] loitering_munition       97 boxes
```

---

## Step 6 — Fine-tune

Trains `yolo11n_drone.pt` on your merged dataset using the ultralytics Python API.

```
# Default run (GTX 1650 optimised)
python scripts/finetune.py

# Custom run name
python scripts/finetune.py --name larp_v1

# Reduce batch if you see CUDA out-of-memory
python scripts/finetune.py --batch 4

# Resume a stopped run
python scripts/finetune.py --resume models/finetuned/larp_v1/weights/last.pt
```

**Training config (defaults):**
| Parameter | Value | Reason |
|-----------|-------|--------|
| `imgsz` | 640 | Standard YOLO input; fits GTX 1650 at batch=8 |
| `batch` | 8 | Safe for 4 GB VRAM; reduce to 4 if OOM |
| `epochs` | 100 | With early stopping |
| `patience` | 15 | Stop if val mAP doesn't improve for 15 epochs |
| `optimizer` | AdamW | Better convergence than SGD for fine-tuning |
| `cache` | True | Load dataset into RAM (16 GB available) — faster epochs |
| `workers` | 2 | Safe for laptop CPU |

**Augmentations enabled:**
| Augmentation | Value | Why |
|-------------|-------|-----|
| `mosaic` | 1.0 | Paste 4 images together — critical for small object robustness |
| `scale` | 0.9 | Heavy scale jitter — drones appear at all sizes |
| `degrees` | 10.0 | Rotation — drones appear at any angle |
| `copy_paste` | 0.1 | Paste drone crops onto new backgrounds |
| `mixup` | 0.05 | Background domain diversity |
| `hsv_h/s/v` | defaults | Colour jitter — helps day↔IR domain gap |

> **Motion blur:** ultralytics 8.x has no built-in motion-blur augmentation. Fast-moving drones in real footage will appear blurred but training images won't show this. Workarounds: (1) capture intentionally blurred frames by panning the camera, (2) use the `albumentations` library with a custom transform wrapper, (3) check if a later ultralytics version adds it natively.

**Output:** `models/finetuned/<run_name>/weights/best.pt`

**Validation printed at end:**
```
mAP50        : 0.87
mAP50-95     : 0.61
Precision    : 0.84
Recall       : 0.79
```

Compare these numbers against the pre-trained baseline to confirm fine-tuning helped.

---

## Full pipeline — quick reference

```
# 1. Baseline (pre-trained, works right now)
python scripts/camera_detect.py

# 2. Capture
python scripts/capture_session.py day_outdoor_01 --mode day --duration 60 --clips 3
python scripts/capture_session.py ir_outdoor_01  --mode ir  --duration 60 --clips 3

# 3. Extract
python scripts/extract_frames.py day_outdoor_01
python scripts/extract_frames.py ir_outdoor_01

# 4. Auto-label
python scripts/auto_label.py data/extracted/day_outdoor_01
python scripts/auto_label.py data/extracted/ir_outdoor_01

# 5. [Manual] Upload to Roboflow, fix labels, export to data/labeled/

# 6. Merge
python scripts/merge_datasets.py \
  --datasets data/labeled/day_outdoor_01 data/labeled/ir_outdoor_01

# 7. Fine-tune
python scripts/finetune.py --name larp_v1

# 8. Deploy fine-tuned model
python scripts/camera_detect.py --model models/finetuned/larp_v1/weights/best.pt
```

---

## Data directory layout

```
data/
├── raw_captures/
│   ├── day_outdoor_01/
│   │   ├── 20260622_114000_day.mp4
│   │   └── 20260622_114000_day.json
│   └── ir_outdoor_01/
│       ├── 20260622_210000_ir.mp4
│       └── 20260622_210000_ir.json
├── extracted/
│   ├── day_outdoor_01/
│   │   └── 20260622_114000_day/
│   │       ├── frame_00000.jpg
│   │       ├── frame_00000.txt   ← YOLO label
│   │       └── review_queue.txt
│   └── ir_outdoor_01/
├── labeled/                       ← Roboflow exports go here
│   ├── day_outdoor_01/
│   │   ├── images/
│   │   ├── labels/
│   │   └── data.yaml
│   └── ir_outdoor_01/
└── merged/                        ← output of merge_datasets.py
    ├── images/
    │   ├── train/
    │   └── val/
    ├── labels/
    │   ├── train/
    │   └── val/
    └── data.yaml

models/
├── yolo11n_drone.pt               ← pre-trained baseline (auto-downloaded)
└── finetuned/
    └── larp_v1/
        └── weights/
            ├── best.pt            ← use this for deployment
            └── last.pt            ← use this to resume training
```
