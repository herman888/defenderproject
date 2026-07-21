# Raspberry Pi 5 companion computer

The Raspberry Pi 5 can add meaningful onboard capability without replacing the
flight controller. The flight controller should retain stabilization, arming,
failsafes, and immediate motor control. The Pi is the higher-level perception
and evidence computer.

## Valuable onboard roles

| Role | Value |
|---|---|
| InnoMaker capture | Reads the actual USB UVC day/IR camera |
| Detector inference | Runs an optimized YOLO model and emits detections |
| Timestamping | Associates frames, detections, and FC telemetry on one clock |
| Mission recording | Stores compressed video, metadata, health, and events |
| Simulation bridge | Sends the same versioned observations to SIL/HIL |
| Health monitoring | Reports temperature, throttling, dropped frames, and latency |

The implemented `aegis.companion-perception.v1` contract sends timestamped image
dimensions, model identity, and validated bounding boxes. It deliberately does
not enable actuation.

## Exercise it before buying hardware

```powershell
python scripts\run_companion_smoke.py `
  --frames 10000 `
  --output reports\companion_smoke.json
```

This checks schema generation and serialization throughput on any computer. The
versioned profile is `hardware_profiles/raspberry_pi5_companion.json`.

## Lock and replay a detector before hardware arrives

The candidate manifest at `models/vision/drone_detector_candidate.json` is
intentionally unlocked because detector weights are not committed. After
downloading or exporting the exact artifact, copy the candidate manifest and
checksum-lock that copy:

```powershell
Copy-Item models\vision\drone_detector_candidate.json `
  models\vision\drone_detector_deployed.json
python scripts\lock_vision_model.py `
  --manifest models\vision\drone_detector_deployed.json `
  --artifact models\yolo11n_drone.pt
```

Replay untouched video or an ordered image directory through that exact model:

```powershell
python scripts\replay_camera_recording.py `
  --input recordings\held-out-day `
  --manifest models\vision\drone_detector_deployed.json `
  --output reports\held-out-day.perception.jsonl `
  --device auto
```

Replay refuses unlocked, missing, size-mismatched, or checksum-mismatched model
artifacts. Packets identify the locked model and use a recording-relative clock.
The sidecar report hashes both the source and output and labels throughput as a
host replay measurement, not Pi or field performance.

## When the Pi arrives

1. Install 64-bit Raspberry Pi OS and configure active cooling.
2. Connect the InnoMaker camera over USB and verify UVC modes and frame rate.
3. Deploy the checksum-locked model already exercised on held-out recordings.
4. Record CPU, accelerator, memory, temperature, throttling, inference latency,
   frame drops, and power draw.
5. Replay Pi detections into the simulator before connecting any autopilot.
6. Add read-only flight-controller telemetry and verify clock/frame alignment.
7. Consider commands only after SIL/HIL, safety, and loss-of-link gates pass.

## HAT selection

Choose the HAT only after measuring the model. An AI accelerator HAT may improve
inference, while an autopilot or sensor HAT solves a different problem. Confirm:

- Pi 5 and 64-bit OS compatibility;
- supported model format and operators;
- sustained rather than peak inference rate;
- power and cooling requirements;
- available CSI/USB/PCIe interfaces;
- driver lifecycle and reproducible deployment.

Do not purchase based only on advertised TOPS.
