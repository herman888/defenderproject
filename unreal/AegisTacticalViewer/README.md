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
   listens only on UDP `127.0.0.1:8788`.
4. Press `C` while the viewer has focus to cycle between **Chase**,
   **Tactical**, and **Terrain** camera framing.

The viewer creates basic-shape spheres for the intruder and interceptor. To
replace them, create Blueprint subclasses of
`AegisTacticalTrackActor`, give each a mesh/material, and assign those classes
to the telemetry component in a Blueprint subclass of
`AegisTacticalTelemetryManager`.

## One-click repeating demo

Run [`launch_unreal_demo.ps1`](../../anti-drone-dome/scripts/launch_unreal_demo.ps1).
It starts a regular single-threat Python mission, records each mission to JSONL,
repeats it after completion, launches the local bridge, and opens this project.
Press Play once in Unreal. Press `C` to cycle camera framing. Use
`stop_unreal_demo.ps1` to stop only the Python helpers; Unreal remains open.

## Packaged viewer

The tested Windows build is at `unreal/builds/AegisTacticalViewer-Win64/Windows/`.
Run `anti-drone-dome/scripts/launch_packaged_unreal_demo.ps1` for the same
continuous demo without opening the Unreal editor or pressing Play.

## Start the live pipeline manually

In `anti-drone-dome`, use two terminals:

```powershell
# Terminal 1: validate, enrich, and forward packets to Unreal.
python integration\unreal_bridge.py --listen 127.0.0.1:8787 --unreal 127.0.0.1:8788 --echo

# Terminal 2: run the authoritative Python simulation.
python main.py --telemetry-udp 127.0.0.1:8787
```

Then press Play in Unreal. `LogAegisTacticalViewer` reports received packets in
the Unreal Output Log. The actors interpolate only between received snapshots;
they do not extrapolate or issue commands back to Python.

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
