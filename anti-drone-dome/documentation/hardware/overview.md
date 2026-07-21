# Hardware overview

Project LARP currently has two physical quads plus a USB camera for detection
work. The simulation does not claim these devices are connected unless a
validated hardware profile reports that state.

## Platforms

| Role | Platform | Notes |
|------|----------|--------|
| Original lab quad | Omnibus F4 SD (`OMNIBUSF4SD`) | Spektrum sat on SBUS / UART1 |
| Second lab quad | Mamba Fury F4 OSD (`FURYF4OSD`) | Spektrum / DX4e |
| Vision | InnoMaker U20CAM-1080P | Day + IR (IR-Cut), USB UVC |

## Radio

Both quads use a **Spektrum DX4e** (or compatible) with a satellite receiver.

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
| Default resolution | 1280×720 (up to 1920×1080) |
| Modes | Day (color) + Night (IR) |
| Interface | USB 2.0 UVC |

Live detect: `bash run_camera_detect.sh` from `anti-drone-dome/`.

## Power & safety

- **Props off** for all USB / Betaflight / motor-test work
- Battery on when testing motors or when USB data is flaky on Omnibus
- Never arm near people or indoors without clear space
