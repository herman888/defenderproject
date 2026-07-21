# Project LARP

**Localised Aerial Response Platform** — anti-drone detection, simulation, and intercept demonstrator.

This site is the living documentation for the anti-drone dome stack: physical quads, Betaflight firmware, YOLO detection, and PyBullet simulation. Add new pages anytime — see [Contributing](contributing.md).

---

## What this project covers

| Area | What we build |
|------|----------------|
| **Hardware** | Omnibus F4 + Fury F4 OSD quads, Spektrum / DX4e radio, InnoMaker USB camera |
| **Firmware** | Betaflight flash, DFU recovery, ST-Link fallback |
| **Software** | PyBullet intercept sim, YOLO drone detection, capture → fine-tune pipeline |
| **Demo** | Detect → track → intercept style aerial response |

---

## Quick start

### Simulation (Mac)

```bash
cd anti-drone-dome
bash run_mac.sh
```

### Camera + threat detection

```bash
cd anti-drone-dome
bash run_camera_detect.sh
```

### Docs site (this site)

```bash
cd anti-drone-dome
python3 -m venv .venv-docs          # first time only
source .venv-docs/bin/activate
pip install -r requirements-docs.txt  # first time only
mkdocs serve
```

Open [http://127.0.0.1:8000](http://127.0.0.1:8000).

---

## Sections

- **[Hardware](hardware/overview.md)** — boards, radio, camera
- **[Software](software/overview.md)** — sim, detection pipeline
- **[Firmware](firmware/flashing.md)** — DFU flash and recovery
- **[Gallery](gallery/overview.md)** — screenshots and renders (growing)

---

## Source notes

Long-form originals still live in the repo:

- `docs/FIRMWARE.md` — FC comparison and flash scripts
- `PIPELINE.md` — capture-to-fine-tune detection pipeline
- `README.md` — sim setup and controller notes
