# Unreal/Cesium telemetry bridge

The Unreal bridge is a small, standalone process that sits between the
simulator and an Unreal Engine (optionally Cesium for Unreal) client. It
consumes the authoritative [`aegis.tactical.v1`](external-renderers.md) UDP
stream, performs the validation and coordinate work that would otherwise live
on Unreal's game thread, and re-emits an enriched `aegis.unreal-bridge.v1`
packet.

The simulator stays authoritative. The bridge never changes physics, guidance,
sensors, or evidence — it only augments the presentation packet.

```
main.py  --telemetry-udp 127.0.0.1:8787
            │  aegis.tactical.v1 (ENU, metres, xyzw)
            ▼
integration/unreal_bridge.py   (validate → order → geodetic → forward)
            │  aegis.unreal-bridge.v1 (ENU preserved + WGS84 geodetic)
            ▼
Unreal Engine / Cesium for Unreal   127.0.0.1:8788
```

## What the bridge adds

Every field of the original packet is preserved, so a flat local-level Unreal
map can keep using `position_enu_m` unchanged. The bridge adds, per track:

| Field | Meaning |
|---|---|
| `geodetic.latitude` / `.longitude` | WGS84 degrees, computed from the packet's `georeference.origin` using a full ellipsoidal ENU→ECEF→geodetic transform |
| `geodetic.altitude_m` | WGS84 height in metres |
| `heading_deg` | Compass heading of the velocity vector (0° = North, clockwise) |
| `ground_speed_mps` | Horizontal speed |
| `speed_mps` | Full 3-D speed |

At the packet level it adds `bridge_schema: "aegis.unreal-bridge.v1"` and, when
present, `predicted_intercept_geodetic`. A `null` interceptor track is passed
through as `null`.

## Running it

```powershell
python integration\unreal_bridge.py `
  --listen 127.0.0.1:8787 `
  --unreal 127.0.0.1:8788 `
  --stats-interval 240 `
  --echo
```

Then launch the simulator pointing its telemetry at the bridge's listen port:

```powershell
python main.py --telemetry-udp 127.0.0.1:8787
```

The canonical UE 5.8 presentation project is
`unreal/AegisTacticalViewer/AegisTacticalViewer.uproject`. It binds only to
`127.0.0.1:8788`, validates the bridge schema before displaying a track, and
has no socket or code path back to Python. The saved local visual map is
`/Game/Maps`; it is intentionally not a real-world georeference.

`--echo` prints a per-packet geodetic summary; `--stats-interval N` reports
received/forwarded/dropped/rejected counts every `N` forwarded packets.

The bridge validates each datagram, enforces strictly increasing sequence and
mission time, counts upstream sequence gaps as loss, and silently drops
malformed, duplicate, or out-of-order datagrams (all expected on UDP) instead of
crashing. It can be exercised offline with the recorded-stream replay tool
described in [external renderers](external-renderers.md).

## Cesium for Unreal integration

The geodetic fields are exactly what a `CesiumGeoreference` needs:

1. Set the georeference origin from `georeference.origin` (respect the
   `placeholder` vs `approved` status — do not present a placeholder as a real
   field site).
2. For each track, place a globe anchor at `geodetic.latitude`,
   `geodetic.longitude`, `geodetic.altitude_m`.
3. Orient the actor with `heading_deg` (and the original `orientation_xyzw` if
   full attitude is needed).

Because the bridge already computes geodetic coordinates, the Unreal client no
longer has to implement the ENU→georeferenced conversion itself — it consumes
lat/lon/height directly.

## Flat local-level maps

If you are not using Cesium, keep using `position_enu_m` (metres, right-handed
East-North-Up) and `orientation_xyzw`. The recommended mapping into Unreal's
left-handed, centimetre world is explicit rather than guessed:

- Unreal X (cm) = North × 100
- Unreal Y (cm) = East × 100
- Unreal Z (cm) = Up × 100
- Actor yaw (deg) = `heading_deg`

Document whichever convention your project adopts and apply it in exactly one
place.

## Boundaries that still apply

- **Presentation only.** Buffer two snapshots and interpolate for rendering;
  never feed interpolated state back into guidance, sensors, or evidence.
- **Staleness.** Mark telemetry stale after a receive timeout and stop
  extrapolating — UDP has no loss-of-link signal.
- **Security.** This is local research telemetry, not an authenticated command
  channel. Do not expose it to untrusted networks or use it for actuation. Keep
  operator commands on a separate, authenticated, safety-gated path.
