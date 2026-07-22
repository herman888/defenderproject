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
| `aegis.vision-model.v1` | Vision manifest tools | Exact detector identity, artifact hash, and inference configuration |
| `aegis.vision-replay-report.v1` | Vision replay | Source/output hashes and host replay performance |

## Tactical UDP

```json
{
  "schema": "aegis.tactical.v1",
  "sequence": 42,
  "mission_time_s": 8.2,
  "timestamp_clock": "simulation-relative",
  "status": "ENGAGING",
  "site": "Southern Ontario training site",
  "guidance": "apn",
  "coordinate_frame": {
    "type": "local-tangent-plane",
    "axes": "ENU",
    "position_unit": "m",
    "velocity_unit": "m/s",
    "orientation": "xyzw"
  },
  "georeference": {
    "origin": {
      "latitude": 43.0,
      "longitude": -79.0,
      "altitude_m": 0.0
    },
    "status": "placeholder"
  },
  "terrain": {
    "source": "Copernicus DEM GLO-90",
    "collision_authoritative": true
  },
  "tracks": {
    "intruder": {
      "id": "TRK-001",
      "role": "intruder",
      "asset_id": "intruder/shahed136",
      "type": "shahed136",
      "position_enu_m": [210.0, 430.0, 120.0],
      "velocity_enu_mps": [-21.0, -38.0, 0.0],
      "orientation_xyzw": [0.0, 0.0, 0.88, 0.47]
    },
    "interceptor": null
  }
}
```

UDP is intentionally lightweight and unordered. Consumers must reject malformed
packets, monitor sequence gaps, and treat stale state as unavailable rather
than extrapolating indefinitely.

The canonical schema is
[`aegis.tactical.v1.schema.json`](../schemas/aegis.tactical.v1.schema.json).
The current geodetic coordinates are explicitly marked as placeholders and must
not be interpreted as an approved operating site.

## Evidence integrity

Completed mission manifests include SHA-256 hashes and byte sizes for telemetry,
events, and attached artifacts. Raw camera arrays are excluded from JSONL;
video belongs in a separately encoded artifact.
