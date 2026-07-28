# Tactical Viewer asset intake

This project deliberately starts with high-contrast Engine placeholder meshes. They are a safe, clear fallback while the simulation and local-network telemetry are verified. Python remains authoritative; the viewer has no command or simulation return path.

## One manual Fab/Quixel step

Sign in to Fab inside Unreal, then add only free or account-licensed assets whose license screen you can verify. Prefer these searches:

| Use | Fab/Quixel search | Budget |
|---|---|---|
| Terrain base | `Megascans dry sand surface` | 2K, tiled |
| Rocky variation | `Megascans desert rock surface` | 2K, tiled |
| Dressing | `desert rock low poly` | a few instances, no dense scatter |
| Intruder visual | `generic fixed wing drone` | low-poly / LODs required |
| Interceptor visual | `generic quadcopter` | low-poly / LODs required |

Import into `Content/Art/Fab/` (not into `Maps/`). Keep screenshots or receipts of each asset's displayed license with the project records. Do not import assets with unclear rights, real-world weapon branding, or claims of operational accuracy.

## Hooking them up

Update the soft mesh paths in `Source/AegisTacticalViewer/Private/TacticalAssetRegistry.cpp`. Keep the existing BasicShapes fallback entries: unknown `asset_id` values must remain visible rather than causing a failed track.

## GTX 1650 / 4 GB budget

Use 2K texture variants, texture streaming, material instances, traditional shadow maps, and restrained prop counts. Do not enable Lumen, Nanite, Cesium, or large 4K texture packs for this target. The project starts with a 1400 MB streaming pool and scalable quality settings; adjust only after profiling a packaged 1080p build.

## Map position

`Maps.umap` is the existing local World Partition scene. It is visual context only: it is not georeferenced. Do not imply that it represents a real site until an approved georeference is supplied.
