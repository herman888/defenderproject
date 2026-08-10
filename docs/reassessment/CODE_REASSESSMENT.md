# Code reassessment: brain-direction reconciliation

Scope: code, configuration, executable scripts, generated model metadata, and
tests were inspected. Existing Markdown documentation was not edited or used as
evidence for a capability. This report classifies the checked-out code against
the current product direction: an effector-agnostic perception, tracking,
RF-to-CV handoff, and evidence/replay companion layer.

Status labels used below:

- **CORE**: directly useful to the product's perception, track, cue/handoff,
  assignment, or evidence/replay boundary.
- **SUPPORTING**: earns its place as a harness, simulator, adapter, or
  presentation/testing tool, but is not product core.
- **ORPHAN / MISALIGNED**: coupled to the retired whole-interceptor/kinetic
  product. It is retained; the recommendation is a future disposition, not an
  instruction to delete it.

## 1. Architecture-vs-direction map

| Area / modules | Status | What it does and recommendation |
| --- | --- | --- |
| `anti-drone-dome/integration/companion_link.py` | CORE | Defines and validates `aegis.companion-perception.v1` packets containing timestamped image dimensions and bounding boxes. This is the closest existing Pi-to-consumer boundary; keep and extend later with an explicit track/cue contract. |
| `anti-drone-dome/integration/vision_model.py` | CORE | Validates/checksum-locks an object-detector manifest and selects a PyTorch CPU/CUDA device. Preserve its artifact-provenance design; refactor the runtime/backend enum for Hailo rather than treating Ultralytics/PyTorch as the deployed interface. |
| `anti-drone-dome/integration/vision_replay.py` and `scripts/replay_camera_recording.py` | CORE | Run a locked Ultralytics model over recorded images/video and emit deterministic perception JSONL plus input/output hashes. Keep as the evidence replay seam; add a Hailo replay implementation beside it later. |
| `anti-drone-dome/scripts/capture_session.py`, `extract_frames.py`, `auto_label.py`, `merge_datasets.py`, `filter_annotations.py`, `fetch_public_datasets.py`, `convert_*.py`, and `finetune.py` | CORE | Collect, prepare, label, merge, and train camera data. The workflow serves the perception brain; retain it, while separating desktop training from the eventual `.hef` deployment/export workflow. |
| `anti-drone-dome/scripts/camera_detect.py` | SUPPORTING | Opens the InnoMaker UVC camera and overlays desktop YOLO detections. Useful capture/inference smoke harness, but it emits no perception packet or track; refactor later into a reusable source/adapter, not a product runtime. |
| `anti-drone-dome/scripts/track_and_navigate.py` | CORE, incomplete | The only live-camera multi-object path: UVC frame -> Ultralytics YOLO -> Supervision ByteTrack -> IDs/centroids/px-frame velocity. Its own TODO states the guidance handoff is absent; keep and make it the initial live tracking seam. |
| `anti-drone-dome/guidance/passive_optical.py` | CORE, dormant | Converts a monocular bounding box to an ENU alpha-beta track with explicitly placeholder intrinsics/target width. It already returns the track shape expected by fusion but has no live caller; retain and wire only after camera calibration/range policy is decided. |
| `anti-drone-dome/sensors/fusion.py` | CORE | Time-aligns, gates, and confidence-weights radar and EO 3-D tracks. The algorithm is reusable, but its current callers provide synthetic radar/rendered EO; retain and feed it a real tracker contract later. |
| `anti-drone-dome/sensors/radar.py`, `radar_batch.py`, and `radar_model.py` | SUPPORTING | Synthetic one-target/multi-target radar measurements and tracking for sensor-in-loop experiments. They exercise fusion/assignment interfaces, but are not RF direction finding or a physical sensor integration; keep as test harness and label as synthetic in future code work. |
| `anti-drone-dome/guidance/intercept.py` and `guidance/setpoint.py` | CORE | APN/terminal guidance and frame-safe setpoints consume a generic `position_estimate`/velocity track. Keep as the downstream handoff consumer; it should remain vehicle/effector neutral at its public boundary. |
| `anti-drone-dome/comms/datalink.py` | CORE seam, incomplete | Serializes a 3-D track into `GLOBAL_POSITION_INT`, but currently uses localhost UDP, fixed latitude/longitude, and a simulated coordinate conversion. Retain as a prototype seam; refactor later to a real UART/MAVLink companion transport and explicit coordinate origin. |
| `anti-drone-dome/comms/sitl_bridge.py` | SUPPORTING | Sends setpoints to ArduPilot SITL over UDP and reads simulated vehicle state. Useful regression adapter, not a physical Pi-to-Mamba integration; keep for test only. |
| `anti-drone-dome/swarm/assignment.py`, `coordinator.py`, `scenario.py`, `telemetry.py`, and `runner.py` | CORE | Anonymous-track prioritization/assignment and its replayable scenario harness. This maps to multi-target prioritization/assignment, provided it remains cue/asset assignment rather than swarm-kill behavior; keep. |
| `anti-drone-dome/swarm/rf_link.py` | SUPPORTING | Models RF link quality/loss for synthetic resilience testing. It is not RF direction finding and has no physical RF input; keep as a simulation harness, then decide whether to refactor it into an explicit RF-cue simulator. |
| `anti-drone-dome/swarm/cpk_optimizer.py` | ORPHAN / MISALIGNED | Cost-per-kill optimization assumes the retired effector economics. Retire-later from the product runtime; retain history and tests until a new, cue/assignment-relevant objective is defined. |
| `anti-drone-dome/integration/mission_record.py`, `tactical_stream.py`, `local_sim_control.py`, `unreal_bridge.py`, and `tactical_udp_multi_effector.py` | SUPPORTING | Versioned simulation/presentation records and UDP bridges. Mission recording and schema validation reinforce the evidence layer; the tactical schema itself is interceptor-centric and should be refactored later into brain/track/cue records. |
| `anti-drone-dome/hardware/profile.py`, `hardware_profiles/*.json`, and `validation/{workbench,flight_log,model_calibration,failure_analysis}.py` | CORE | Parameter/evidence-status validation, run gates, and log alignment are directly aligned with the evidence differentiator. Preserve; replace current interceptor performance gates with perception/track/cue gates in a later change. |
| `anti-drone-dome/main.py` | SUPPORTING | Monolithic PyBullet mission runner that demonstrates a synthetic radar/EO->guidance loop. It is a valuable integration harness, but is not the deployable brain; retain and progressively consume the same packet contracts as real integrations. |
| `anti-drone-dome/sim/{physics,terrain,geospatial,seeding,waypoints,camera_debug_ui}.py` | SUPPORTING | Deterministic world/rendering/environment support for reproducible sensor and cue experiments. Keep as a harness. |
| `anti-drone-dome/sim/{drone,airframe_profiles,flight_envelope,collision}.py`, `scenarios.py`, and `scenario_data/airframe_profiles_v1.json` | ORPHAN / MISALIGNED | Encode a specific interceptor/intruder and airframe dynamics. Keep the generic envelope/contact utilities if useful, but refactor-later toward third-party-platform profiles rather than product-owned airframes. |
| `anti-drone-dome/sim/rocket_effector.py` and `scenarios_multi_effector.py` | ORPHAN / MISALIGNED | Explicit rocket/multi-effector modeling conflicts with the new effector-agnostic brain. Retire-later; do not extend. |
| `anti-drone-dome/dome/killzone.py` | ORPHAN / MISALIGNED | Models a protected-dome intercept outcome, not a portable cue/track product. Retire-later or replace with generic geofence/decision status. |
| `anti-drone-dome/ml/{policy,controllers,environment,observation,scenario_curriculum,stress_scenarios}.py` and `scripts/train_interceptor.py`, `benchmark_controllers.py`, `generate_training_dataset.py`, `diagnose_guidance_failure.py` | ORPHAN / MISALIGNED | PPO/APN-interceptor research assumes ownership of the effector/controller. Retain for reproducibility; do not make it a product dependency. The APN setpoint interface itself remains CORE. |
| `anti-drone-dome/viz/{dashboard,vispy_renderer,dashboard_matplotlib_legacy,trails,acmi_writer}.py` | SUPPORTING | Command-center and replay visualization help demonstrate/review evidence, but UI language and ACMI events are interceptor-centric. Keep the viewer/replay utility; refactor-later labels and data model. |
| `anti-drone-dome/scripts/{run_regression_campaign,run_hardware_validation,run_companion_smoke,check_determinism,measure_perf_baseline,record_swarm_replay,replay_swarm_stream,replay_tactical_stream}.py` | SUPPORTING | Reproducibility, contract, and performance harnesses. Retain; change their target metrics only in a later, scoped evidence-gate redesign. |
| `anti-drone-dome/scripts/{download_osm_map,download_elevation_map,render_command_center_preview,verify_ui_sequence,validate_unreal_motion_recording,launch_*,package_unreal_release,test_unreal_viewer,stop_unreal_demo}.py` | SUPPORTING | Simulation/viewer tooling. It earns a place only as a local demo/replay harness; do not expand it ahead of the live perception path. |
| `anti-drone-dome/scripts/betaflight_*`, `setup_*`, `flash_*`, `recover_*`, `restore_*`, `watch_*`, `wait_for_fc.sh`, and `betaflight_fc*.env` | ORPHAN / MISALIGNED | Specific Omnibus/Fury Betaflight recovery, Spektrum, and motor tooling. The target is a Mamba F405-class FC with the Pi as companion; retain for historical lab recoverability, retire-later from product workflows. |
| `anti-drone-dome/tests/` | SUPPORTING | Unit/integration coverage protects the simulation, contracts, profiles, and evidence harnesses. Keep; add real-camera/Hailo contract/replay tests in a later change. |
| `anti-drone-dome/assets/` | ORPHAN / MISALIGNED | Interceptor, Shahed, and tactical-scene models are presentation/simulation assets from the old product. Retain untouched; avoid adding new effector assets. |
| `gym-pybullet-drones/gym_pybullet_drones/defender/` | ORPHAN / MISALIGNED | A parallel defender/interceptor simulation stack. Retire-later or archive outside the active dependency path. |
| Other `gym-pybullet-drones` environments/controllers/assets/examples | SUPPORTING, uncertain | Third-party simulation substrate and examples. It may still support local experimentation, but current product value is indirect; retain unless dependency analysis proves it unused. |
| `unreal/AegisTacticalViewer/` | SUPPORTING, frozen | Receive-only tactical presentation and automation. Its AEGIS/interceptor terminology is stale but it may still show tracks/replay; keep frozen and refactor-later only if presentation is needed. |
| Root/configuration files (`config.py`, `pyproject.toml`, requirements, runners) | SUPPORTING | Runtime setup and named simulation constants. Keep, but split brain-runtime configuration from simulator/airframe values in a future change. |

