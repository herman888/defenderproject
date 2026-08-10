# CTO reassessment agenda and internal annex

**Use:** internal working document. It complements the shareable stakeholder
reassessment pack; do not send this file externally without review.

## Meeting outcome required

Leave the CTO review with written owners and dates for:

1. the first sellable product wedge;
2. one target partner system and interface;
3. one camera-plus-compute baseline;
4. the evidence required before any performance statement;
5. the engineering stop list.

## Evidence inventory

| Workstream | Present capability | Missing for product decision |
| --- | --- | --- |
| Core software | 225 local tests, CI, deterministic swarm check, mission records | Release branch/tag policy and externally visible CI run |
| Simulation | PyBullet, profiles, drag/lift/actuator/energy/turbulence model, scenarios | Measured vehicle/sensor parameters and model residual validation |
| Camera/vision | Capture, extraction, labelling, merge, fine-tune, lock-manifest, replay, companion packet | Selected camera, frozen data split, locked model, held-out metrics, edge benchmark |
| Radar/tracking | Synthetic radar, Kalman tracking, association, fusion | Hardware selection, clutter/false-track data, range trial |
| Guidance | APN baseline, terminal variants, replayable synthetic campaign | Calibrated sensor-in-loop comparison, HIL, measured contact geometry |
| Edge platform | Versioned companion packet and smoke benchmark | Production board, service image, timing/thermal/power data, security/update design |
| Vehicle | Reference profile, hardware inventory, SIL/SITL/HIL readiness docs | Selected airframe, propulsion, battery, inertia, avionics, integration evidence |
| Viewer | Local packaged replay, 5 Unreal automation tests, release package/hash | Demonstration procedure and release artifact storage; no further rendering work |
| Documentation | Strict-built site and diligence material | Vercel owner action and public link check |

## Product choices to make

### 1. Product wedge

Choose one:

- **Preferred:** edge perception and evidence-integration pilot for an existing
  aerial/robotics customer.
- Digital-twin and validation service for a sensor/vehicle supplier.
- Full integrated vehicle program.

The first option uses current assets best and requires the least unsupported
claim. Do not sell a full field interceptor product before the measured sensor,
vehicle, safety, and authorization gates exist.

### 2. Authority boundary

Write and approve:

- what the onboard node may perceive, track, record, and report;
- what only a host/operator may authorize;
- what is explicitly unavailable when link, clock, sensor, or compute health
  is degraded;
- whether the first pilot is read-only, advisory, or a bounded simulation/HIL
  workflow.

### 3. Edge-board choice

Retire Nano from new-design consideration. Select Orin Nano 8 GB or Orin NX
16 GB only after a written workload budget covering camera count, image size,
model engine, tracker, log encryption, telemetry rate, memory, power, thermal
margin, and lifecycle.

## First edge proof plan

1. Lock the BOM for one camera, lens, cable, carrier, storage, and power
   arrangement.
2. Define clocks and timestamp ownership at capture, inference, packet
   publish, host receive, and recording.
3. Collect labelled positive and negative recordings under defined conditions.
4. Freeze the dataset split and exact model artifact.
5. Build a TensorRT engine for the chosen board and record p50/p95/p99:
   capture-to-detection, detection-to-track, track-to-packet, packet loss,
   temperature, power, memory, and throttle events.
6. Publish a companion replay report and update the simulation sensor model
   only with measured values.

## UI/product requirements

The command center must distinguish:

- simulated versus measured;
- capture FPS versus inference FPS versus end-to-end track age;
- detector confidence versus fusion confidence;
- fresh versus coasting versus stale tracks;
- normal sensor operation versus injected failure;
- baseline guidance versus experimental guidance;
- local research transport versus qualified partner integration.

Do not create an attractive number if its source, time basis, or test condition
is unknown.

## Supplier due-diligence questions

### Camera and optics

- Sensor data sheet, lens choice, focus, FOV, low-light behavior, exposure
  control, interface, driver support, supply lifecycle, and mechanical mount.
- Are raw frames/timestamps accessible? What is the capture pipeline latency?
- Can recordings be retained and shared under the intended data terms?

### Compute/carrier

- Production-module lifecycle, carrier availability, operating temperature,
  storage endurance, secure boot, update mechanism, camera interfaces, and
  power transients.
- Thermal test method at the intended enclosure, altitude, vibration, and
  power mode.

### Airframe/propulsion

- Mass breakdown, CG/inertia, thrust curves, battery discharge, ESC/motor
  response, vibration, telemetry access, failure behavior, and firmware/API.

### Integration host

- Accepted transport/interface, coordinate frame, timestamps, command
  authority, packet-loss behavior, audit requirements, and test environment.

## Business questions for CEO/CTO

1. Who pays first: sensor vendor, vehicle maker, integrator, site operator, or
   research program?
2. What specific decision does the first paid pilot deliver?
3. What partner data becomes proprietary, and what may be published?
4. What is the minimum field evidence needed before customer-facing claims?
5. Is the product sold as hardware, licensed edge software, integration
   service, or a combined pilot?
6. What support, update, security, and warranty promise can the team actually
   maintain?

## Stop list

- No new residual-RL work unless a calibrated scenario demonstrates APN's
  limitation.
- No new Unreal art/rendering work; preserve package/replay/test quality.
- No field or autonomy claim based on synthetic results.
- No production commitment to Jetson Nano.
- No partner-specific interface without a schema, replay, failure behavior, and
  ownership agreement.

## Immediate owners

| Owner | Next action | Exit artifact |
| --- | --- | --- |
| Founder / business lead | Select the first buyer hypothesis and target partner | One-page pilot problem statement and partner list |
| CTO | Approve edge architecture, board-evaluation plan, and authority boundary | Signed technical decision record |
| Vision lead | Lock camera/data protocol and produce held-out evaluation plan | Dataset/annotation/metric specification |
| Systems lead | Define the host adapter and timing contract | Versioned interface and replay test plan |
| Hardware lead | Build measured airframe and power test plan | BOM and test matrix |
| Documentation/release owner | Restore Vercel, tag baseline, curate data room | Public link and release index |
