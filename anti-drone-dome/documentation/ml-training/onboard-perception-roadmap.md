# Onboard perception roadmap

## Purpose and boundary

This roadmap turns the Raspberry Pi 5 + AI HAT+ 2 into a traceable onboard
perception computer. It detects and tracks visual objects, records evidence,
and publishes timestamped observations for a ground display and replay/simulation
environment.

The Pi is an observation producer. It does not own vehicle stabilization,
arming, failsafes, or real-world target-engagement decisions. Those safety-critical
functions remain outside this perception stack. This document deliberately does
not specify autonomous pursuit, interception, collision, or engagement behaviour.

```text
camera -> detector -> tracker -> observation contract -> recorder / map / simulation replay
                                           |
                                           +-> Pi health and GPS-quality telemetry
```

## Current evidence

| Item | Current state | Interpretation |
| --- | --- | --- |
| Pi runtime | AI HAT+ 2 / Hailo-10H bring-up passed | Hardware is ready for inference benchmarking. |
| Candidate model | `models/yolo11n_drone.pt` | Single-class `drone` baseline; provenance and validation are not yet measured. |
| Existing fine-tune candidate | `models/finetuned/finetune_20260622_200022/weights/best.pt` | Internal validation result: precision 0.958, recall 0.760, mAP@50 0.790, mAP@50-95 0.619. Not a field-performance claim. |
| Existing merged data | 4,476 train and 789 validation images | Three classes: `drone`, `fpv_drone`, `loitering_munition`; source-level split provenance must be reconstructed. |
| Local target camera | Not yet available | No claim can yet be made for the target lens, mount, lighting, or motion conditions. |

## Round 0: reproducible baseline

The first deliverable is not a new model. It is a locked experiment that another
computer can reproduce.

1. Write a dataset manifest listing every source, licence, download version,
   class mapping, image count, checksum, and split rule.
2. Create train, validation, and test splits by source video, scene, recording
   session, or location -- never by random neighbouring frames.
3. Start with one deployed class: `drone`. Keep finer taxonomy only when the
   data supports it and its confusion cost is understood.
4. Establish a fixed test report containing precision, recall, mAP, false-positive
   examples, target-size bins, and per-source results.
5. Evaluate the current models without changing the test set. Select a model only
   after this comparison.

The old fine-tune run is a candidate for comparison; it is not the deployed
baseline until its data and evaluation provenance are captured.

## Data needed

### Detection and tracking data

Collect or license data covering:

- drones at near, medium, and very small image sizes;
- varied shapes, colours, orientations, speeds, and backgrounds;
- clear daylight, low light, backlight, haze, clouds, rain, and IR conditions;
- camera shake, motion blur, compression artefacts, occlusion, and propeller
  vibration;
- short video sequences with stable object identities, for tracker evaluation;
- empty scenes and hard negatives: birds, aircraft, insects, kites, clouds,
  glare, branches, buildings, and reflections.

Public datasets can provide breadth, but target-camera footage is required to
measure deployment performance. Synthetic imagery may add rare weather and scale
conditions, but is augmentation data only and must not be the final test set.

### Navigation-safety and telemetry data

For safe mapping, replay, and supervised mission software, retain:

- synchronized video timestamps;
- Pi GPS location, altitude, speed, fix type, satellite count, HDOP, and UTC
  time source;
- camera calibration and mounting orientation, recorded as measured or
  design-placeholder evidence;
- Pi temperature, voltage/throttling state, CPU/NPU load, frame rate, queue
  depth, inference latency, and dropped-frame count;
- flight-controller telemetry required for replay, with coordinate-frame and
  clock-offset documentation;
- controlled simulator/replay scenarios with known ground truth for scoring.

This data supports detection overlays, georeferenced observations, operator
alerts, health monitoring, and simulation validation. It is not a substitute for
an independent flight controller's safety functions.

## Training and deployment path

1. Train and fine-tune on the training PC, not on the Pi.
2. Keep the smallest detector that satisfies the fixed benchmark; test input
   resolution and crop/tile preprocessing for small objects before simply
   choosing a larger network.
3. Save the chosen weights, training arguments, data manifest, report, and
   SHA-256 checksum together.
4. Compile the selected model with the Hailo x86_64 Linux toolchain into a
   hardware-specific `.hef` artifact, using representative calibration images.
5. On the Pi, measure end-to-end camera-to-observation p50/p95 latency, frame
   rate, temperature, throttling, and dropped frames.
6. Repeat the same test on target-camera recordings before any claim of onboard
   performance.

## Observation contract

Use a versioned `aegis.companion-perception.v1` observation rather than an
ad-hoc dictionary. Every event should include:

