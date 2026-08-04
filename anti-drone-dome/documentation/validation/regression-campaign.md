# Synthetic regression campaign

Run the complete named campaign:

```powershell
python scripts\run_regression_campaign.py `
  --repeats 100 `
  --seed 1000 `
  --output validation_reports\regression_campaign
```

The command writes:

- `regression_campaign.json`: full episode evidence and analysis
- `regression_campaign.csv`: compact per-scenario summary
- `regression_campaign.html`: human-readable release report

[Open the published HTML report](../assets/reports/regression_campaign.html) |
[Download the CSV summary](../assets/reports/regression_campaign.csv)

## Gate semantics

Each scenario can override:

- minimum Wilson-lower intercept rate
- maximum p95 mission duration
- maximum p95 energy
- maximum action-saturation fraction

The stress-factor section reports observed correlations only. It does not claim
that a factor threshold proves a root cause.

## Current powered result

8 scenarios, 100 deterministic repeats each, 800 episodes, APN controller.

| Scenario | Intercept rate | Wilson 95% lower | Gate | p95 duration | Result |
|---|---|---|---|---|---|
| `terrain-mask-low` | 100% | 96.3% | 95% | 15.7 s | pass |
| `baseline-direct` | 91% | 83.8% | 95% | 17.7 s | fail |
| `agile-pop-up` | 43% | 33.7% | 85% | 35.9 s | fail |
| `degraded-track` | 36% | 27.3% | 80% | 61.9 s | fail |
| `remote-launch` | 34% | 25.5% | 95% | 27.2 s | fail |
| `spiral-noisy` | 33% | 24.6% | 80% | 120.0 s | fail |
| `crosswind-crossing` | 11% | 6.3% | 95% | 120.0 s | fail |
| `compound-edge` | 9% | 4.8% | 70% | 120.0 s | fail |

**Overall: 357/800 interceptions (44.6%). 1 of 8 scenarios passes its gate.**

### Why this replaced a previously reported 800/800

An earlier revision of this page reported 800/800 interceptions with a 96.3%
Wilson lower bound on every scenario. **That result was measured with an 18 m
contact radius** — a proximity gate inherited from the cinematic viewer, not a
physical contact criterion. Scoring an 18 m near-miss as a kill made every
scenario succeed and made the campaign incapable of discriminating between them.

`INTERCEPT_CONTACT_RADIUS_M` is now **1.0 m**, representing actual physical
contact between a sub-metre interceptor and its target. The numbers above are
the same campaign, same seeds, same controller, re-measured against that
criterion.

The failures are the useful part. A stress campaign in which nothing ever fails
is not stressing anything, and the curve above is the first evidence in this
project that distinguishes an easy engagement from a hard one: a clean
low-altitude intercept is reliable, a crosswind crossing shot or a compound
maximum-stress case is currently not.

Three scenarios (`spiral-noisy`, `crosswind-crossing`, `compound-edge`) show a
p95 duration at the 120 s ceiling, meaning the dominant failure mode is
**timeout rather than miss** — the interceptor does not converge on the
collision triangle at all, rather than converging and missing narrowly. That
points at guidance and closing geometry, not at terminal accuracy.

### Gate status

The gates were calibrated against the 18 m radius and have **not** been
recalibrated. They are currently aspirational targets rather than achievable
pass thresholds, and the campaign therefore reports `release_ready: false`.
Recalibrating them to sit just under present performance would make the suite
pass without changing anything real; that has deliberately not been done.

These results verify repeatability in the current synthetic model. They are not
field reliability, certification, or a prediction of effectiveness.
