# Parameter register and evidence status

This register separates a sound software implementation from values that have
been measured on the intended hardware. A parameter is never promoted merely
because it makes a synthetic campaign pass.

## Status vocabulary

| Status | Meaning | Permitted claim |
| --- | --- | --- |
| `measured` | Measured against a recorded method, instrument, date, and artifact | The measurement and its stated bounds |
| `representative-unvalidated` | Drawn from public dimensions or a generic vehicle class | Scenario exploration only |
| `design-placeholder` | Internal engineering assumption pending selection or test | No hardware or field-performance claim |

## Vehicle dynamics

The versioned source is
`scenario_data/airframe_profiles_v1.json`; the loader rejects unknown evidence
statuses at runtime.

| Item | Current value / source | Status | Evidence needed to promote it |
| --- | --- | --- | --- |
| Interceptor mass | 1.5 kg reference profile | `design-placeholder` | Itemised weighed mass budget, including seeker, compute, battery, wiring, and airframe |
| Interceptor inertia | `[0.045, 0.045, 0.080] kg m²` | `design-placeholder` | CAD mass properties or pendulum / torsional test |
| Interceptor propulsion, lag, and force slew | 260 N maximum horizontal force; 0.06 s lag | `design-placeholder` | Thrust-stand and commanded-step tests with selected motors, props, ESCs, and battery |
| Interceptor energy | 180 Wh | `design-placeholder` | Battery discharge data at representative propulsion and avionics loads |
| Shahed-like threat | Public dimensions plus representative envelope | `representative-unvalidated` | Approved flight-log comparison or verified manufacturer data |
| Consumer-quad and FPV threats | Generic class profiles | `representative-unvalidated` | Exact airframe datasets and flight-log calibration |
| Turbulence | Per-profile force standard deviation | `design-placeholder` / `representative-unvalidated` | Weather/flight log fit or a stated Dryden-model configuration |
| Contact radius | 1.0 m | `design-placeholder` | Geometric contact model derived from selected vehicle envelopes and a documented safety margin |

## Sensors and estimation

| Item | Current value / source | Status | Evidence needed to promote it |
| --- | --- | --- | --- |
| Radar equation and Swerling probability model | Standard closed-form model in `sensors/radar_model.py` | Model verified; budget unvalidated | Selected front-end data sheet and controlled range measurements |
| Radar budget | 100 W, 30 dBi, 9.4 GHz, 4 dB NF, 5 MHz BW, 20 pulses | `design-placeholder` | Selected hardware, antenna pattern, receiver noise, waveform, and field detection trials |
| Radar tracking | One-target 9-state Kalman tracker | Implemented; not sufficient for swarm evidence | Multi-target measurements, association tests, clutter and false-track characterization |
| EO rendered-camera observation | PyBullet rendering with configured noise/latency | Synthetic only | Camera recording replay and controlled target-range evaluation |
| Vision model | Candidate manifest only; no checksum-locked selected model | Not validated | Frozen dataset split, held-out results, false-positive study, exact model hash, and target-device latency |
| Perception crop mode | Synthetic host comparison: full-frame resize never reached 50% at 64 px; centre crop and native tiles first reached 50% at 24 px in `artifacts/vision/pixel_floor_20260811T151545Z.json` | `measured` (synthetic, host-only) | Off-centre and recorded-camera comparison before selecting a live mode; preprocessing result is not a field detection claim |
| Perception crop size / centre / tile overlap | Test values: 640 px centre crop, centre `(0.5, 0.5)`, tile overlap 0.2; no deployment selection | `measured` (synthetic, host-only) | The current generator centres each synthetic target, so it cannot justify a coverage choice; evaluate marked/off-centre recordings first |
| Camera crop / tile configuration | `NOT MEASURED` / not selected | `design-placeholder` | Record exact native-resolution crop/tile, resize, camera mode, and target-pixel method with each camera artifact |
| Acoustic seeker | Not implemented | Not validated | Bench, hover, and forward-flight SNR/bearing experiment |

## Guidance, compute, and communications

| Item | Current value / source | Status | Evidence needed to promote it |
| --- | --- | --- | --- |
| APN guidance | Deterministic software implementation with regression cases | Software-verified only | Sensor-in-loop Monte Carlo followed by HIL and controlled flight data |
| Terminal guidance variants | PD default; ZEM and auto selectable | Experimental | Pre-registered comparison using calibrated sensing and contact geometry |
| Residual PPO policy | Does not outperform APN in archived synthetic comparisons | Deferred | A measured scenario class where APN demonstrably underperforms |
| Edge compute | Raspberry Pi 5 + Hailo-8/8L AI HAT+ measurement platform; capture-to-detection, detection-to-track, FPS, NPU, temperature, and power are `NOT MEASURED` | `design-placeholder` | Versioned target-device camera and pipeline artifact |
| Alternatives | Orin Nano 8 GB / Orin NX 16 GB | `design-placeholder` | Re-evaluate only if the Pi/Hailo first evidence gate fails p95 end-to-end latency, sustained thermals, or power |
| RF link | Range-only simulation model | `design-placeholder` | Frequency plan, antenna patterns, receiver sensitivity, and loss-of-link tests |
| Command transport | Local research UDP / SITL interfaces | Not production-capable | Authenticated, replay-protected command design and HIL qualification |

## Rules for evidence changes

1. Keep the raw measurement or flight-log artifact with its hash.
2. Record the method, hardware configuration, uncertainty, and operator.
3. Update the versioned profile and this register in the same change.
4. Re-run the regression campaign; do not assume a better parameter improves
   system performance.
5. Publish the delta, including regressions.
