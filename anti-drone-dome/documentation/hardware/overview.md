# Hardware overview

Project LARP's first measurement stack is a Pi companion, a flight controller,
and a USB camera. The simulation does not claim these devices are connected
unless a validated hardware profile reports that state.

## Platforms

| Role | Platform | Notes |
|------|----------|--------|
| Perception compute | Raspberry Pi 5 + Pi AI HAT+ / AI Kit | Hailo-8/8L NPU; HailoRT + Dataflow Compiler and `.hef` export. Performance is **NOT MEASURED**. |
| Current airframe flight control | Diatone / Mamba Fury F4 OSD (`FURYF4OSD`) | Measured over USB: Betaflight 2025.12.5, STM32F40X; VCP/UART1/UART3/UART6 exposed. This is the current airframe. |
| Second fleet flight control | Omnibus F4 SD (`OMNIBUSF4SD`) | Separate physical quad; not yet interrogated in the fleet pass. |
| Motors | TOA 2306 2150KV, 5-inch class | At least one build. Pack voltage is **NOT CONFIRMED**. |
| Vision | InnoMaker U20CAM-1080PD&N-S1 | USB 2.0 UVC day/IR camera; direct Pi USB connection, not CSI. |
| Analog FPV | Lumenier camera/VTX stack, 5.8 GHz whip, LEDs, 470 uF low-ESR cap | Present and wired; separate from the Pi perception path. |
| Receiver | `SPEK2048` configured on the current FURYF4OSD | Real Spektrum fleet ecosystem; physical receiver presence/binding remains **NOT MEASURED**. No live signal at interrogation (`RXLOSS`, RX rate 0). |

## Radio

The current airframe is the FURYF4OSD; the Omnibus is the second quad in the
fleet. `SPEK2048` on the FURY is a measured configuration, not evidence of a
bound receiver. Inventory the Spektrum transmitter and all satellites/receivers
before buying replacement radio hardware.

- Signal wire → **SBUS** pad (UART1 Serial Rx)
- Power → **3.3V** (not 5V)
- Ground → **GND**

Details: [Radio](radio.md).

## Flight controllers

Board targets, pads, and setup scripts: [Flight Controllers](flight-controllers.md).

## Camera (detection)

| Spec | Value |
|------|--------|
| Model | InnoMaker U20CAM-1080PD&N-S1 |
| Native modes | 1080p30, YUY2 and MJPEG; auto IR-cut day/night, onboard IR LEDs and MEMS mic |
| Interface | USB 2.0 UVC directly to Pi 5 USB; not CSI ribbon |
| Lens | Wide, approximately 120 degrees diagonal / 102 degrees horizontal class |
| Capture envelope | Measured Windows/ffmpeg-host result: 1080p MJPEG approximately 30 fps; 720p YUY2 approximately 10 fps. Re-measure latency/jitter on the Pi/Linux backend. |

Live detect: `bash run_camera_detect.sh` from `anti-drone-dome/`.

### Camera limits and first evidence gate

USB 2.0 bandwidth means 1080p capture must use MJPEG rather than YUY2; CPU
decode cost must be measured. The sensor is rolling shutter, so airframe
vibration can smear imagery. A global-shutter IMX296-class camera is the named
upgrade path.

The wide lens is a terminal-lock camera, not an acquisition-at-range camera.
The useful range is estimated at roughly 20 to 40 m and is **NOT MEASURED**.
At approximately 102 degrees horizontal over 1920 pixels, a 25 cm target is a
geometric estimate of about 9 pixels at 30 m at native resolution, or about 3
pixels if the whole frame is resized to a 640-pixel model input. The pipeline
must center-crop or tile native-resolution imagery rather than resize the whole
frame. Record the chosen crop configuration in the parameter register before
claiming a detection envelope.

## Power & safety

- **Props off** for all USB / Betaflight / motor-test work
- Battery on when testing motors or when USB data is flaky on Omnibus
- Never arm near people or indoors without clear space
