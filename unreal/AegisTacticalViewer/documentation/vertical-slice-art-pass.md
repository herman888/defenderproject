# Aegis vertical-slice art pass

This is the small, bounded content pass that turns the telemetry viewer into a
finished demonstration without changing the Python source of truth. It assumes
UE 5.8, static/baked lighting, and a GTX 1650 with 4 GB VRAM.

## Asset slots

Use only checked-license assets and retain their source metadata under
`anti-drone-dome/assets/ATTRIBUTION.md`.

| Slot | Expected project path | Budget / setup |
| --- | --- | --- |
| Interceptor | `/Game/Aegis/Vehicles/SM_Interceptor` | Rocket-shaped, body-X, four-tail-prop interceptor; <= 35k triangles at LOD0, 3 authored LODs, 2K textures. The C++ registry already selects this mesh. |
| Fixed-wing threat | `/Game/Aegis/Imported/Shahed136` | Keep the existing attributed import; preserve its local-forward axis so telemetry attitude remains exact. |
| Radar mast | `/Game/Aegis/Imported/RadarTower` | Keep the imported tower. Its separate C++ antenna/pulse is deliberately visual-only. |
| Range material | `/Game/Aegis/Environment/M_RangeTerrain` | Four tiled layers: sand, dirt, rock, and compacted road. Blend by painted weight, slope, and a macro colour texture. |
| Dressing | `/Game/Aegis/Environment/SM_Rock_*`, `SM_Scrub_*`, `SM_UtilityBuilding_*` | Use instanced static meshes, 2–3 LODs, and cull distances of 30–180 m. |

The C++ fallback compound is intentional: it provides a deterministic scene
for a packaged demo until these replacements are assigned in the map.

## Map and lighting

1. Keep the existing World Partition map as the visual training range, not a
   georeferenced claim. Paint the terrain with the range material above, then
   place sparse rock/scrub instances and a narrow service road leading to the
   site actor.
2. Use one movable directional light only if the day/night cycle is required;
   otherwise bake the directional/skylight contribution. Enable distance-field
   shadows only after measuring VRAM. Do not enable Lumen or virtual shadow
   maps for the GTX 1650 preset.
3. Add an unbound Post Process Volume with restrained values: AO intensity
   0.35, AO radius 120, bloom 0.15–0.25, local exposure enabled, a warm
   low-saturation desert LUT, and no motion blur. Add Exponential Height Fog
   for haze, not expensive volumetric fog.
4. Add a Sky Atmosphere and Sky Light, then bake/probe the final time of day.
   Test both a clear view and the telemetry environment’s reduced-visibility
   scenario; environmental labels remain telemetry facts, not rendered sensor
   results.

## Niagara and audio hand-off

The runtime includes low-cost fallback effects so the showcase remains
packagable without external content. Once the art assets are licensed, replace
them with these bounded Niagara systems:

- `NS_Contrail`: CPU ribbon, 24-point cap, 1.5 s lifetime, no collision.
- `NS_RotorWash`: spawn only below 8 m AGL, 80 particles/s maximum, distance
  culled at 120 m.
- `NS_Intercept`: 0.35 s flash, pooled debris/smoke, spawned only from the
  validated terminal status transition.
- `NS_RadarPulse`: 1–2 translucent rings with a fixed maximum of one active
  pulse; it must never imply a detection absent from telemetry.

Create a MetaSound for each vehicle and expose only display parameters:
`speed_mps`, `rotor_rpm_visual`, and `link_stale`. Attach attenuation and
spatialization to the rendering actor. Suggested priorities are engine/rotor,
lock warning, radar sweep, deployment, then terminal effect. Do not route any
audio or VFX callback into simulation, guidance, or hardware control.

## Acceptance capture

At 1080p, test the regular Python demo at TSR 75%, 80%, and 85%. Capture the
launch/deployment, radar-acquisition, closest-approach, and terminal beats.
The acceptance target is 45–60 FPS with no camera-terrain penetration, no
unbounded particle growth, readable target boxes, and identical simulation
recordings with the viewer enabled or disabled.
