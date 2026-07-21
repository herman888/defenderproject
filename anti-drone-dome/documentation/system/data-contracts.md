# Data contracts and coordinate frames

All versioned interfaces use JSON-compatible values and explicit schema names.

## Coordinate conventions

- Mission state: local East-North-Up (ENU)
- Position: metres
- Velocity: metres per second
- Acceleration: metres per second squared
- Time: seconds

Flight-log validation can ingest ENU or NED and converts before alignment.

## Schemas

| Schema | Producer | Purpose |
|---|---|---|
| `aegis.tactical.v1` | Tactical UDP publisher | Compact live state for external clients |
| `aegis.mission.v1` | Mission recorder | Run identity, environment, result, artifacts |
| `aegis.telemetry-sample.v1` | Mission recorder | Normalized mission snapshots |
| `aegis.mission-event.v1` | Mission recorder | Ordered mission lifecycle events |
| `aegis.hardware-profile.v1` | Hardware profile loader | Vehicle, protocol, safety, and gates |
| `aegis.regression-campaign.v1` | Scenario catalog | Named deterministic stress cases |
| `aegis.regression-report.v1` | Campaign runner | Episode evidence and gate decisions |
| `aegis.elevation-grid.v1` | Elevation downloader | Local-ENU terrain samples and provenance |
| `aegis.companion-perception.v1` | Onboard companion | Timestamped camera detections without actuation |

## Tactical UDP

```json
{
  "schema": "aegis.tactical.v1",
  "sequence": 42,
  "mission_time": 8.2,
  "intruder_pos": [210.0, 430.0, 120.0],
  "interceptor_pos": [35.0, 80.0, 62.0],
  "fused_track": {},
  "predicted_intercept": [145.0, 295.0, 88.0]
}
```

UDP is intentionally lightweight and unordered. Consumers must reject malformed
packets, monitor sequence gaps, and treat stale state as unavailable rather
than extrapolating indefinitely.

## Evidence integrity

Completed mission manifests include SHA-256 hashes and byte sizes for telemetry,
events, and attached artifacts. Raw camera arrays are excluded from JSONL;
video belongs in a separately encoded artifact.
