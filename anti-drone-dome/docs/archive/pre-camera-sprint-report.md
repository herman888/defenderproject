# Pre-camera sprint report

Date: 2026-08-12. Scope is the Windows host and committed evidence only. This is
not a target-device or field-performance report.

## Measured evidence

| Subject | Result | Artifact |
| --- | --- | --- |
| Synthetic pixel floor, centre crop | 50% at 24 px; 90% `NOT MEASURED` | `artifacts/vision/pixel_floor_20260811T151545Z.json` |
| Synthetic pixel floor, native tiles | 50% at 24 px; 90% `NOT MEASURED` | `artifacts/vision/pixel_floor_20260811T151545Z.json` |
| Synthetic pixel floor, full-frame resize | 50% and 90% `NOT MEASURED` through 64 px | `artifacts/vision/pixel_floor_20260811T151545Z.json` |
| Centre-crop host processing cost | 104.8–142.4 ms mean across the reported widths | `artifacts/vision/pixel_floor_20260811T151545Z.json` |
| Native-tile host processing cost | 317.0–470.4 ms mean across the reported widths | `artifacts/vision/pixel_floor_20260811T151545Z.json` |
| Hailo bring-up | Fail: no `hailortcli`, PCIe Hailo device, or Dataflow Compiler on this Windows host | `artifacts/hailo/bringup_20260813T014408Z.json` |
| Hailo compiler availability | Blocked: no compiler command/environment; candidate model SHA-256 captured | `artifacts/hailo/compile_20260812T230955Z.json` |

## Important contradiction

The synthetic generator pastes its target at the image centre. Centre crop winning
that experiment therefore does **not** justify centre crop for wide-area coverage;
it confirms pixel-size sensitivity only. A crop selection is intentionally not
made. The next run must include known off-centre targets and recorded camera imagery.

Full-frame resize performed worse than expected: it did not reach 50% detection in
this five-source sweep even at 64 px. This is a small, synthetic candidate-model
result—not a field detection floor.

## Recommendation

Do not deploy a selected crop mode yet. For the next controlled recording replay,
compare centre crop and tiles at 640 px with the same off-centre annotations; tiles
have the clear host-cost penalty in the existing artifact. Keep full-frame resize
as a negative-control path because it lost all measured 50% crossings here.

## Hailo and latency status

Hailo compilation is `NOT MEASURED`: the checked host has no Linux WSL distribution
and no Dataflow Compiler installation, while no Hailo device is present. The compiler
record script preserves the complete log and CPU-fallback result once a licensed
Linux compiler environment is available. Pi inference latency, utilization,
thermals, power, and quantized-output degradation remain `NOT MEASURED`.

Existing camera latency records are luminance-crossing proxies on this host, not
camera properties. Their exposure setting was not recorded as locked, so they do
not test the auto-exposure hypothesis. The revised procedure requires a bright
scene, short locked exposure, and the actual driver exposure setting before a rerun.

## Still unmeasured and unblockers

| Item | Status | Unblocker |
| --- | --- | --- |
| Hailo `.hef`, compiler log, CPU fallback, quantization comparison | `NOT MEASURED` | Linux x86 environment plus licensed compatible DFC suite and ONNX export |
| Pi/Hailo inference and thermal/power baseline | `NOT MEASURED` | Pi 5 + HAT+ accessible to an operator; follow `docs/procedures/hailo-setup.md` |
| Tracking continuity/dropouts/ID switches/reacquisition | `NOT MEASURED` | Timestamped recorded detection stream, with truth IDs for ID-switch/reacquisition measures |
| Bright locked-exposure latency sequence | `NOT MEASURED` | Bright scene, manually locked short exposure, and the camera-day procedure |
| Camera FOV/intrinsics/marked-range data | `NOT MEASURED` | Arriving global-shutter camera, target, marked distances, and `fov-measurement.md` |

## Verification

Full Python suite: **239 passed in 25.49 s**. Strict MkDocs build: **passed** in an
isolated environment. MkDocs reported existing pages omitted from navigation; these
are warnings, not strict-build failures.
