# Project LARP

**Localised Aerial Response Platform** — anti-drone detection, simulation, and intercept demonstrator.

This site is the living technical record for the AEGIS counter-UAS research
stack: simulation, sensor fusion, guidance, machine learning, validation,
hardware integration, Betaflight firmware, and YOLO detection.

!!! note "For investors and technical partners"
    Start with the [stakeholder brief](briefing/partner-investor-brief.md),
    then use the [presentation and diligence kit](briefing/presentation-kit.md)
    to review the evidence, limitations, and next validation gate.

!!! info "Real implementation versus roadmap"
    The [implementation status](system/implementation-status.md) identifies
    running code, verified evidence, environment-dependent features, and future
    work. Archived prompts preserve design history but are not used as proof.

---

## What this project covers

| Area | What we build |
|------|----------------|
| **Hardware** | Omnibus F4 + Fury F4 OSD quads, Spektrum / DX4e radio, InnoMaker USB camera |
| **Firmware** | Betaflight flash, DFU recovery, ST-Link fallback |
| **Software** | PyBullet digital twin, Qt command center, radar/EO fusion, APN and residual RL |
| **Training** | Residual-policy curriculum plus real-camera YOLO capture-to-fine-tune pipeline |
| **Validation** | Named stress campaigns, mission records, ACMI replay, SIL/HIL readiness |
| **Demo** | Detect → fuse → track → intercept → replay and evidence reporting |

---

## Quick start

### Simulation

```bash
cd anti-drone-dome
python main.py --auto-start --render-backend opengl
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
- **[System](system/architecture.md)** — architecture, interfaces, safety boundaries
- **[Software](software/overview.md)** — simulation, guidance, ML, detection
- **[Validation](validation/overview.md)** — campaigns, evidence, hardware readiness
- **[Firmware](firmware/flashing.md)** — DFU flash and recovery
- **[Gallery](gallery/overview.md)** — verified screenshots and rendered views

---

## Source notes

MkDocs source lives entirely under `documentation/`. Repository-level README
files remain concise entry points for developers and link back to this site.
