# Implementation status

This page separates running code from validated evidence and future work.

## Implemented now

| Capability | Actual implementation |
|---|---|
| Physics | PyBullet authoritative dynamics in local ENU coordinates |
| Operator interface | Qt/PyQtGraph integrated command center |
| Tactical rendering | Embedded PyBullet camera using OpenGL or Tiny Renderer |
| Environment | Collision terrain from cached elevation, with procedural fallback, plus cached OSM |
| Sensors | Single-engagement radar/EO fusion plus synthetic multi-target radar with anonymous-track association for swarm simulation |
| Guidance | APN default with command limits |
| ML | Optional bounded residual PPO and Gymnasium training environment |
| Vision training | Capture, extract, auto-label, merge, fine-tune, and live YOLO scripts |
| Companion path | Pi 5 read-only profile, locked model manifests, recorded-media replay, and versioned perception telemetry |
| Scenarios | Interactive profiles plus eight deterministic stress cases |
| Evidence | Mission JSONL, event log, hashes, ACMI, JSON/CSV/HTML reports |
| External integration | Validated, georeferenced `aegis.tactical.v1` UDP telemetry with deterministic JSONL replay |
| Presentation bridge | `aegis.unreal-bridge.v1` UDP bridge enriching tactical telemetry with WGS84 geodetic, heading, and speed for Unreal/Cesium clients |
| Swarm coordination | Sensor-in-loop experimental swarm: synthetic multi-target radar, anonymous-track assignment, one-way RF link model, headless runner, live command-center view, and `aegis.swarm-coordination.v1` telemetry |
| Flight envelope | Realistic turn-g / climb-rate / minimum-airspeed limits (fixed-wing bank-to-turn vs multirotor hover) applied to swarm motion, grounded in per-airframe profile values |
| Hardware posture | SIL/SITL and read-only Betaflight profiles |
| Airframe fidelity | Versioned physical/presentation profiles, profile-synchronized mass/inertia, actuator lag, stall, turbulence, energy use, and voltage sag |
| Runtime control | Live speed selection plus recorded radar, EO, and actuator failure injection |
| Model calibration | ENU/NED log alignment with bias, velocity error, and bounded candidate recommendations |

## Verified in the current repository

- The current headless automated suite passes; CI publishes its exact count as
  an artifact rather than relying on this page.
- The strict MkDocs build passes.
- The Unreal editor target compiles cleanly against UE 5.8.
- The eight-case APN campaign completed 380/800 synthetic interceptions (47.5%),
  passing 1 of 8 scenario gates. An earlier 800/800 figure was measured with an
  18 m proximity gate rather than the current 1.0 m physical contact radius; see
  [the regression campaign](../validation/regression-campaign.md).
- Live timestamped command-center captures show changing mission state.
- A headless profile-driven Shahed mission intercepted at T+60.6 s.
- The published regression report matches its generated JSON/CSV evidence.

These checks establish repeatability in this software and simulation model.
They do not establish real-world interception reliability.

## Implemented but environment-dependent

| Capability | Requirement |
|---|---|
| CUDA PPO/YOLO | CUDA-enabled PyTorch wheel and compatible NVIDIA runtime |
| OSM environment | Approved coordinates and a completed map-cache download |
| Elevation terrain | Approved coordinates and a completed Copernicus elevation cache |
| YOLO perception | Valid trained weights |
| ArduPilot SITL | Running MAVLink-compatible SITL endpoint and arm acknowledgement |

## Not implemented or not validated

- Cesium geospatial integration (the local packaged Unreal presentation client
  and its receive-only telemetry path are implemented)
- authenticated production telemetry or command transport
- Betaflight/MSP actuation bridge
- physical interceptor actuation
- sustained Pi 5/InnoMaker/accelerator measurements
- a selected and checksum-locked production detector artifact
- field-calibrated radar/EO timing
- flight-log-derived, physically validated dynamics parameters
- HIL timing and loss-of-link qualification
- regulatory, range, or safety certification

## Architectural continuity

The first iteration was not discarded or replaced with a mockup. The project
still follows its original practical architecture:

1. PyBullet runs physics and generates authoritative state.
2. Sensors transform that state into observations and a fused track.
3. APN generates the nominal intercept command.
4. Residual ML can add a bounded correction.
5. The same state drives the command center, recorder, reports, and UDP stream.

Higher-fidelity rendering is an adapter around this working core, not a claim
that the core has already migrated to Unreal.

## Training value

The project has two complementary training tracks:

- **Guidance ML:** procedural scenarios and APN expert data support offline
  research, but residual-policy comparisons from before the 1 m contact fix are
  archived rather than current decision evidence.
- **Camera ML:** real day/IR camera recordings train a detector that can run in
  the live hardware pipeline or the rendered-camera simulation path.

The guidance track improves autonomy research and regression coverage. The
camera track is especially relevant to real hardware because its training data
can come from the actual sensor and operating environment.