## 2. Hardware-assumption audit

### Direct search result

Searches were run across non-Markdown code/configuration for `coral`,
`edgetpu`, `jetson`, `tensorrt`, `tensor_rt`, `hailo`, `hailort`, `dataflow`,
`.hef`, `onnx`, `tflite`, `cuda`, and `torchscript`.

- No Coral, EdgeTPU, Jetson, TensorRT, ONNX, or TFLite implementation was
  found.
- No HailoRT or Hailo Dataflow Compiler implementation was found.
- Hailo appears only in training-script comments/docstrings, not as a runtime
  backend or export step.
- There is no `.hef` artifact, loader, scheduler, preprocessing adapter, or
  Hailo detection decoder in the active code.

### Non-Pi/Hailo compute and export assumptions

| File:line | Finding |
| --- | --- |
| `anti-drone-dome/integration/vision_model.py:14,90,186-201` | The manifest and resolver permit only `auto`, `cpu`, and `cuda`; `auto` probes PyTorch CUDA and returns CUDA device `0`. This excludes a Hailo backend. |
| `anti-drone-dome/main.py:675,2331,2439-2446` | Rendered-camera inference is passed CUDA device `0`; CLI offers only CPU/CUDA and validates PyTorch CUDA. This is desktop simulation compute, not Pi/Hailo inference. |
| `anti-drone-dome/scripts/camera_detect.py:216-217,257,298-325` | Live UVC detector selects CPU/CUDA through the PyTorch resolver and calls Ultralytics directly. No Hailo adapter or packet output exists. |
| `anti-drone-dome/scripts/track_and_navigate.py:258` | Live tracker hardcodes `model.predict(..., device=0)`, requiring a visible CUDA GPU instead of an accelerator-neutral/Hailo path. |
| `anti-drone-dome/scripts/auto_label.py:129-130` | Defaults annotation inference to device `0` (GPU). This is development tooling, but it hardcodes the desktop assumption. |
| `anti-drone-dome/scripts/finetune.py:5-7,25,55,59-60` | Comments assert Pi/Hailo-8L throughput and `.hef` availability, but the implementation trains/validates via Ultralytics with GPU device `0`; it contains no Hailo export. The throughput values have no in-repo benchmark/provenance. |
| `anti-drone-dome/scripts/replay_camera_recording.py:102,115-116,141,167` | Locked replay uses the same CPU/CUDA PyTorch/Ultralytics path and reports `cuda:0`; it cannot replay a deployed Hailo artifact. |
| `anti-drone-dome/scripts/train_interceptor.py:94-97,192,225` | PPO training accepts CPU/CUDA PyTorch only. This is old interceptor research rather than the Pi inference pipeline. |
| `anti-drone-dome/models/finetuned/*/args.yaml:65` | Seven checked-in fine-tuning metadata files name `format: torchscript`; no `.hef` deployment artifact is recorded. |

