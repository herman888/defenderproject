# AEGIS vehicle asset slots

The curated importer currently supplies:

- Shahed shells:
  `/Game/Aegis/Imported/Shahed136/80_followers_iranian_shahed-136_drone/StaticMeshes/Object_6`
  and `Object_8`
- Radar tower:
  `/Game/Aegis/Imported/RadarTower/rts_radar_tower__1_/StaticMeshes/radar_tower_build_0`

Run `Scripts/import_curated_assets.py` through `UnrealEditor-Cmd.exe` to
re-import the attributed GLB sources and reapply the 2K/streaming settings.

The viewer also automatically uses these future static-mesh slots when they
exist:

- `/Game/Aegis/Vehicles/SM_Interceptor`
- `/Game/Aegis/Vehicles/SM_FpvThreat`
- `/Game/Aegis/Vehicles/SM_ConsumerQuad`

Missing slots retain low-cost procedural silhouettes. Imported meshes are
presentation assets only: Python telemetry continues to own position,
attitude, speed, sensing, guidance, and mission outcome.

For the GTX 1650 target, use 2K materials, authored LODs, simple collision (or
no collision for display tracks), and avoid Nanite-only meshes.
