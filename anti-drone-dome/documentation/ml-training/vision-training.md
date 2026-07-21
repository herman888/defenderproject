# Camera and vision training

Camera training is a direct bridge from the lab simulator to useful physical
hardware. It is separate from interceptor-policy training and produces a
different deployable artifact: YOLO detector weights.

## Implemented workflow

```text
InnoMaker camera
  -> recorded day/IR clips and metadata
  -> extracted frames
  -> baseline YOLO auto-labels
  -> human correction
  -> merged versioned dataset
  -> fine-tuned detector
  -> live camera or rendered-camera evaluation
```

The repository includes scripts for capture, frame extraction, auto-labeling,
dataset merging, fine-tuning, and live detection. See the
[detection pipeline](../software/detection-pipeline.md) for commands.

## Why it is valuable

- Uses observations from the actual camera intended for lab work.
- Captures real backgrounds, exposure, blur, compression, range, and viewing
  angles that a perfect simulated sensor cannot reproduce.
- Supports day and IR collection.
- Creates hard negatives from empty or confusing scenes.
- Can supply a trained model to both live detection and the simulated rendered
  camera path.
- Produces data that can reveal sensor and model limitations before flight.

## Evidence required for a model

Every candidate detector should retain:

- source capture session IDs and camera mode;
- train, validation, and held-out test splits;
- class definitions and dataset version;
- precision, recall, mAP, and confidence threshold;
- false-positive results on hard-negative footage;
- range, lighting, and target-size breakdowns;
- model hash, training configuration, and runtime backend;
- live-camera latency and achieved frame rate.

The repository now enforces these deployment basics with
`aegis.vision-model.v1`. `scripts/lock_vision_model.py` binds a manifest to the
exact artifact size and SHA-256 digest. `scripts/replay_camera_recording.py`
then runs that locked model over held-out video or ordered frames and writes
versioned companion-perception JSONL plus a hashed replay report. This makes
recorded evaluation reproducible before Pi hardware is available.

## Avoiding fake performance

A model is not validated merely because training loss decreases or a few
screenshots look correct. Report held-out results and test the exact exported
weights on untouched recordings. Simulation-generated images can augment the
dataset, but final claims must remain separated into:

1. synthetic rendered-camera performance;
2. recorded lab-camera performance;
3. controlled field performance.

No field-performance claim is currently made without corresponding real
footage and evaluation evidence.
