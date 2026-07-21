# Flight controllers and protocol boundary

The project has **two physical quads**, each with a different flight controller (FC). Scripts live in `scripts/` and share helpers in `betaflight_common.sh` (DFU flash, cloud hex download, CLI over USB).

**Active profile:** `betaflight_fc.env` currently points at the **Omnibus** drone. Fury scripts source `betaflight_fc_fury.env` directly.

---

## Quick comparison

| | **Omnibus drone** (original) | **Fury drone** |
|---|---|---|
| **Board** | Omnibus F4 (Hobbywing XRotor Micro OMNIBUS F4 G2 class) | Diatone / Mamba **Fury F4 OSD** |
| **Betaflight target** | **`OMNIBUSF4SD`** | `FURYF4OSD` |
| **Firmware release** | `2025.12.5` | `2025.12.5` |
| **Radio build** | **Spektrum** (DX4e + satellite) | **Spektrum** (DX4e + satellite) |
| **Motor protocol** | DSHOT | DSHOT |
| **Setup script** | `setup_omnibus_f4.sh` | `setup_fury_f4.sh` |
| **Env file** | `betaflight_fc_omnibus.env` | `betaflight_fc_fury.env` |
| **USB recovery** | Flaky micro-USB → `stlink_recover_fc.sh` / DFU mass erase | BOOT + DFU → `fix_fury_dfu_flash.sh` |
| **Configurator** | [app.betaflight.com](https://app.betaflight.com) | Same |

---

## Hardware notes

### Omnibus F4 SD

- PCB may be labeled **HW906-YT4** (Hobbywing). Pad names (SBUS, TX1, 3V3) are **wiring**, not ST-Link.
- **BOOT** button by USB enters DFU. **OSD** pads near USB are factory test — not debug.
- If Mac shows **no** `/dev/cu.usb*` and `dfu-util -l` is empty, the USB data path may be bad; ST-Link (GND / SWCLK / SWDIO on bottom pads, battery on) is the fallback.
- Spektrum satellite on the **SBUS** pad needs correct Serial Rx (UART1) and often `serialrx_inverted`.

### Fury F4 OSD

- Same STM32 DFU workflow: hold **BOOT**, plug USB, release after ~3 s.
- Radio is wired for **Spektrum serial RX** — after flash, set **Receiver → SPEKTRUM2048 / SPEK2048OR2048** and enable the correct UART under **Ports**.

---

## Switching which drone you are flashing

```bash
cd anti-drone-dome/scripts

# Omnibus
bash setup_omnibus_f4.sh              # diagnose
bash setup_omnibus_f4.sh --flash      # restore build
bash setup_omnibus_f4.sh --spektrum   # Spektrum cloud build
bash fix_omnibus_dfu_flash.sh         # mass erase + Spektrum recovery

# Fury
bash setup_fury_f4.sh                 # diagnose + Spektrum instructions
bash setup_fury_f4.sh --flash         # Spektrum flash
bash fix_fury_dfu_flash.sh            # mass-erase + recovery flash
bash setup_fury_radio.sh              # Spektrum bind / configurator steps
```

To make **Fury** the default for generic scripts, edit `betaflight_fc.env` to source `betaflight_fc_fury.env`.

---

## File map

| File | Purpose |
|------|---------|
| `betaflight_fc.env` | Active profile pointer (Omnibus by default) |
| `betaflight_fc_omnibus.env` | Omnibus target + build flags |
| `betaflight_fc_fury.env` | Fury target + Spektrum build flags |
| `betaflight_common.sh` | Shared DFU, download, CLI helpers |
| `betaflight_flash.sh` | Generic DFU flash (uses active profile) |
| `stlink_recover_fc.sh` | Omnibus ST-Link restore |
| `fix_omnibus_dfu_flash.sh` | Omnibus DFU erase + Spektrum hex |
| `fix_fury_dfu_flash.sh` | Fury DFU erase + Spektrum hex |
| `betaflight_motor_test.py` | Interactive motor spin via CLI |

---

## Mac prerequisites

```bash
brew install dfu-util
# optional for Omnibus ST-Link recovery:
brew install stlink
```

Python serial access uses the venv at `gym-pybullet-drones/.venv` (see `PY=` in the env files).

See also: [Flashing](../firmware/flashing.md) · [Recovery](../firmware/recovery.md)