### Board/link assumptions that conflict with the confirmed architecture

| File:line | Finding |
| --- | --- |
| `anti-drone-dome/hardware_profiles/raspberry_pi5_companion.json:5-10,19-24,35-41` | The Pi profile is `telemetry-only`, chooses `udp` to `127.0.0.1:49100`, and sets `accelerator_hat` to `not-selected`. It does not declare Hailo, UART, or MAVLink. |
| `anti-drone-dome/comms/datalink.py:1-17,31-46,53-112` | Uses local UDP MAVLink and fixed pseudo-geodetic origin constants. It has no serial/UART device configuration, baud rate, heartbeat, or Pi companion identity. |
| `anti-drone-dome/comms/sitl_bridge.py` | Is an ArduPilot SITL/UDP bridge. It is not a Mamba F405 companion integration. |
| `anti-drone-dome/hardware_profiles/larp_betaflight_readonly.json:5-10` | Hardcodes legacy Betaflight/MSP targets `OMNIBUSF4`, `OMNIBUSF4SD`, and `FURYF4OSD`; it is retained lab history, not the confirmed flight-brain architecture. |
| `anti-drone-dome/scripts/betaflight_*.sh`, `setup_omnibus_f4.sh`, `setup_fury_f4.sh`, `recover_fc.sh`, `restore_*`, `watch_and_flash_omnibus.sh`, and related `*.env` files | Hardcode Omnibus/Fury boards, Betaflight firmware, Spektrum setup, and motor/DFU workflows. These are not portable companion-brain code. |

