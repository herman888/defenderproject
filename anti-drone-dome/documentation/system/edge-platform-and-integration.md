# Edge platform, integration, and live-evidence architecture

## Product position

Project LARP should be presented as an interoperable **edge perception,
tracking, and evidence platform** for a human-authorized aerial system. It is
not a claim that one vehicle can replace every existing command, sensor, or
safety system.

The individual vehicle product is an onboard node that:

1. captures and timestamps camera observations;
2. produces a bounded, versioned perception track and health status;
3. fuses or forwards that track to an existing host system through a documented
   adapter;
4. carries out only the bounded mission behavior that a human-authorized
   system permits.

Target selection and release authority are not delegated to the edge node. The
node must report uncertainty, stale data, and degraded health instead of
presenting a false sense of autonomy.

## Integration principle

Do not promise universal plug-and-play integration. Promise a reusable adapter
layer with a stable core contract.

| Layer | Stable Project LARP responsibility | Partner-specific responsibility |
| --- | --- | --- |
| Perception | Camera capture, model identity, detection and track health | Camera choice, optics, enclosure, mounting |
| Edge track | Timestamped detections, temporal track, uncertainty, staleness | Host coordinate frame and acceptance criteria |
| Integration adapter | Versioned payload, schema validation, rate limiting, audit log | Existing flight/C2/robotics interface and authorization policy |
| Mission boundary | Read-only evidence by default; explicit, bounded authorized mission state | Human workflow, safety case, and operating approval |

The current companion contract is `aegis.companion-perception.v1`; the tactical
and multi-target-assignment contracts are likewise versioned. New adapters
should translate to those contracts rather than making an ad-hoc coupling to a
particular vendor.

## Live evidence cards

The command center should make the health of each link obvious in one glance.
It must show a dash or NOT MEASURED when a value does not exist, not a
synthetic-looking number.

| Card | Live fields | Why it matters |
| --- | --- | --- |
| Camera / EO | Source, model ID and hash, capture FPS, inference p50/p95, frame age, detection confidence, target pixel size, dropped/late frames | Separates image capture from actual detector performance |
| Radar | Scan age, measurement age, range, SNR, track confidence, coast state, injected-failure state | Makes stale or degraded sensing visible |
| Fusion / track | Contributing sensors, output age, innovation/residual, uncertainty, track state, prediction horizon | Explains why a track is trusted or rejected |
| Edge compute | Board identity, software release, capture-to-detection latency, detection-to-track latency, end-to-end FPS, NPU utilization, temperature, power draw | Every absent metric renders as `NOT MEASURED`; prevents a desktop benchmark being presented as edge performance |
| Link and recording | Packet age/loss, clock source, mission ID, recording status, artifact hash when complete | Lets a partner reproduce the displayed result |

For an investor demo, use the camera card, fusion/track card, and evidence
status as the primary view. Put configuration controls and failure injection
behind an operator-only presentation view after mission start.

## Camera-tracking improvement sequence

The existing rendered EO path and versioned vision manifest are useful
integration scaffolding, but the candidate model has no selected dataset,
artifact hash, or held-out validation. The next work is therefore measurement,
not a new detector architecture.

1. Lock one camera configuration: sensor, lens, exposure mode, resolution,
   frame rate, mounting, and timestamp source.
2. Record labelled day, low-light, motion-blur, clutter, and empty-scene
   sessions. Keep hard negatives.
3. Freeze a train/validation/test split before tuning thresholds.
4. Lock the selected exported model by SHA-256 and run it on the intended edge
   board.
5. Publish per-condition precision/recall, false-positive rate, target-size
   bands, capture-to-track p50/p95/p99 latency, dropped frames, and thermal
   behavior.
6. Replay the same recordings through the companion contract and compare the
   output with the simulation camera model.

The output of this work is a measured perception envelope, not merely a
bounding-box video.

## Edge compute decision

### Measurement platform: Raspberry Pi 5 + Hailo-8/8L

