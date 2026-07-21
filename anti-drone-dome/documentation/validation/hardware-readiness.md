# Hardware readiness

Run the reference software-in-the-loop profile:

```powershell
python scripts\run_hardware_validation.py `
  --profile hardware_profiles\reference_sil.json `
  --episodes 20 `
  --output reports\hardware_validation
```

Optional reference and candidate logs can be aligned in ENU or NED:

```powershell
python scripts\run_hardware_validation.py `
  --reference-log <reference.csv> `
  --candidate-log <candidate.csv> `
  --reference-frame ENU `
  --candidate-frame NED
```

## Profile modes

| Mode | Intended use |
|---|---|
| `sil` | Internal simulation and controller evidence |
| `sitl` | ArduPilot software-in-the-loop |
| `hil` | Hardware-in-loop profile after explicit approval |
| `hardware_readonly` | Telemetry inspection without actuation |

Profiles validate vehicle limits, sensors, links, safety acknowledgements, and
release gates. Read-only profiles cannot enable actuation.

## Current hardware boundary

The physical Omnibus and Fury boards are Betaflight/MSP systems. The project
represents them as read-only because the implemented command bridge is MAVLink
for ArduPilot SITL. Physical actuation remains disabled by default.

!!! danger
    Do not infer flight readiness from a passing SIL report. Hardware-ready
    requires measured interfaces, timing, log alignment, safety controls, and
    independent approval.

