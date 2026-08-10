# Bench day 1: Windows camera and FC characterization

**Date:** 2026-08-10. **Scope:** Windows development host only; no Raspberry Pi, Hailo, battery, props, arming, motor command, setting write, or firmware flash.

## Measured camera results

The original enumeration artifact has invalid code provenance and is superseded; it is not evidence. The replacement transcript is `artifacts/camera/enumeration_20260810T233320Z.json`, stamped with commit `62db938`, which contains the generating harness. The device is `Innomaker-U20CAM-1080PD&N-S1` (VID:PID `0BDA:5856`). YUY2 is advertised at 5 fps for 1920x1080 and 10 fps for 1280x720. IR-cut/night mode and auto-exposure-priority are **NOT MEASURED VIA OPENCV/DIRECTSHOW**; that is not a driver-level absence claim.

| Requested mode | Achieved mean FPS | Interval p50 / p95 / p99 ms | Evidence |
| --- | ---: | --- | --- |
| 1920x1080 MJPEG | 29.962 | measured on this host/backend | `artifacts/camera/throughput_1920x1080_mjpg_20260810T233441Z.json` |
| 1280x720 MJPEG | 30.021 | measured on this host/backend | `artifacts/camera/throughput_1280x720_mjpg_20260810T233506Z.json` |
| 1280x720 YUY2 | 10.002 | measured on this host/backend | `artifacts/camera/throughput_1280x720_yuy2_20260810T233709Z.json` |
| 640x480 YUY2 | 29.996 | measured on this host/backend | `artifacts/camera/throughput_640x480_yuy2_20260810T233530Z.json` |
| 1280x800 MJPEG | 30.004 | measured on this host/backend | `artifacts/camera/throughput_1280x800_mjpg_20260810T233555Z.json` |

MJPEG cost is combined capture, pipe transfer, and decode; split decode cost is **NOT MEASURED**. Drop/duplicate counts are **NOT MEASURED** because the backend exposes no device sequence counter. The recurring p95/p99 tails across both high-bandwidth and 640x480 YUY2 modes are host/backend measurements, not a camera property: Windows scheduling and blocking pipe reads are plausible contributors. Re-measure on the Pi/Linux backend before attributing tail jitter to the device.

## Expectations tested

The USB 2.0 expectation was confirmed: uncompressed 1080p YUY2 is only advertised at 5 fps; 720p YUY2 is 10 fps, while MJPEG reaches approximately 30 fps at 1080p. No expectation was contradicted.

## FC interrogation

COM5 is a USB serial device (VID:PID `0483:5740`). With DTR asserted and `#` used solely to enter the CLI, the read-only transcript `artifacts/fc/raw_dump_20260810T233823Z.txt` identifies Betaflight 2025.12.5 on `FURYF4OSD` / STM32F40X, with a 16Mbit external flash device. VCP, UART1, UART3, and UART6 have no assigned serial functions; the receiver protocol is `SPEK2048`, while `RX rate: 0` and `RXLOSS` show no present receiver signal. The MCU unique ID and the ArduPilot-fit answer remain **NOT MEASURED**. No flashing, save, setting, arm, or motor command was sent.

## Not measured today

Glass-to-glass latency and FOV require an operator-facing screen/target setup. Intrinsics, recordings, target pixel-vs-range, crop-vs-resize detections, detection range, false-positive rate, capture-to-detection latency, tracking latency, NPU utilization, temperature, and power remain **NOT MEASURED**. Pi/Hailo work is blocked by absent hardware and was not attempted.

## Human decisions

1. Perform the displayed-flash and two-distance FOV procedures with an operator.
2. Resolve why COM5 provides no Betaflight CLI response before identifying an ArduPilot target or considering firmware changes.
3. Record non-held-out development clips, then run the candidate-model crop/resize/tile comparison. It is not a detector-performance claim.

## Verification

After the bench additions, the full test suite passed: **230 passed**. `mkdocs build --strict` also passed. A fresh Python 3.12 environment resolved every `requirements-bench.txt` pin: OpenCV 4.11.0, psutil 7.0.0, pyserial 3.5, torch 2.13.0+cpu, and ultralytics 8.3.151. There is no comparable pre-change run in this work session, so its result is **NOT MEASURED** rather than reconstructed.
