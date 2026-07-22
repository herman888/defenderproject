# Current evidence and honest claims

## Verified in this repository

| Area | Evidence |
|---|---|
| Tests | 35 tests passed after tactical-contract and replay hardening |
| Live mission | OpenGL tactical mission intercepted at approximately T+15.7 s |
| Visual dynamics | Timestamped frames changed 14.5% then 25.6% |
| Stress campaign | 800/800 APN synthetic interceptions across eight cases |
| Campaign confidence | 96.3% Wilson lower bound per 100/100 case |
| ML comparison | PPO preserved interception but did not outperform APN |
| Recording | Raw camera arrays removed from JSONL telemetry |
| External renderer | Georeferenced `aegis.tactical.v1` validation, JSONL capture, and exact UDP replay implemented |
| Companion contract | 10,000 read-only perception packets serialized at 41,274/s on the AMD64 development host |

## Environment-specific findings

The available NVIDIA Quadro T2000 accelerated OpenGL rendering, but the tested
Python environment contained a CPU-only PyTorch build. CUDA learning and
inference remain unavailable until a compatible CUDA-enabled wheel is installed
and verified.

The companion smoke result measures packet validation and serialization only.
It is not a Raspberry Pi, camera-capture, inference, thermal, or network
benchmark.

## Not yet verified

- real radar and EO timing under field conditions
- real vehicle dynamics identification
- hardware-in-loop command latency and loss behavior
- Betaflight actuation
- outdoor safety and regulatory approvals
- photorealistic Unreal/Cesium client

The project is a capable lab validation platform, not a certified field system.