## 3. Critical-path gap for this sprint

Sprint question: **can perception hold a lock on a small moving drone and feed
guidance a good real-world track?**

### What runs today

1. **Desktop live detection and 2-D tracking exists, as an isolated script.**
   `scripts/track_and_navigate.py:39-169` opens the InnoMaker UVC camera,
   reads frames on a background thread, and loads Ultralytics YOLO at
   `:222-224`. The loop at `:248-289` resizes frames, performs detection,
   constructs `supervision.Detections`, and updates `sv.ByteTrack`.
   `_TrackState` at `:96-128` keeps 10-frame centroid history and reports
   pixel-per-frame velocity/age.

2. **A generic 3-D passive-optical track estimator exists.**
   `guidance/passive_optical.py:95-134`,
   `PassiveOpticalTracker.update_from_bbox`, converts a bbox plus calibrated
   pose into ENU position/velocity. `track()` at `:136-165` returns a
   `position_estimate`, `velocity`, timestamp, confidence, and range
   uncertainty in a shape fusion accepts.

3. **The simulation path exercises 3-D EO/radar fusion and guidance.**
   `main.py:659-686` creates `RenderedCameraSensor`; `main.py:981-1025`
   scans synthetic radar, renders an EO image, invokes
   `RenderedCameraSensor.observe` (`sensors/camera.py:65-205`), and passes
   the result to `TrackFusion.update` (`sensors/fusion.py:108-203`). The
   resulting `guidance_track` is consumed by
   `PurePursuitGuidance.compute_guidance` at `main.py:1039-1059`.

4. **There is a record/replay evidence seam.**
   `scripts/replay_camera_recording.py:112-160` verifies a model artifact,
   performs deterministic inference on recorded media, and emits
   `aegis.companion-perception.v1` through
   `integration/vision_replay.py:8-41` and
   `integration/companion_link.py:12-61`. It correctly states the rate is
   host replay rather than Pi/field performance.

