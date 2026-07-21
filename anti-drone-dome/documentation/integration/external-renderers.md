# Unreal, Cesium, ROS, and external clients

Launch the simulator with a UDP destination:

```powershell
python main.py --telemetry-udp 127.0.0.1:49000
```

The `aegis.tactical.v1` packet is a presentation boundary. It keeps PyBullet,
sensor fusion, guidance, and ML authoritative while allowing another process to
render geospatial terrain, buildings, atmosphere, effects, and operator views.

## Unreal/Cesium adapter responsibilities

1. Parse and validate the schema and sequence.
2. Convert local ENU to the selected Cesium georeference.
3. Interpolate visuals between valid packets without changing simulation state.
4. Render each track from one canonical actor and one label anchor.
5. Mark stale or missing telemetry rather than hiding the failure.
6. Keep operator commands on a separate authenticated and safety-gated channel.

## Why UDP

UDP offers a small dependency-free prototype boundary and does not block the
physics loop. A production deployment may wrap the same versioned state in
ROS 2/DDS, but transport changes should not silently change field semantics.

## Security boundary

The current stream is local research telemetry, not an authenticated command
protocol. Do not expose it to untrusted networks or use it for actuation.

