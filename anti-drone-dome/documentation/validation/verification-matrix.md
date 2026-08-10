# Verification matrix

This matrix defines what each claim requires. It prevents a passing unit test,
attractive render, or training curve from being presented as field evidence.

| Claim area | Current evidence | Required next method | Exit artifact | Current decision |
| --- | --- | --- | --- | --- |
| Python simulation correctness | Current automated suite | Continuous headless test execution | JUnit result and passing-test count from CI | Software-ready |
| Documentation integrity | Strict local MkDocs build | Static deployment check | Successful public HTTP deployment and link check | Blocked: public Vercel URL is unavailable |
| Single engagement in simulation | Deterministic synthetic regression campaign | Seeded rerun after every model change | JSON/CSV/HTML campaign with Wilson intervals | Research evidence only; `release_ready: false` |
| Swarm coordination | Headless and live demonstrations | Multi-target sensor, association, and fusion in the loop | Sensor-in-loop campaign with leakage/error attribution | Not valid for performance claims |
| Guidance | APN, PD/ZEM/auto synthetic comparisons | Pre-registered calibrated-sensor comparison | Per-case result table and trajectory artifacts | APN remains nominal baseline |
| Radar | Closed-form detection model unit tests | Selected-hardware range test | Detection probability versus range/RCS/conditions | Budget values are placeholders |
| EO detection | Candidate workflows and historic fine-tuning outputs | Held-out recorded-camera evaluation | Frozen dataset manifest, PR curves, confusion matrix, latency report | No deployed model selected |
| Acoustic cueing | Architecture only | Bench → hover → forward-flight test | Detection-range/SNR and angular-error report | Not implemented |
| Vehicle dynamics | Representative profiles and synthetic motion | Flight-log or thrust-stand calibration | Residual/error report and measured profile revision | Not calibrated |
| Compute latency | Host serialization smoke result | Target-device thermal and latency test | p50/p95/p99 per-stage latency budget | Not measured on target hardware |
| Communications | Local simulation and SITL paths | Authenticated-link and loss-of-link HIL test | Protocol specification and HIL report | Local research only |
| Unreal presentation | Packaged local Win64 build and source automation tests | Automated compile, test, package, and replay smoke | Versioned package, SHA-256, test log, replay capture | Demonstration-ready, not release-automated |

## Evidence methods

- **A — analysis:** an independently reviewable calculation or model check.
- **T — test:** an automated or controlled procedure with a pass/fail result.
- **D — demonstration:** an observed integration behavior, recorded with
  timestamped state.
- **I — inspection:** a reviewed artifact such as a manifest, profile, or
  source-controlled configuration.

Every published result should identify its method, environment, input hashes,
seed where applicable, and limitations.