- UTC and monotonic timestamp;
- frame identifier and camera identifier;
- model ID, model checksum, model input size, and threshold configuration;
- bounding box, class, confidence, and tracker ID;
- Pi location plus GPS quality fields;
- inference latency, frame age, and system-health fields;
- an explicit `evidence.status` for measured versus placeholder physical values.

## Acceptance gates

| Gate | Required evidence |
| --- | --- |
| Dataset ready | Manifest, licence record, source-level split, and label review sample. |
| Model candidate | Frozen test report with false-positive review and small-target results. |
| Hailo ready | Versioned `.hef`, calibration provenance, and successful Pi benchmark. |
| Camera ready | Repeatable recordings from the actual camera in day and IR modes. |
| Integration ready | Timestamp/coordinate-frame checks, replay output, health telemetry, and no command path from perception to vehicle actuation. |

## Deferred assistant models

Qwen or another small LLM/VLM may later help an operator search logs, summarize
incidents, or review selected snapshots. It is not the real-time detector and
must not compete with the detector for an unmeasured Hailo runtime budget.

## Professional skills for a C-UAS product team

This project is a learning and prototype environment. Any work for an employer
must follow that employer's security, safety, export-control, customer, and
approval processes. Do not copy non-public requirements, source code, data,
test results, architecture, or operational details into this repository.

The useful professional mental model for an onboard autonomy product is:

```text
sense -> estimate -> apply approved mission/safety constraints -> control execution
  ^                                                                  |
  +--------- health monitoring, logging, review, and oversight ------+
```

The main skills to develop are:

| Area | Why it matters in a product team |
| --- | --- |
| Systems engineering | Turns a mission need into requirements, interfaces, test cases, and traceable evidence across hardware and software teams. |
| Flight dynamics and controls | Explains how a vehicle follows safe mission inputs while the flight controller retains stability and failsafe responsibility. |
| State estimation and sensor fusion | Combines imperfect camera, GPS, inertial, and timing data into an estimate with known uncertainty. |
| Perception ML | Covers data quality, labels, false positives, model evaluation, edge deployment, and model-drift monitoring. |
| Real-time embedded engineering | Covers latency budgets, clock alignment, watchdogs, power, heat, communications, and graceful degradation. |
| Safety and assurance | Covers hazard analysis, independent abort paths, geofencing, return-to-home behaviour, test gates, and evidence-based claims. |
| Simulation and replay | Enables software-in-the-loop, hardware-in-the-loop, and recorded-data testing before controlled field work. |
| Human factors | Ensures alerts, confidence, uncertainty, and system state are understandable to an operator under time pressure. |
| Security and configuration control | Protects access, software supply chain, secrets, model provenance, data lineage, and change history. |

For this repository, the best near-term learning sequence is:

1. Vision-model evaluation and Hailo deployment.
2. GPS/telemetry, coordinate frames, and clock alignment.
3. Flight-controller interface boundaries and safety monitoring.
4. Simulation and replay-based verification.
5. Requirements writing, test reporting, and calibrated technical claims.

The goal is not to write every component personally. It is to understand the
whole loop well enough to state what was observed, what the system estimates,
how certain it is, which safety constraints apply, and what test evidence
supports a claim.

## Hardware map for the supervised onboard loop

This is a practical mapping from the system loop to the equipment already
available or worth considering. It is intentionally a perception, telemetry,
and vehicle-safety stack; it is not an autonomous engagement design.

| Loop layer | Use now | Sensible next hardware | What must be demonstrated |
| --- | --- | --- | --- |
| Mission boundary and operator view | A laptop ground display and written test cards | Ground-control software on a dedicated laptop; a reliable manual control/abort capability chosen for the approved airframe | The operator can see state, stop a test, and recover from a lost link. |
| Sense | Raspberry Pi 5, AI HAT+ 2, future InnoMaker UVC camera, existing M8N GNSS | Camera mount with repeatable orientation; vibration isolation; an approved flight controller with its own IMU/barometer/compass | Camera framing, GPS quality, and sensor timestamps are recorded. |
| Time and coordinates | Pi clock plus GPS data logs | GNSS time pulse/UTC discipline and documented camera-to-body-to-world coordinate frames | A replay gives the same position and timing interpretation as the live run. |
| Perception | Hailo-10H and the YOLO candidate model | No more AI hardware is needed now; first deploy a measured Hailo `.hef` model | p50/p95 latency, false positives, missed detections, thermals, and model provenance. |
| Estimate and validation | Software tracker and `aegis.companion-perception.v1` observation contract | No purchase required initially | Tracks remain stable only when evidence persists; uncertainty is retained. |
| Safety gates | Pi health checks and logged GPS quality | Flight-controller battery/power monitoring, independent manual abort path, and a quality power module matched to the airframe | Weak GPS, thermal/power events, or lost camera cause a known safe state. |
| Flight execution | Keep separate from the Pi | If an approved airframe needs a controller, a Pixhawk 6C-class flight controller and matched power module are a good value baseline | The flight controller, not the Pi, enforces stability, limits, geofence, and return-home behaviour. |
| Monitoring and evidence | Pi logs, Hailo/Pi health, SSD or microSD storage | Active cooling and a 128--256 GB high-endurance microSD for extended video/log capture | Every test is replayable with versioned software, model, and configuration. |

