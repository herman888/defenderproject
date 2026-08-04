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
| `baseline-direct` | 92% | 85.0% | 95% | 17.7 s | fail |
| `agile-pop-up` | 45% | 35.6% | 85% | 35.9 s | fail |
| `remote-launch` | 43% | 33.7% | 95% | 27.2 s | fail |
| `degraded-track` | 37% | 28.2% | 80% | 61.9 s | fail |
| `spiral-noisy` | 33% | 24.6% | 80% | 120.0 s | fail |
| `crosswind-crossing` | 19% | 12.5% | 95% | 120.0 s | fail |
| `compound-edge` | 11% | 6.3% | 70% | 120.0 s | fail |

**Overall: 380/800 interceptions (47.5%). 1 of 8 scenarios passes its gate.**

Campaign runs are deterministic: repeated runs of the same seed set reproduce
these counts exactly.

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

Contact is also now evaluated over the **path travelled during each step**
rather than at its endpoints. An endpoint-only test misses any pass where the
step displacement exceeds the contact radius, and it disagreed with the reported
outcome: an episode terminated on a swept contact was reported as a miss
whenever the sampled endpoint separation was still outside the radius. Fixing
both recovered 23 episodes (44.6% → 47.5%), concentrated in `remote-launch`
(+9) and `crosswind-crossing` (+8).

The failures are the useful part. A stress campaign in which nothing ever fails
is not stressing anything, and the curve above is the first evidence in this
project that distinguishes an easy engagement from a hard one: a clean
low-altitude intercept is reliable, a crosswind crossing shot or a compound
maximum-stress case is currently not.

### Diagnosed failure mode: a terminal limit cycle

Three scenarios (`spiral-noisy`, `crosswind-crossing`, `compound-edge`) show a
p95 duration at the 120 s ceiling, so the dominant outcome is **timeout rather
than miss**. Instrumenting the guidance internals
(`scripts/diagnose_guidance_failure.py`) shows what that actually is, and it is
not a convergence failure:

```
t= 2.0s  R=1228m  Vc=+118.5  LOS=  0.37 deg/s  sat=0.04  ADAPTIVE_APN
t=10.0s  R= 201m  Vc=+118.3  LOS=  0.70 deg/s  sat=0.06  ADAPTIVE_APN
t=12.0s  R=  19m  Vc= -32.5  LOS=142.49 deg/s  sat=1.00  TERMINAL
t=30.0s  R=   9m  Vc= +10.0  LOS= 27.19 deg/s  sat=0.19  TERMINAL
t=66.0s  R=   9m  Vc= +11.7  LOS= 15.46 deg/s  sat=0.16  TERMINAL
```

**Midcourse guidance is sound** — line-of-sight rate is held below 2 deg/s from
1228 m to 201 m at 4-6% of available acceleration. The interceptor then
overshoots at ~118 m/s and settles into a stable orbit at 8-9 m that it does not
escape, spending 87% of the episode in `TERMINAL` mode.

The mechanism is structural to proportional navigation. The command is
`N' · Vc · lambda_dot`. Inside the orbit the closing speed collapses to ~10 m/s
while the line-of-sight rate climbs to 20-50 deg/s, so **the law commands least
authority exactly when the geometry is worst**: action saturation sits at
0.10-0.39 while the miss distance is on the order of a metre, leaving roughly
70% of available acceleration unused.

This is a terminal-phase problem, not a midcourse or sensing one. Candidate
directions, none yet implemented:

- switch laws in the terminal phase rather than continuing PN, whose
  line-of-sight rate diverges as range goes to zero by construction; a
  zero-effort-miss formulation nulls predicted miss before that singularity
- add break-off and re-attack behaviour, since orbiting for 100 s after an
  overshoot is not a behaviour a real system would have
- confirm the 1.0 m contact radius against airframe geometry: a ~0.35 m-span
  interceptor against a 2.5 m-span target implies a combined characteristic
  radius nearer 1.4 m, which must be justified dimensionally rather than tuned
  to pass

### Gate status

The gates were calibrated against the 18 m radius and have **not** been
recalibrated. They are currently aspirational targets rather than achievable
pass thresholds, and the campaign therefore reports `release_ready: false`.
Recalibrating them to sit just under present performance would make the suite
pass without changing anything real; that has deliberately not been done.

These results verify repeatability in the current synthetic model. They are not
field reliability, certification, or a prediction of effectiveness.
