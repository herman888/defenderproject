# Current evidence and honest claims

## Verified in this repository

| Area | Evidence |
|---|---|
| Tests | 167 tests passed (`venv312\Scripts\python.exe -m pytest -q` from `anti-drone-dome/`) |
| Live mission | OpenGL tactical mission intercepted at approximately T+15.7 s |
| Visual dynamics | Timestamped frames changed 14.5% then 25.6% |
| Stress campaign | 380/800 APN synthetic interceptions across eight cases (47.5%), 1 of 8 gates passed |
| Campaign confidence | Wilson 95% lower bound per case ranges 6.3% (`compound-edge`) to 96.3% (`terrain-mask-low`) |
| Contact criterion | 1.0 m physical contact radius, replacing an inherited 18 m proximity gate |
| ML comparison | PPO preserved interception but did not outperform APN |
| Recording | Raw camera arrays removed from JSONL telemetry |
| External renderer | Georeferenced `aegis.tactical.v1` validation, JSONL capture, and exact UDP replay implemented |
| Fidelity smoke | Profile-driven 200 kg representative Shahed intercepted at T+60.6 s in a headless 8x mission |
| Companion contract | 10,000 read-only perception packets serialized at 41,274/s on the AMD64 development host |

## Environment-specific findings

The available NVIDIA Quadro T2000 accelerated OpenGL rendering, but the tested
Python environment contained a CPU-only PyTorch build. CUDA learning and
inference remain unavailable until a compatible CUDA-enabled wheel is installed
and verified.

The companion smoke result measures packet validation and serialization only.
It is not a Raspberry Pi, camera-capture, inference, thermal, or network
benchmark.

## Correction, 2026-08-04

This page previously reported **800/800 interceptions with a 96.3% Wilson lower
bound on every case**. That figure was measured with an 18 m contact radius — a
proximity gate carried over from the cinematic viewer, not a physical contact
criterion — which caused every scenario to score 100% and made the campaign
unable to distinguish an easy engagement from a hard one.

With `INTERCEPT_CONTACT_RADIUS_M = 1.0`, the same campaign, seeds, and
controller yield 380/800. The failures are the point: this is the first
evidence in the project that separates scenario difficulty. See
[the regression campaign](../validation/regression-campaign.md) for the
per-scenario curve and the gate status.

## Not yet verified

- real radar and EO timing under field conditions
- real vehicle dynamics identification
- hardware-in-loop command latency and loss behavior
- Betaflight actuation
- outdoor safety and regulatory approvals
- photorealistic Unreal/Cesium client

The project is a capable lab validation platform, not a certified field system.