5. **There is a prototype generic guidance transport.**
   `comms/datalink.py:53-85`, `DataLink.send_track`, accepts the same
   position/velocity track shape and emits MAVLink `GLOBAL_POSITION_INT`.

### What is synthetic, stubbed, or only simulated

- The `main.py` mission loop receives simulated target truth through
  `RadarNode.scan(true_pos)` (`sensors/radar.py:273`) and rendered EO uses a
  PyBullet target body plus rendered RGB/depth/segmentation. It is not a live
  camera/real radar loop.
- `RenderedCameraSensor` can run YOLO, but selects the single highest-
  confidence box (`sensors/camera.py:141-158`) and unprojects it using the
  simulator depth buffer (`:160-198`). That is not real target association or
  real-world range estimation.
- `PassiveOpticalTracker` is unused by the live UVC tracker. Its focal length,
  principal point, reference target width, and uncertainty are nominal
  defaults, explicitly design placeholders.
- `TrackFusion` is exercised only with synthetic radar/rendered-camera tracks
  by `main.py`; no live perception packet is decoded into it.
- The camera replay path creates **detection** packets only. It has no
  ByteTrack state, no 3-D estimator, no fusion invocation, and no MAVLink
  output.
- `DataLink` is only called from the simulation loop at `main.py:1198`, which
  sends `radar_return`, not the fused EO/radar `guidance_track`.
- `track_and_navigate.py` marks a track stable after eight frames and prints
  `ready for guidance handoff`, but only displays/logs it. Its module TODO
  (`:18-28`) explicitly lists all missing steps.

### Missing for a real Pi 5 + Hailo lock-to-cue pipeline

1. A HailoRT camera-inference adapter that loads a versioned `.hef`, owns the
   Pi camera preprocessing/postprocessing, produces class/confidence/bbox, and
   records Hailo/runtime/model identity. None exists.
2. A Hailo Dataflow Compiler export/quantization pipeline that turns a selected
   trained detector into the exact deployable `.hef`, with model/dataset/export
   provenance and checksum. None exists.
3. A reusable, timestamped **live track contract**: detection packet ->
   tracker ID/lifecycle -> pixel covariance -> calibrated bearing/elevation ->
   optional monocular/radar range -> 3-D ENU track covariance. The present
   companion schema stops at boxes.
4. Camera intrinsics/extrinsics calibration, timestamp discipline, and a
   coordinate transform between Pi camera, vehicle attitude, ground cue, and
   MAVLink frames. The present camera code assumes either simulator matrices or
   an unimplemented conversion.
5. Real RF direction-finding ingestion and the RF-to-CV handoff: cue bearing,
   uncertainty, target-selection policy, camera slew/ROI, and loss/reacquire
   behavior. No RF-DF input, cue message, or handoff state machine exists.
6. Real sensor association and multi-target selection. ByteTrack has 2-D
   image IDs, while fusion expects one 3-D EO candidate and simulation already
   knows the target; no cross-sensor association policy exists.
7. UART MAVLink companion transport to the Mamba F405-class FC: serial
   configuration, heartbeat, time synchronization, message contract, health,
   link loss, and acknowledgement handling are absent. Existing link code is
   localhost UDP/SITL.
8. A held-out real-camera lock-quality campaign: ID switches, track survival,
   reacquisition, false tracks, bearing/range error, end-to-end age/latency,
   and conditions (target size, range, motion, lighting, EW) are not measured
   in code artifacts.

### Specific integration seams for the future Hailo detector

These are seams to use later, not changes made in this pass.

1. **Detector boundary:** implement a Hailo-backed sibling to the call site in
   `scripts/track_and_navigate.py:258`, returning an adapter-neutral list of
   boxes/classes/confidences. The desired reusable wire shape already exists in
   `integration.companion_link.build_perception_packet`.
2. **Tracking boundary:** keep `sv.ByteTrack` (or substitute an equivalent)
   behind the `tracked` result at `track_and_navigate.py:275`; create a
   versioned track/cue packet rather than passing console tuples.
3. **3-D estimation boundary:** call
   `PassiveOpticalTracker.update_from_bbox` for each selected track with real
   calibrated pose, then call `track()`; alternatively define a range-bearing
   cue contract when radar/RF provides range.
4. **Fusion boundary:** pass the resulting EO track plus a real range/radar
   cue to `TrackFusion.update`, replacing the synthetic arguments in
   `main.py:1017-1023`.
