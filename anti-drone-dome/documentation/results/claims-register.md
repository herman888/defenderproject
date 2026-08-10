# Claims register

This register is the only source for externally quotable numerical claims.
Every row links the statement to its exact artifact and criterion. A number
without a row here is not a claim.

| Claim text | Exact scenario or case | Contact criterion | Source artifact path | Seed | Date produced | Status |
| --- | --- | --- | --- | --- | --- | --- |
| APN achieves sub-20 cm intercept versus 51 to 748 m miss distance for naive pursuit | `fpv_attack` / `spiral` / mid-pad legacy comparison | **18 m cinematic proximity criterion; not rerun at 1 m** | `tests/test_apn_comparison.py` and `tests/diag_legacy_worstcase.py`; no committed result artifact records the quoted sub-20 cm value | UNVERIFIED | UNVERIFIED | **SUPERSEDED, RERUN REQUIRED** |
| 380 interceptions in 800 episodes across eight named cases; one of eight release gates passed | `terrain-mask-low`, `baseline-direct`, `agile-pop-up`, `remote-launch`, `crosswind-crossing`, `spiral-noisy`, `degraded-track`, `compound-edge` | 1 m simulated swept-contact criterion | `validation_reports/regression_campaign.json`; method `scripts/run_regression_campaign.py`; corrective provenance in commit `17f3788` | 1000 through 1799 | 2026-08-04 | **VERIFIED (synthetic only)** |

The first row must be rerun with the 1 m simulated criterion before it can be
quoted again. It must always travel with the full-campaign row above.
