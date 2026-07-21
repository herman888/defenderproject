# Implementation status

This page separates running code from validated evidence and future work.

## Implemented now

| Capability | Actual implementation |
|---|---|
| Physics | PyBullet authoritative dynamics in local ENU coordinates |
| Operator interface | Qt/PyQtGraph integrated command center |
| Tactical rendering | Embedded PyBullet camera using OpenGL or Tiny Renderer |
| Environment | Procedural terrain plus cached OSM roads and buildings |
| Sensors | Simulated radar, rendered EO/segmentation, optional YOLO, fusion |
| Guidance | APN default with command limits |
| ML | Optional bounded residual PPO and Gymnasium training environment |
| Scenarios | Interactive profiles plus eight deterministic stress cases |
| Evidence | Mission JSONL, event log, hashes, ACMI, JSON/CSV/HTML reports |
| External integration | Versioned `aegis.tactical.v1` UDP telemetry |
| Hardware posture | SIL/SITL and read-only Betaflight profiles |

## Verified in the current repository

- 29 automated tests pass.
- The strict MkDocs build passes.
- The eight-case APN campaign completed 800/800 synthetic interceptions.
- Live timestamped command-center captures show changing mission state.
- The published regression report matches its generated JSON/CSV evidence.

These checks establish repeatability in this software and simulation model.
They do not establish real-world interception reliability.

## Implemented but environment-dependent

| Capability | Requirement |
|---|---|
| CUDA PPO/YOLO | CUDA-enabled PyTorch wheel and compatible NVIDIA runtime |
| OSM environment | Approved coordinates and a completed map-cache download |
| YOLO perception | Valid trained weights |
| ArduPilot SITL | Running MAVLink-compatible SITL endpoint and arm acknowledgement |

## Not implemented or not validated

- Unreal Engine/Cesium presentation client
- authenticated production telemetry or command transport
- Betaflight/MSP actuation bridge
- physical interceptor actuation
- field-calibrated radar/EO timing
- flight-log-derived dynamics model
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
