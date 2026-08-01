# Aegis Tactical Viewer

This is an Unreal Engine **presentation client** for the Defender Project.
Python remains the source of truth for physics, sensors, guidance, and mission
evidence. This project only renders the validated UDP telemetry emitted by
`anti-drone-dome/integration/unreal_bridge.py`.

## Prerequisites

- Unreal Engine 5.8 installed through Epic Games Launcher
- Visual Studio 2022 with the **Game development with C++** workload on Windows
- The Defender Project Python virtual environment prepared as documented in
  `anti-drone-dome/README.md`

## First editor launch

1. Open `AegisTacticalViewer.uproject` in Unreal Engine. Let Unreal build the
   C++ modules if prompted.
2. The saved local World Partition map is already `Content/Maps.umap`; it is
   visual context only and not a real-world georeference.
3. Press Play. The game mode automatically creates a telemetry manager which
   listens only on UDP `127.0.0.1:8788`. It accepts either the preferred
   enriched bridge feed or the simulator's validated local tactical feed;
   direct packets derive a display-only heading from their velocity.
4. Press `C` while the viewer has focus to cycle through **Engagement**,
   **Command**, **Chase**, **Top Down**, **Orbit**, and **Sensor / EO** views.
   In Orbit view, use mouse/right stick to orbit and the mouse wheel to zoom.
   Press `H` for the clean cinematic overlay; press it again for the full tactical HUD.

The attributed Shahed-136 and radar-tower models in
`anti-drone-dome/assets` are imported under `/Game/Aegis/Imported`; attribution
and CC BY 4.0 source links are recorded in
`anti-drone-dome/assets/ATTRIBUTION.md`. The viewer still keeps deterministic
engine-shape fallbacks, and the interceptor remains a generated quadcopter
silhouette until a suitable attributed model is added. These are presentation
assets rather than claims about a real aircraft or location. The telemetry,
physics, and display-only safety boundary do not change.

For the final art pass, add only free/verified-license Fab or Quixel content:

1. A stylized or generic fixed-wing UAV mesh and a quadcopter mesh.
2. A tiled sand/rock ground material plus a small rock and scrub set.
3. Optional generic training-range props such as a radar mast, service road,
   and non-identifying utility buildings.

Keep textures at 2K and use scalable materials; this project is tuned for a
GTX 1650 with 4 GB VRAM.

## One-click repeating demo

Run [`launch_unreal_demo.ps1`](../../anti-drone-dome/scripts/launch_unreal_demo.ps1).
It starts a regular single-threat Python mission, records each mission to JSONL,
repeats it after completion, launches the local bridge, and opens this project.
Press Play once in Unreal. Press `C` to cycle camera framing. Use
`stop_unreal_demo.ps1` to stop only the Python helpers; Unreal remains open.

## Packaged viewer

The tested Windows build is at
`unreal/builds/AegisTacticalViewer-Win64-curated/Windows/`.
Run `anti-drone-dome/scripts/launch_packaged_unreal_demo.ps1` for the same
continuous demo without opening the Unreal editor or pressing Play.

The packaged viewer also provides loopback-only training controls:

| Key | Local simulation action |
| --- | --- |
| `Space` | Pause/resume |
| `R` | Restart current scenario |
| `1`, `2`, `4`, `8` | Requested simulation rate |
| `C` | Cycle tactical camera |
| `H` | Toggle clean cinematic / full tactical HUD |
| Mouse/right stick + wheel | Orbit camera and zoom (Orbit view only) |
| `N` | Load the next curated scenario preset |
| `F5`, `F6`, `F7` | Toggle radar, EO, or actuator failure injection |
| `X` | Clear all injected failures |

Every live run records JSONL and ACMI evidence. Run
`anti-drone-dome/scripts/launch_packaged_unreal_replay.ps1` to replay the most
recent validated JSONL mission at 2x.

The default controller is adaptive APN: navigation gain, command speed,
terminal blend, and target-acceleration compensation respond to the live
engagement and track confidence. A learned policy can be added only as a
bounded residual. See
[`GUIDANCE_AI.md`](../../anti-drone-dome/GUIDANCE_AI.md). To verify that both
vehicles move continuously in a recording, run:

```powershell
python scripts\validate_unreal_motion_recording.py missions\renderer\unreal-demo.jsonl
```

## Vertical-slice presentation pass

The viewer’s code-side presentation pass is deliberately asset-independent:

- The flight camera now has predictive framing, telemetry-triggered cuts for
  deployment/radar acquisition/intercept, manual orbit, dynamic FOV, and a
  visibility trace to avoid terrain and compound geometry.
- Vehicle trails are pooled continuous contrail sections instead of dots, with
  speed-responsive engine glow, navigation lights, rotor motion, and a visual
  radar sweep/pulse. These are display effects only.
- `H` keeps target boxes, altitude labels, and off-screen arrows while removing
  the panels for cinematic capture. Full tactical mode adds closure, time to
  intercept, altitude delta, track confidence, history, and the ENU picture.
- The default renderer keeps Lumen and virtual shadows disabled, enables
  modest AO/bloom/exposure, and uses TSR at 80% internal resolution. Use the
  75–85% quality tiers as the intended GTX 1650 range.

The remaining editor-only art work is documented in
[`documentation/vertical-slice-art-pass.md`](documentation/vertical-slice-art-pass.md).

## Start the live pipeline manually

In `anti-drone-dome`, use two terminals:

```powershell
# Terminal 1: validate, enrich, and forward packets to Unreal.
python integration\unreal_bridge.py --listen 127.0.0.1:8787 --unreal 127.0.0.1:8788 --echo

# Terminal 2: run the authoritative Python simulation.
python main.py --telemetry-udp 127.0.0.1:8787
```

Then press Play in Unreal. `LogAegisTacticalViewer` reports received packets in
the Unreal Output Log. The actors interpolate only between received snapshots
and never extrapolate. The controls above send a separate, whitelisted protocol
to the local training simulation on `127.0.0.1:8789`; there is no hardware or
weapon command path.

For the simplest local viewer path, the simulator may send straight to the
viewer instead: `python main.py --telemetry-udp 127.0.0.1:8788`. The bridge is
still preferred when Cesium/geodetic metadata or a separate validation hop is
required.

## Coordinate convention

The bridge sends local ENU coordinates in metres. The only conversion is in
`AegisTacticalTrackActor::ApplySnapshot`:

| Source ENU | Unreal world |
| --- | --- |
| North (m) | X (cm) |
| East (m) | Y (cm) |
| Up (m) | Z (cm) |

`heading_deg` is compass heading: 0 = North, increasing clockwise. It maps
directly to Unreal yaw when X is North and Y is East.

## Safety boundary

This is display-only local research telemetry. Do not expose UDP port 8788 to
untrusted networks and do not use this viewer as a command or actuation path.
