# Project LARP strategic reassessment pack

**Audience:** investors, technical partners, suppliers, and program
stakeholders  
**Purpose:** establish what exists, what is verified, what is valuable now,
and what a first partnership should fund or supply.

## Executive position

Project LARP is an evidence-first edge-perception, tracking, integration, and
validation platform for human-authorized aerial systems. The immediate product
is not a field-ready autonomous system. It is the engineering and evidence
layer that lets a partner evaluate camera, sensing, tracking, vehicle, compute,
and integration assumptions with traceable results.

The strongest near-term commercial offer is a paid measurement and integration
pilot: take one partner sensor or vehicle configuration, establish a measured
operating envelope, integrate it through a versioned interface, and deliver a
replayable evidence pack.

## Current snapshot

| Area | What exists | Current confidence |
| --- | --- | --- |
| Authoritative simulation | Python/PyBullet system with named scenarios, sensing, guidance, vehicle profiles, recording, and deterministic checks | Software-verified; physical parameters mostly unvalidated |
| Coordination | Anonymous synthetic multi-target radar tracks and association feed swarm coordination | Research-only; sensor budget and track errors require calibration |
| Camera / EO | Capture-to-training workflow, rendered EO path, model manifest, companion-perception contract, and replay tools | Candidate model only; no locked validated detector |
| Guidance | APN baseline and synthetic stress campaigns | Software evidence only; hard scenarios fail under corrected contact criterion |
| Command center | Live tactical picture, radar/EO/fusion state, replay, recording, failure injection, and visible evidence status | Presentation-ready for research demonstration |
| Unreal viewer | Receive-only local viewer, replay path, automation tests, packaged Win64 release, SHA-256 manifest | Demonstration-ready; not an operational control client |
| Hardware | Candidate camera, flight-control inventory, profiles, SIL/HIL readiness paths | No calibrated integrated airframe or approved field operation |
| Edge compute | Companion schema and benchmark scaffolding | Jetson Nano is legacy/lab only; production board must be selected and measured |
| Documentation | Strict-built technical site, parameter register, verification matrix, roadmap, schemas, and stakeholder material | Public deployment still needs Vercel restoration |

## What has been verified

- 225 automated Python tests pass locally.
- Strict documentation build passes.
- The seeded sensor-in-loop swarm run is deterministic.
- Unreal automation tests pass and a versioned Win64 package was built with a
  SHA-256 release manifest.
- The simulator performs recorded end-to-end synthetic engagements and replay.
- The project now uses a 1 m simulated contact criterion rather than the
  inherited 18 m cinematic proximity threshold.

The full synthetic APN campaign is 380 interceptions in 800 episodes across
eight named cases, with one of eight release gates passing. That is useful
evidence of differentiation between easy and hard scenarios; it is not a field
reliability claim.

## What is valuable today

1. **Integration-risk reduction:** a partner can see the effect of sensor,
   latency, track quality, vehicle assumptions, and failure modes before
   committing to a hardware integration.
2. **Evidence discipline:** parameters, schemas, seeds, replay artifacts, and
   limitations are versioned rather than being hidden inside a live demo.
3. **Interoperability foundation:** the edge companion, tactical, and swarm
   interfaces are versioned and can be adapted to an existing host system.
4. **A credible pilot vehicle:** the command center and packaged replay make
   the engineering process understandable to non-specialist stakeholders.

## What is not yet claimed

- validated real-world detection range, false-positive rate, or camera latency;
- a selected, checksum-locked, held-out validated vision model;
- calibrated airframe dynamics, energy, actuation, or contact geometry;
- target-device thermal or end-to-end latency performance;
- approved range, safety, regulatory, or operational deployment;
- autonomous target selection, release, or field interception reliability.

## Product framing

The product should be described as three compatible layers:

| Working layer | Customer value | Boundary |
| --- | --- | --- |
| LARP Edge | Onboard perception, track-health, compute-health, and evidence node | Reports uncertainty and degraded state; no target-selection authority |
| LARP Integrate | Adapter and audit layer for an existing host, flight, C2, or robotics system | No promise of universal plug-and-play; each host needs an agreed adapter |
| LARP Evidence | Replay, validation, parameter, and reporting workbench | Does not convert synthetic results into field certification |

The individual vehicle should be positioned as an interoperable,
human-authorized autonomous platform: it can execute bounded onboard
perception and mission behavior after authorization, while the surrounding
partner system retains the agreed authority and safety policy.

## What a partner should see live

The primary demonstration view should show five evidence cards:

1. camera/EO: model identity, frame age, confidence, target size, and measured
   latency once available;
2. radar: scan age, SNR, range, confidence, and coast/degraded state;
3. fusion: sensor contributions, output age, uncertainty, and prediction;
4. edge compute: board, release, temperature, power mode, throttling, and
   actual p50/p95/p99 timing;
5. link and recording: packet age/loss, clock, mission ID, and artifact state.

Until a metric is measured, the product must display NOT MEASURED or SYNTHETIC,
not a polished substitute.

## Compute decision

The Raspberry Pi 5 plus Pi AI HAT+ / AI Kit (Hailo-8/8L) is the first
measurement platform. Its performance, thermal behaviour, and power are
**NOT MEASURED**. HailoRT plus Hailo Dataflow Compiler and a locked `.hef`
artifact are the planned toolchain. Orin Nano 8 GB and Orin NX 16 GB remain
named alternatives only if the recorded Pi/Hailo p95 end-to-end latency,
sustained thermal, or power result fails the first evidence gate. See the
[edge-platform plan](../system/edge-platform-and-integration.md).

## Partnership requests

| Counterparty | Request | Deliverable |
| --- | --- | --- |
| Camera / optics supplier | Current InnoMaker U20CAM USB rolling-shutter wide-lens camera has estimated 20–40 m terminal-lock use and **NOT MEASURED** capture/track limits. Supply one locked narrow-FOV global-shutter camera/lens configuration plus controlled small-drone recordings at known ranges. | Measured detection and capture-to-track envelope for that exact configuration, replayable. |
| Edge-compute supplier | Pi 5 + Hailo measurement support and thermal guidance | Board-specific latency, thermal, and power report |
| Airframe / propulsion supplier | Mass, inertia, thrust, battery, actuator, and integration data | Measured profile and model residual report |
| Host-system partner | One documented read-only or bounded adapter target | Replayable integration and stale-data/failure report |
| Range / safety partner | Review of a controlled evidence plan | Approved, recorded, limited-scope demonstration package |

## The decision we seek

Fund or partner around a defined first evidence gate, not an open-ended feature
list. The preferred first gate is a locked camera plus edge-compute
configuration, measured on held-out recordings and delivered through one
versioned partner interface.

## Supporting material

- [Stakeholder brief](partner-investor-brief.md)
- [Presentation and diligence kit](presentation-kit.md)
- [Edge platform and integration](../system/edge-platform-and-integration.md)
- [Implementation status](../system/implementation-status.md)
- [Parameter register](../system/parameter-register.md)
- [Verification matrix](../validation/verification-matrix.md)
- [Current evidence](../results/current-evidence.md)
- [Evidence-first roadmap](../system/roadmap.md)
