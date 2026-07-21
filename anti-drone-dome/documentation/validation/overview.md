# Validation workbench

Validation has three evidence layers:

1. Unit and integration tests for code-level behavior.
2. Deterministic synthetic campaigns for controller regression.
3. Hardware-readiness reports for SIL, log alignment, interfaces, and safety.

No layer converts synthetic results into certified real-world performance.

## Evidence outputs

| Output | Format | Purpose |
|---|---|---|
| Regression report | JSON, CSV, HTML | Scenario gates and reproducible episodes |
| Hardware report | JSON, HTML | SIL/HIL readiness and blockers |
| Mission record | JSONL + manifest | Time-series state, events, result, hashes |
| Replay | ACMI | Tacview-compatible post-mission review |
| UI captures | PNG + state JSON | Visual and state-synchronization evidence |

## Statistical rule

Intercept gates use the lower bound of a two-sided 95% Wilson interval rather
than the point estimate. A small perfect sample can therefore fail an evidence
gate even when its observed intercept rate is 100%.