The first measurement platform is a Raspberry Pi 5 with a Pi AI HAT+ / AI Kit
using a Hailo-8 or Hailo-8L NPU. This is a measurement decision, not a claim
that the platform is proven for the product. The deployment toolchain is
HailoRT plus Hailo Dataflow Compiler and a locked `.hef` artifact.

Coral is not a candidate. The anchor-free DFL detect head used by YOLO11n
frequently falls back to CPU on the Edge TPU; Hailo uses a different compiler
and export path, so that specific failure mode does not apply. This does not
establish throughput, latency, thermal behaviour, power, accuracy, or tracking
quality on the Pi/Hailo configuration: each is **NOT MEASURED** until a
versioned target-device artifact exists.

### Decision and re-evaluation path

| Role | Candidate | Decision rule |
| --- | --- | --- |
| First evidence gate | Raspberry Pi 5 + Hailo-8/8L AI HAT+ | Measure exact camera/model/runtime configuration first. Capture-to-detection p95: **NOT MEASURED**; detection-to-track p95: **NOT MEASURED**; sustained thermals: **NOT MEASURED**; power: **NOT MEASURED**. |
| Named alternative | NVIDIA Orin Nano 8 GB | Re-evaluate only if the measured Pi/Hailo p95 end-to-end latency, sustained thermals, or power fail the first evidence gate. |
| Named alternative | NVIDIA Orin NX 16 GB | Apply the same trigger when the measured workload cannot meet the first evidence gate. |

NVIDIA lists Orin Nano and Orin NX production modules through January 2032.
They remain evaluated alternatives, not owned hardware or the present
measurement baseline. Advertised TOPS are not a latency or thermal guarantee.
The final board choice must follow an application-specific benchmark.
[NVIDIA lifecycle](https://developer.nvidia.com/embedded/lifecycle),
[Orin Nano module overview](https://developer.nvidia.com/embedded/jetson-modules),
and [carrier specification](https://developer.nvidia.com/downloads/assets/embedded/secure/jetson/orin_nano/docs/jetson_orin_nano_devkit_carrier_board_specification_sp.pdf)
support this selection path.

## Commercial software stack

Use a small, version-pinned stack. Avoid shipping a research desktop
environment to an edge product.

| Layer | Product choice | Gate before commercial use |
| --- | --- | --- |
| Operating system | Exact Raspberry Pi OS image, HailoRT release, and Hailo compiler/export manifest, pinned and reproducibly provisioned | Board, camera driver, secure-update, and compatibility qualification |
| Video ingest | V4L2 or GStreamer with hardware-supported camera path | Measured capture timestamp and loss behavior |
| Inference | Hailo `.hef` artifact derived from a locked model artifact | Exact `.hef`, model hash, accuracy, and per-board latency report |
| Tracking | Lightweight temporal association with explicit age and uncertainty | Replay performance on held-out recordings |
| Service boundary | Small versioned perception service exposing the existing companion schema | Schema, backpressure, restart, and stale-data tests |
| Deployment | Signed container/image, SBOM, configuration manifest, audit logs, staged updates | Rollback, power-loss, and update-recovery test |
| Observability | Local metrics and retained mission artifacts; no sensitive video by default | Clock, privacy, storage, and retention policy |

The Pi/Hailo path must not inherit TensorRT, JetPack, or Edge TPU assumptions.
HailoRT and the exact compiler/export revision belong in every target-device
artifact. The NVIDIA references above remain relevant only if the recorded
Pi/Hailo evidence triggers an Orin re-evaluation.

## Product milestones

1. **Edge perception alpha:** locked camera and a read-only companion stream
   with real capture and latency metrics.
2. **Interoperability alpha:** one adapter to a partner host system, replayed
   against recorded data with clock and failure behavior visible.
3. **Measured vehicle profile:** one airframe's mass, energy, actuator, and
   thermal evidence added to the parameter register.
4. **Integrated evidence pilot:** one approved partner workflow using recorded
   artifacts, health cards, and a documented human-authorization boundary.

This framing is commercially stronger than claiming a universal autonomous
drone. It gives customers a modular edge capability that can integrate with
their existing system while retaining traceability and human accountability.
