# Betaflight firmware — two drones, two boards

The project has **two physical quads**, each with a different flight controller (FC). Scripts live in `anti-drone-dome/scripts/` and share helpers in `betaflight_common.sh` (DFU flash, cloud hex download, CLI over USB).

**Active profile:** `betaflight_fc.env` currently points at the **Omnibus** drone. Fury scripts source `betaflight_fc_fury.env` directly.

---

## Quick comparison

| | **Omnibus drone** (original) | **Fury drone** |
|---|---|---|
| **Board** | Omnibus F4 (Hobbywing XRotor Micro OMNIBUS F4 G2 class) | Diatone / Mamba **Fury F4 OSD** (or F405 MK2 class) |
| **Betaflight target** | `OMNIBUSF4` — use **`OMNIBUSF4SD`** if Configurator shows *Omnibus F4 SD* | `FURYF4OSD` |
| **Firmware release** | `2025.12.4` | `2025.12.4` |
| **Default radio build** | **CRSF** (ExpressLRS / Crossfire style) | **Spektrum** (DX4e + satellite) |
| **Motor protocol** | DSHOT | DSHOT |
| **Setup script** | `setup_omnibus_f4.sh` | `setup_fury_f4.sh` |
| **Env file** | `betaflight_fc_omnibus.env` | `betaflight_fc_fury.env` |
| **USB recovery** | Often flaky micro-USB → `stlink_recover_fc.sh` if DFU dead | BOOT button + DFU usually works → `fix_fury_dfu_flash.sh` |
| **Configurator** | [app.betaflight.com](https://app.betaflight.com) | Same |

---

## Hardware notes

### Omnibus F4

- PCB may be labeled **HW906-YT4** (Hobbywing). Pad names (SBUS, TX1, 3V3) are **wiring**, not ST-Link.
- **BOOT** button by USB enters DFU. **OSD** pads near USB are factory test — not debug.
- If Mac shows **no** `/dev/cu.usb*` and `dfu-util -l` is empty, the USB data path may be bad; ST-Link (GND / SWCLK / SWDIO on bottom pads, battery on) is the fallback.

### Fury F4 OSD

- Same STM32 DFU workflow: hold **BOOT**, plug USB, release after ~3 s.
- Radio is wired for **Spektrum serial RX** — after flash, set **Receiver → SPEKTRUM2048** and enable the correct UART under **Ports**.

---

## Switching which drone you are flashing

```bash
cd anti-drone-dome/scripts

# Omnibus (default via betaflight_fc.env)
bash setup_omnibus_f4.sh           # diagnose
bash setup_omnibus_f4.sh --flash   # restore 2025.12.4 + CRSF
bash setup_omnibus_f4.sh --spektrum  # same board, Spektrum build

# Fury
bash setup_fury_f4.sh              # diagnose + Spektrum instructions
bash setup_fury_f4.sh --flash        # 2025.12.4 + Spektrum
bash fix_fury_dfu_flash.sh           # mass-erase + recovery flash
bash setup_fury_radio.sh             # Spektrum bind / configurator steps
```

To make **Fury** the default for generic scripts (`betaflight_flash.sh`, `betaflight_common.sh`), edit `betaflight_fc.env`:

```bash
# source betaflight_fc_omnibus.env   # comment out
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/betaflight_fc_fury.env"
```

---

## DFU flash flow (both boards)

1. **Props off.** Battery on for full power / motor tests; optional for flash only.
2. Quit Chrome / Betaflight Configurator if the serial port is busy.
3. Enter DFU: CLI command `bl`, or hold **BOOT** while plugging USB.
4. Scripts call the [Betaflight cloud build API](https://build.betaflight.com), cache hex under `/tmp/bf_<TARGET>_<RELEASE>.hex`, and flash with `dfu-util`.
5. Unplug USB, wait 5 s, replug **without** holding BOOT. Status LED should blink; port reappears as `/dev/cu.usbmodem*`.

**Motor test (after USB works):**

```bash
python3 anti-drone-dome/scripts/betaflight_motor_test.py
```

---

## ST-Link recovery (Omnibus only)

When USB serial and DFU are both dead:

```bash
brew install stlink
bash anti-drone-dome/scripts/stlink_recover_fc.sh
```

Wire ST-Link **GND, SWDIO, SWCLK** to FC pads; power FC with battery. Uses `st-flash` to write the same `2025.12.4` hex as the DFU path.

---

## File map

| File | Purpose |
|------|---------|
| `betaflight_fc.env` | Active profile pointer (Omnibus by default) |
| `betaflight_fc_omnibus.env` | Omnibus target + CRSF build flags |
| `betaflight_fc_fury.env` | Fury target + Spektrum build flags |
| `betaflight_common.sh` | Shared DFU, download, CLI helpers |
| `betaflight_flash.sh` | Generic DFU flash (uses active profile) |
| `betaflight_flash_omnibus.sh` | Older standalone Omnibus flash (hardcoded port) |
| `stlink_recover_fc.sh` | Omnibus ST-Link restore |
| `fix_fury_dfu_flash.sh` | Fury DFU erase + Spektrum hex |
| `watch_and_flash_omnibus.sh` | Wait for USB then flash Omnibus |
| `betaflight_motor_test.py` | Interactive motor spin via CLI |

---

## Mac prerequisites

```bash
brew install dfu-util
# optional for Omnibus ST-Link recovery:
brew install stlink
```

Python serial access uses the venv at `gym-pybullet-drones/.venv` (see `PY=` in the env files). Adjust paths in `betaflight_fc_*.env` if your machine differs.