### What the current equipment is good for

- **Raspberry Pi 5 + AI HAT+ 2:** enough edge compute for the detector, tracker,
  health reporting, and recording. Do not add another accelerator before measuring
  the Hailo deployment.
- **64 GB microSD:** sufficient for Raspberry Pi OS, models, software, and short
  recording sessions. For repeated video collection, use a reputable 128--256 GB
  high-endurance card and move completed sessions to the training PC.
- **M8N GNSS:** useful now for timestamped position, basic outdoor navigation
  experiments, and learning the telemetry interfaces. Treat its position as an
  estimate, not precision truth.
- **Apple USB-C power brick:** acceptable for bench setup only if the Pi reports
  no undervoltage/throttling. Its headline wattage does not by itself prove it
  provides the Pi's required 5 V / 5 A power profile.

### Best-value purchase sequence

1. **Camera and mount first.** The planned UVC camera and a rigid, repeatable,
   vibration-aware mount unlock the only data that can validate the actual vision
   product. Collect day, low-light, and IR-Cut recordings before changing models
   repeatedly.
2. **Reliable Pi power and cooling.** For bench work, use Raspberry Pi's 27 W
   supply. For an onboard build, use a professionally specified, regulated power
   solution that can provide the Pi's 5 V / 5 A requirement under load; verify it
   with Pi throttling logs. Never connect a Pi directly to a flight battery.
3. **Flight-controller foundation, only if not already supplied with the
   airframe.** A Pixhawk 6C-class controller is a reasonable value option because
   it is a supported autopilot class with redundant IMUs and mature PX4/ArduPilot
   tooling. Purchase the controller with a correctly matched power module rather
   than treating the Pi as a replacement.
4. **Keep the M8N for learning; upgrade GNSS only when measurement shows the
   need.** Standard M8N-generation GPS is commonly a few metres accurate. If the
   product needs repeatable, high-accuracy positioning, use a genuine u-blox
   F9P-based multi-band RTK rover and an approved correction source. This is a
   positioning upgrade, not a replacement for safety logic.
5. **Do not buy yet:** another AI accelerator, a large language model setup,
   radar, SDR/RF equipment, or a custom carrier board. None closes the current
   evidence gap as effectively as target-camera data, a reproducible benchmark,
   and reliable power/telemetry.

### Integration principles

- The Pi publishes observations and health; the flight controller retains the
  authority for stabilization, geofence, return-home, and failsafes.
- Power, clock alignment, coordinate frames, and camera mounting are product
  requirements, not installation details. Record their evidence status.
- Add one new component at a time and run a repeatable bench/replay test before
  combining it with the rest of the system.
- Select components against the employer's approved parts, security, export,
  airworthiness, and test processes when work crosses into a company product.

## Reliability and safety assurance

Reliable autonomy is not created by one accurate model. It is a chain of checks
that makes uncertainty visible and chooses a safe degraded state when evidence
is missing.

1. **Validate, do not trust a single input.** Require persistent observations,
   tracker consistency, and known sensor health before presenting a detection as
   high confidence. Preserve an explicit `unknown` state.
2. **Budget timing end to end.** Measure camera exposure, frame transport,
   inference, tracking, telemetry, and display delay. Report the age of every
   observation, not only the inference duration.
3. **Treat component health as data.** GPS fix quality, camera disconnects,
   storage errors, temperature, voltage, throttling, battery, and link status
   must be available to the operator and recorded alongside detections.
4. **Use independent safety ownership.** The Pi can fail without removing the
   flight controller's stabilization, geofence, return-home, manual override,
   and safe-recovery functions.
5. **Define safe degradation in advance.** For each failure condition, specify
   the visible alert, the retained evidence, the operator response, and the
   vehicle-safe state. Test the failure path as deliberately as the nominal path.
6. **Test from cheap to expensive.** Run unit tests, recorded-data replay,
   software-in-the-loop, hardware-in-the-loop, bench testing, and controlled
   flight tests in that order. A simulation result is not a field-performance
   claim.
7. **Make every result traceable.** Preserve the software revision, firmware
   revision, model hash, data manifest, configuration, environment, operator
   actions, and outcome. Regression-test every material change.
8. **Use explicit release gates.** A feature does not move from prototype to
   product because it looks good in a demo. It moves only when its predefined
   accuracy, latency, availability, failure-handling, and review evidence gates
   are satisfied.
