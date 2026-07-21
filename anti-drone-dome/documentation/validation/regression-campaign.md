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

- 8 scenarios
- 100 deterministic repeats per scenario
- 800/800 APN interceptions
- 96.3% Wilson lower bound for each perfect 100-episode scenario
- `compound-edge` highest on the performance watchlist at 55.3% limit
  utilization

These results verify repeatability in the current synthetic model. They are not
field reliability, certification, or a prediction of effectiveness.
