# Controller evaluation

## Held-out benchmark

```powershell
python scripts\benchmark_controllers.py `
  --procedural `
  --episodes 100 `
  --model models\interceptor_ppo_curriculum_v2.zip `
  --output reports\apn_vs_curriculum_v2
```

Reports include every episode plus CSV aggregates for intercept rate, closest
approach, duration, energy, reward, and action saturation.

## Current interpretation

The included curriculum policy completed 106,496 transitions. APN and residual
PPO both intercepted 100/100 held-out maximum-difficulty procedural scenarios.
A larger paired 100-seed analysis found residual PPO slightly slower and more
energy-intensive than APN with non-overlapping bootstrap intervals.

Therefore:

- residual PPO preserves the tested APN interception baseline;
- no ML performance advantage is claimed;
- training reward alone is not accepted as deployment evidence;
- APN remains the nominal safety controller.

## Sim-to-real gates

Before flight use:

1. identify dynamics from approved flight logs;
2. replay representative radar and EO recordings;
3. validate coordinate frames, latency, and clock alignment;
4. pass SIL and HIL gates on the target compute;
5. retain command limits and independent abort paths;
6. complete safety and range review.