5. **Guidance handoff boundary:** pass the selected fused track to the existing
   `PurePursuitGuidance.compute_guidance` consumer (`main.py:1054-1055`) and
   serialize the desired setpoint/track through a new UART MAVLink companion
   adapter, rather than the current fixed-origin UDP `DataLink`.
6. **Evidence boundary:** reuse the locking/reporting ideas in
   `vision_model.py` and `replay_camera_recording.py`, but record Hailo
   `.hef` hash, compiler/runtime versions, Pi thermal state, camera frame
   timestamps, tracker results, and final cue packets.

## 4. Claims / evidence hygiene (code only)

The following are code comments, docstrings, logs, test names, UI labels, or
configuration values that present a synthetic result as confirmed/operational,
or attach an untraceable performance claim to a hardcoded value. This section
does not flag code that clearly scopes itself as simulation or placeholder.

| File:line | Wording / value | Why it needs review |
| --- | --- | --- |
| `anti-drone-dome/scripts/finetune.py:5` | `proof of concept, 78.8% mAP50` | No run ID, dataset fingerprint, split, threshold, or held-out scope accompanies the number. |
| `anti-drone-dome/scripts/finetune.py:5-7` | `Pi 5 + Hailo-8L (13 TOPS)`, `runs ~50-70 FPS`, `~25 FPS for yolo11s`, and `At 200+ km/h ... FPS > size` | Hardcoded external-performance/product-selection claims; no target-device benchmark or source is in code. |
| `anti-drone-dome/scripts/track_and_navigate.py:14-15` | `Kalman + IoU matching ... is more robust for fast drones` | Unmeasured comparative claim in a live-path module. |
| `anti-drone-dome/scripts/track_and_navigate.py:51` | `tracks older than this are stable enough for guidance handoff` | Eight frames is an uncalibrated stability threshold. |
| `anti-drone-dome/scripts/track_and_navigate.py:301` | `[STABLE — ready for guidance handoff]` | UI/log label says ready although no handoff exists and no real-world lock criterion is measured. |
| `anti-drone-dome/main.py:993,996,1032,1147` | `Radar track acquired`, `Radar track locked`, `Radar/EO fusion confirmed`, `Intercept confirmed` | These state labels are emitted by the synthetic PyBullet mission loop without an on-screen/source qualifier. They can read as live confirmation in logs/UI capture. |
| `anti-drone-dome/viz/dashboard.py:1513` | `Intercept confirmed` | Presentation label inherits a simulated outcome without displaying its synthetic source at the label. |
| `anti-drone-dome/viz/acmi_writer.py:113` | `Radar Lock - Track Acquired` | Replay event can look like sensor evidence although it comes from the synthetic mission loop. |
| `anti-drone-dome/scripts/render_command_center_preview.py:69,90` | `Radar track confirmed`, `EO correlation established`, `Radar track acquired` | Hardcoded preview events are rendered as operational status without a synthetic/preview marker. |
| `anti-drone-dome/guidance/intercept.py:53` | `_V_INT = 68.0  # nominal intercept speed (below 70 m/s hard cap)` | Product-specific performance/limit value without a linked measured profile in code. |
| `anti-drone-dome/scenarios.py:65-80,93-114` | Named threat weights, cruise speeds, RCS/lift/drag values and descriptions | Values make specific performance/classification assertions but are not connected to a traceable artifact; they are scenario parameters, not measured inputs. |
| `anti-drone-dome/sensors/radar.py:319` | `Shahed-136 ≈ 0.05` RCS | Specific target RCS presented in executable sensing code without a traceable measurement source. |
| `anti-drone-dome/sensors/radar_model.py:160` | `representative small X-band surveillance set` defaults | Hardware-like radar budget can be mistaken for a selected/measured sensor unless every output carries its placeholder status. |
| `anti-drone-dome/hardware_profiles/{reference_sil,ardupilot_sitl,larp_betaflight_readonly,raspberry_pi5_companion}.json:31-37 / :32-38 / :33-38 / :47-52` | Intercept rate, duration, energy, saturation, RMSE, and timing gates | Numeric release thresholds are hardcoded for the retired interceptor outcome, with no per-value source/provenance in the JSON. |
| `anti-drone-dome/scenario_data/regression_campaign_v1.json:6-9,79,97,115,133,151-154` | Campaign intercept/duration/energy/saturation limits | Hardcoded performance gates are executable pass/fail criteria without traceable rationale in the config itself. |
| `anti-drone-dome/validation/failure_analysis.py:31,189` | `Identify measured stress factors`; `Stress factors are measured correlations` | Inputs are deterministic simulation episodes; this wording can be read as physical measurement. |
| `anti-drone-dome/ml/environment.py:214` | `Measured effect here is small` | It refers to the synthetic environment result without saying so in the wording. |
| `anti-drone-dome/scripts/launch_packaged_unreal_demo.ps1:46-51` | `Measured on a 4-core/8-thread` resource budget | No hardware identity, command, date, or artifact is attached to the measurement claim. |
| `anti-drone-dome/test_camera.py:21` | `MJPEG unlocks 60 fps ... YUYV is limited to 30 fps` | Hardware performance assertion lacks camera/host/driver measurement context. |

