# Tactical rendering

## Embedded view

The command center embeds a PyBullet tactical camera with overview, intruder
chase, interceptor chase, and top-down modes. It renders:

- terrain relief and land-cover parcels
- cached OSM roads and building geometry
- purpose-built intruder and interceptor airframes
- fused track anchors and open-corner cues
- velocity vectors and predicted intercept
- sensor and engagement geometry

Adaptive chase cameras keep each aircraft visible and suppress the camera
platform's own label where it would obscure the model.

## Backends

| Backend | Use |
|---|---|
| `opengl` | Preferred accelerated tactical camera |
| `tiny` | CPU compatibility and deterministic headless preview |
| Unreal viewer | Packaged local Windows presentation client; Cesium remains a future geospatial option |

OpenGL improved tactical-frame throughput on the tested Quadro T2000, but it
does not move PyBullet physics to the GPU. CUDA applies only to PyTorch-backed
learning or inference when a CUDA-enabled wheel is installed.

## Visual evidence

The gallery includes captures from the live application. Timestamped T+3,
T+8, and T+13 evidence is retained under `reports/visual_upgrade_live/` with
the corresponding state JSON.

## Limitations

The preview uses simplified lighting, materials, and terrain. It is suitable
for operator workflow and regression screenshots, not cinematic rendering,
survey-grade geospatial analysis, or sensor certification.

