# Project LARP stakeholder brief

## The proposition

Project LARP is building an evidence-first counter-UAS research and validation
platform. Its present value is not a claim of field-ready interception. It is
a repeatable way to turn sensing, tracking, guidance, vehicle assumptions, and
viewer outputs into reviewable evidence before capital is committed to field
integration.

The product path is a defensible engineering workflow:

    measured inputs -> versioned models -> seeded experiments -> recorded artifacts -> reviewable decisions

That distinction matters. A cinematic demo can illustrate an idea; it cannot
establish sensor range, vehicle performance, reliability, or safety. This
project keeps those categories separate.

## What exists today

| Asset | Current state | Why it matters |
| --- | --- | --- |
| Digital twin | Python simulation with versioned scenarios, guidance baselines, mission records, and strict test coverage | Enables controlled comparisons and regression detection |
| Sensor boundary | Synthetic multi-target radar produces anonymous tracks and association rather than passing scenario identifiers into swarm coordination | Makes the next experiments sensitive to sensing and track-management limits |
| Evidence pipeline | Deterministic runs, regression reports, parameter register, verification matrix, and data contracts | Gives partners artifacts they can inspect and reproduce |
| Presentation | Local packaged Unreal viewer and versioned tactical/swarm UDP contracts | Supports a transparent live or replayed technical demonstration |
| Vision and hardware paths | Candidate camera workflow, hardware profiles, calibration tools, and HIL readiness material | Defines integration work without representing it as complete |

The [implementation status](../system/implementation-status.md) and
[current evidence](../results/current-evidence.md) are the authoritative
limits on these statements.

## What we will not claim

The project does **not** currently claim a deployed sensor, validated acoustic
seeker, calibrated airframe, approved operating site, field reliability, or
autonomous operational capability. Current controller results are synthetic;
the named stress campaign is deliberately failing its release gate in several
cases under the corrected 1 m contact criterion.

This is useful negative evidence. It identifies where investment and partner
testing should be directed instead of converting a broad proximity threshold
or a polished render into an unsupported result.

## Why this can become defensible

Defensibility is being built through process and data rights, not by treating
an algorithm name as a moat:

1. **Traceability:** scenarios, model parameters, seeds, telemetry schemas,
   and generated reports are versioned.
2. **Honest interfaces:** the coordination system receives synthetic sensor
   tracks, not hidden scenario labels; presentation clients are receive-only.
3. **Comparable evidence:** every proposed capability has a named exit
   artifact in the [verification matrix](../validation/verification-matrix.md).
4. **Measured-model loop:** partner measurements will revise registered
   parameters, then rerun the same seeded campaign.
5. **No premature ML story:** APN remains the baseline. A learned policy is
   only retained if it improves pre-registered, calibrated sensor-in-loop
   metrics and preserves the same safety constraints.

## Evidence gates and partner opportunities

| Next gate | Partner contribution | Decision artifact | Decision enabled |
| --- | --- | --- | --- |
| Restore public due-diligence site | Vercel/project ownership | Live strict-built site and link check | Shareable technical package |
| Sensor characterization | Radar/EO provider, range, or lab access | Range/RCS/condition and latency report | Select sensing architecture and uncertainty model |
| Acoustic feasibility | Microphone/compute partner and bench access | SNR, bearing error, and thermal/latency report | Continue or retire acoustic cueing path |
| Vehicle calibration | Airframe, thrust stand, and logged test data | Mass, inertia, thrust, energy, and dynamics residual report | Replace representative dynamics with a measured profile |
| HIL and link behavior | Flight-control, communications, and safety partner | Timestamped latency/loss-of-link HIL report | Establish the safe integration envelope |
| Controlled demonstration | Range operator and safety review | Recorded, approved, end-to-end demonstration package | Evaluate a constrained pilot program |

Each partner engagement should define ownership, permitted reuse, data format,
measurement conditions, and publication approval before testing begins. This
is essential both for IP discipline and for credible comparisons.

## Near-term execution plan

1. Restore the Vercel deployment; the configured public URL currently returns
   HTTP 404.
2. Freeze a baseline release tag containing the current documentation,
   deterministic evidence artifact, parameter register, and package manifest.
3. Pre-register the next sensor-in-loop campaign: scenarios, seeds, metrics,
   thresholds, environment, and the conditions that would count as failure.
4. Secure one measurement partner before adding new guidance or rendering
   features. Sensor, airframe, and latency measurements have higher
   information value than more synthetic-policy training.
5. Convert the first partner dataset into a hashed artifact, update the
   parameter register, rerun the campaign, and publish the delta and limits.

## Diligence map

- [Architecture and interfaces](../system/architecture.md)
- [Edge platform and integration](../system/edge-platform-and-integration.md)
- [Implementation status](../system/implementation-status.md)
- [Parameter register](../system/parameter-register.md)
- [Evidence-first roadmap](../system/roadmap.md)
- [Verification matrix](../validation/verification-matrix.md)
- [Current evidence and limitations](../results/current-evidence.md)
- [Regression campaign method](../validation/regression-campaign.md)
- [Data contracts](../system/data-contracts.md)

This brief is deliberately conservative. A partner should be able to discover
limitations from the same documentation package that presents the opportunity.
