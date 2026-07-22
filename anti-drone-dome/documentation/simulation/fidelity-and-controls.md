# Airframe fidelity, sensors, and operator controls

This release improves the authoritative simulation rather than only enlarging
or beautifying rendered models. PyBullet remains authoritative, APN remains the
nominal controller, and every new physical parameter carries an evidence status.

## Versioned airframe profiles

`aegis.airframe-profiles.v1` defines four profiles:

| Profile | Physical model | Evidence status |
|---|---|---|
| `intruder.shahed136.representative-v1` | 200 kg, 3.5 m length, 2.5 m span | representative, unvalidated |
| `intruder.consumer-quad.representative-v1` | 0.9 kg generic consumer quad | representative, unvalidated |
| `intruder.fpv.representative-v1` | 1.0 kg generic FPV | representative, unvalidated |
| `interceptor.reference-v1` | 1.5 kg reference interceptor | design placeholder |

Profiles separate:

- physical dimensions and rigid-body mass/inertia
- presentation scale
- propulsion and force envelopes
- aerodynamic coefficients, areas, stall speed, and stall angle
- actuator time constant and force slew limit
- energy capacity and minimum voltage fraction
- deterministic turbulence
- source, notes, and validation status

The loader rejects duplicate IDs, missing sections, invalid inertia, non-finite
values, unsupported dynamics models, and unknown evidence states. PyBullet body
mass and inertia are synchronized from the selected profile.

These are not manufacturer-grade digital twins. The values are bounded,
representative starting points that must be replaced or calibrated using
approved aircraft data.

## Dynamics added

The `fidelity_v1` path adds:

1. rigid-body mass and diagonal inertia from the profile
2. aerodynamic drag from density, coefficient, area, and airspeed
3. speed- and angle-dependent lift reduction through stall
4. first-order actuator response and force slew limits
5. deterministic turbulence force
6. mechanical-power energy consumption
7. voltage sag that reduces available force as energy declines
8. profile and remaining-energy telemetry in mission evidence

The current attitude layer remains kinematically aligned because torque-level
motor and control-surface identification has not been measured. That is the
next dynamics step after real thrust and inertia data are available.

## Model rendering

The old tactical renderer magnified the Shahed to roughly 30 m and small
quadrotors to 16-20 m. That made them visible but visually misleading.

The renderer now uses restrained tactical magnification:

- Shahed: 5 m displayed span, or 2x physical
- consumer quad: 1.2 m, or 3x physical
- FPV: 1.0 m, or approximately 3x physical
- interceptor: 1.65 m, or 3x physical

Track corners, labels, chase cameras, and prediction cues provide long-range
visibility instead of extreme model inflation. Unreal/Cesium can later offer a
strict 1:1 presentation mode.

## Runtime command-center controls

The command center now supports:

- pause and resume
- restart and abort
- live simulation-rate changes from 0.5x through 8x
- radar failure injection
- EO failure injection
- interceptor actuator failure injection
- existing intruder, route, launch-pad, and camera-view selection

Failure state transitions are written to mission events. Active failures,
airframe profile IDs, and remaining energy are recorded in telemetry. Actuator
failure also suppresses SITL setpoint transmission, so the injection does not
pretend a command was applied.

Hot-swapping an airframe or route inside a mission is intentionally unsupported.
Abort to the menu and start a new recorded run so evidence remains attributable
to one immutable scenario configuration.

## Sensor fidelity

### Radar

The radar now supports deterministic:

- scan dwell cadence
- processing latency
- false-alarm probability
- measurement noise
- Kalman process-noise tuning
- seeded Swerling-style acquisition
- Doppler clutter rejection and lock/coast behavior

### EO

The rendered EO path now supports:

- environment dropout probability
- frame latency
- exposure gain
- image noise before YOLO inference
- bounded lens-position distortion
- rolling-shutter position bias

Segmentation remains the simulation reference detector. Image exposure/noise is
applied to the YOLO image path; geometric effects are represented in the
reported track estimate. Real camera calibration is still required.

## Flight-log calibration

The calibration tool compares measured and simulated ENU or NED trajectories:

```powershell
python scripts\calibrate_airframe.py `
  --profile interceptor.reference-v1 `
  --reference evidence\measured.csv `
  --simulation evidence\simulation.csv `
  --output evidence\calibration.json
```

The report includes time alignment, trajectory RMSE, axis RMSE and bias,
velocity RMSE, and mean speeds. It emits propulsion and drag scale suggestions
bounded to `0.8-1.2`.

It never edits a profile automatically. Every report is marked
`candidate-only`, `review_required`, and `automatic_profile_mutation: false`.

## Verified software evidence

- 42 automated tests pass.
- A headless 8x mission with the 200 kg representative Shahed, radar dwell and
  latency, actuator lag, turbulence, and energy model intercepted at T+60.6 s.
- The run produced a hashed mission manifest and telemetry.

This proves software integration and repeatability in the model. It does not
prove physical interception performance or validate the representative values.
