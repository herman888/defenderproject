# Bench day 1: Windows camera and FC characterization

**Date:** 2026-08-10. **Scope:** Windows development host only; no Raspberry Pi, Hailo, battery, props, arming, motor command, setting write, or firmware flash.

## Measured camera results

The original enumeration artifact has invalid code provenance and is superseded; it is not evidence. The replacement DirectShow device/options transcript will record every enumerated format/mode. The device is `Innomaker-U20CAM-1080PD&N-S1` (VID:PID `0BDA:5856`). YUY2 is advertised at 5 fps for 1920x1080 and 10 fps for 1280x720. IR-cut/night mode and auto-exposure-priority are **NOT MEASURED VIA OPENCV/DIRECTSHOW**; that is not a driver-level absence claim.

| Requested mode | Achieved mean FPS | Interval p50 / p95 / p99 ms | Evidence |
| --- | ---: | --- | --- |
| 1920x1080 MJPEG | 29.962 | 31.603 / 51.845 / 62.392 | `artifacts/camera/throughput_1920x1080_mjpg_20260810T231221Z.json` |
| 1280x720 MJPEG | 30.021 | 31.575 / 50.663 / 63.170 | `artifacts/camera/throughput_1280x720_mjpg_20260810T231246Z.json` |
| 1280x720 YUY2 | 10.002 | 95.266 / 124.434 / 131.178 | `artifacts/camera/throughput_1280x720_yuy2_20260810T231448Z.json` |
| 640x480 YUY2 | 29.996 | 31.523 / 51.460 / 54.865 | `artifacts/camera/throughput_640x480_yuy2_20260810T231315Z.json` |
| 1280x800 MJPEG | 30.004 | 31.574 / 51.247 / 62.253 | `artifacts/camera/throughput_1280x800_mjpg_20260810T231513Z.json` |

MJPEG cost is combined capture, pipe transfer, and decode; split decode cost is **NOT MEASURED**. Drop/duplicate counts are **NOT MEASURED** because the backend exposes no device sequence counter. The recurring p95/p99 tails across both high-bandwidth and 640x480 YUY2 modes are host/backend measurements, not a camera property: Windows scheduling and blocking pipe reads are plausible contributors. Re-measure on the Pi/Linux backend before attributing tail jitter to the device.

## Expectations tested

The USB 2.0 expectation was confirmed: uncompressed 1080p YUY2 is only advertised at 5 fps; 720p YUY2 is 10 fps, while MJPEG reaches approximately 30 fps at 1080p. No expectation was contradicted.

## FC interrogation

COM5 is a USB serial device (VID:PID `0483:5740`). The read-only transcript is `artifacts/fc/raw_dump_20260810T231634Z.txt`; its metadata is `artifacts/fc/interrogation_20260810T231634Z.json`. The port returned no CLI bytes to Ctrl-C or the strict read-only query list. Firmware target, Betaflight version, board/MCU/UID, flash, resource allocation, receiver state, and the ArduPilot-fit answer are **NOT MEASURED**. The unblocker is a confirmed Betaflight CLI session on the FC VCP; no flashing was performed or recommended.

## Not measured today

Glass-to-glass latency and FOV require an operator-facing screen/target setup. Intrinsics, recordings, target pixel-vs-range, crop-vs-resize detections, detection range, false-positive rate, capture-to-detection latency, tracking latency, NPU utilization, temperature, and power remain **NOT MEASURED**. Pi/Hailo work is blocked by absent hardware and was not attempted.

## Human decisions

1. Perform the displayed-flash and two-distance FOV procedures with an operator.
2. Resolve why COM5 provides no Betaflight CLI response before identifying an ArduPilot target or considering firmware changes.
3. Record non-held-out development clips, then run the candidate-model crop/resize/tile comparison. It is not a detector-performance claim.

## Verification

After the bench additions, the full test suite passed: **230 passed**. `mkdocs build --strict` also passed. There is no comparable pre-change run in this work session, so its result is **NOT MEASURED** rather than reconstructed.
