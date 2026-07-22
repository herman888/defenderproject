# Unreal, Cesium, ROS, and external clients

Launch the simulator with a UDP destination and retain the exact transmitted
packets for offline client development:

```powershell
python main.py `
  --telemetry-udp 127.0.0.1:49000 `
  --telemetry-record missions\renderer\tactical.jsonl
```

Recording creation never overwrites evidence. If the requested path exists,
the publisher selects the first free numbered sibling such as
`tactical.001.jsonl`. This also keeps repeated missions in one simulator
session from colliding.

The `aegis.tactical.v1` packet is a presentation boundary. It keeps PyBullet,
sensor fusion, guidance, and ML authoritative while allowing another process to
render geospatial terrain, buildings, atmosphere, effects, and operator views.

The checked-in JSON Schema is published at
[`/schemas/aegis.tactical.v1.schema.json`](../schemas/aegis.tactical.v1.schema.json).
The Python publisher performs equivalent runtime checks without adding a
`jsonschema` dependency.

## What is available before Unreal is installed

- Explicit local ENU axes, metre units, and PyBullet `xyzw` quaternions
- Geodetic latitude, longitude, and altitude for the Cesium georeference
- An explicit `placeholder` or `approved` origin status
- Stable track, role, type, and renderer asset identifiers
- Terrain provenance and confirmation that the same terrain drives collision
- Strict non-negative sequence and simulation-relative mission time
- Validated JSONL recording and exact UDP replay
- Duplicate, out-of-order, backwards-time, and sequence-gap detection

Replay a recorded mission without running PyBullet:

```powershell
python scripts\replay_tactical_stream.py `
  --input missions\renderer\tactical.jsonl `
  --udp 127.0.0.1:49000 `
  --rate 1.0
```

Use `--no-wait` for parser/load testing. It preserves packet sequence and
mission timestamps but intentionally does not preserve wall-clock pacing.

## Unreal/Cesium adapter responsibilities

1. Validate each datagram before putting it on Unreal's game thread.
2. Reject sequence numbers less than or equal to the last accepted value.
3. Count sequence gaps as packet loss and show that health state to the operator.
4. Set the Cesium georeference from `georeference.origin`; do not silently use
   the current placeholder as an approved field site.
5. Convert `position_enu_m` from metres into the georeferenced Unreal world.
6. Convert PyBullet `orientation_xyzw` explicitly rather than reordering by guess.
7. Map `asset_id` to one canonical actor and one label anchor.
8. Buffer two valid snapshots and interpolate presentation only. Never feed
   interpolated state back into guidance, sensors, or evidence.
9. Mark telemetry stale after a configured receive timeout and stop
   extrapolating. UDP has no built-in loss-of-link signal.
10. Keep operator commands on a separate authenticated and safety-gated channel.

## First Unreal milestone

The first client should remain deliberately small:

1. One Cesium world and georeference
2. One UDP receiver bound to `127.0.0.1:49000`
3. Schema/sequence validation off the game thread
4. One actor registry keyed by track ID
5. Shahed and interceptor placeholder assets selected by `asset_id`
6. Position/orientation interpolation and a visible stale-data indicator
7. Live mode and deterministic JSONL replay producing the same poses

Photorealistic assets, weather, EO/IR effects, and operator controls should come
after that contract test passes.

## Why UDP

UDP offers a small dependency-free prototype boundary and does not block the
physics loop. A production deployment may wrap the same versioned state in
ROS 2/DDS, but transport changes should not silently change field semantics.

## Security boundary

The current stream is local research telemetry, not an authenticated command
protocol. Do not expose it to untrusted networks or use it for actuation.