Not flagged as hygiene problems: `replay_camera_recording.py:174` explicitly
limits performance scope; `run_companion_smoke.py:1` explicitly says it runs
without physical hardware; `rocket_effector.py` explicitly calls its values
unmeasured; and most validation code makes its non-actuation boundary explicit.

## 5. Effector-agnosticism check

The following code binds what should become the portable brain to a specific
airframe, flight controller, motor setup, or interceptor outcome.

| File(s) | Coupling and assessment |
| --- | --- |
| `sim/drone.py`, `sim/airframe_profiles.py`, `sim/flight_envelope.py`, `config.py`, `scenarios.py`, `scenario_data/airframe_profiles_v1.json` | Specific interceptor/intruder mass, thrust, speed, battery, altitude, fixed-wing and vehicle dynamics are used in runtime/simulation logic. These must not be inputs required by the portable perception/cue brain. |
| `guidance/intercept.py:53` and much of `ml/` | Guidance gains, acceleration limits, target-contact behavior, and PPO training are tied to one interceptor performance model. Preserve APN's generic track/setpoint interface, but isolate these platform values later. |
| `dome/killzone.py`, `sim/collision.py`, `sim/rocket_effector.py`, `scenarios_multi_effector.py`, `swarm/cpk_optimizer.py` | Protected-dome, collision, rocket, and cost-per-kill concepts encode an owned effector/kill chain. They are not portable brain logic. |
| `comms/datalink.py:7-9` | Fixed pseudo-geodetic origin and ENU-to-lat/lon scale are embedded in transport. A portable companion needs negotiated/calibrated frame origin, not a project location. |
| `comms/sitl_bridge.py` and `hardware_profiles/ardupilot_sitl.json` | ArduPilot SITL control path is useful test infrastructure, not the Mamba F405 deployment interface. |
| `hardware_profiles/larp_betaflight_readonly.json` and `scripts/betaflight_*`, `setup_*`, `recover_*`, `restore_*`, `watch_*` | Explicit legacy Omnibus/Fury/Betaflight/Spektrum assumptions. Keep only as lab recovery history; do not route companion features through them. |
| `hardware_profiles/raspberry_pi5_companion.json` | Correctly identifies Pi 5 but still defines a generic lab quadrotor and UDP-only telemetry; it does not yet encode the confirmed Pi+Hailo / Mamba F405 UART-MAVLink architecture. |
| `main.py:1039-1083,1198` | Synthetic mission directly applies setpoints to its own `interceptor` object or ArduPilot SITL and broadcasts a synthetic radar return. A portable brain should expose track/cue/setpoint contracts without owning vehicle dynamics. |
| `unreal/AegisTacticalViewer/`, `assets/*interceptor*`, `assets/shahed136.*`, and viewer scripts | Viewer names, models, and status imagery are tied to AEGIS/interceptor framing. It is presentation-only, so retain frozen and refactor only if needed for brain/replay demonstrations. |

### Bottom line

The repository already contains useful building blocks for the new product:
locked detection artifacts, recorded-media replay, a perception packet, 2-D
ByteTrack, a generic passive-optical estimator, EO/radar fusion, generic APN
track consumption, assignment, and reproducible validation harnesses. The
critical chain is not connected in real hardware: there is currently no
Hailo-backed live detector, no RF cue, no packet-to-3-D-track bridge, no live
fusion/association, and no UART MAVLink companion handoff to the Mamba FC.
The shortest defensible product path is to close that traceable perception
chain before changing interceptor simulation, effector models, PPO, or viewer
features.
