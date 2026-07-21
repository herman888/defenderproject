# Mission recording and replay

Each recorded run receives a UTC-derived ID and its own directory:

```text
mission_records/<run_id>/
  manifest.json
  telemetry.jsonl
  events.jsonl
  mission.acmi
```

## Manifest

The `aegis.mission.v1` manifest records:

- mission and hardware profile
- Python and platform identity
- local ENU units and coordinate frame
- final status and result
- sample and event counts
- artifact paths, sizes, and SHA-256 hashes

Incomplete runs are explicitly marked `incomplete` with a reason.

## Telemetry

Normalized samples include positions, velocities, fused sensor state, weather,
guidance mode, predicted intercept, confidence, TTI, backend identity, events,
and real-time factor.

Raw image arrays are deliberately excluded. Store video as an encoded,
separately hashed artifact to prevent telemetry files from growing by hundreds
of megabytes during a short mission.

## ACMI

The recorder exports Tacview-compatible ACMI for post-mission trajectory review.
ACMI complements, but does not replace, the normalized JSONL evidence.

