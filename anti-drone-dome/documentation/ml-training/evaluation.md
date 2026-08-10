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

The included curriculum policy completed 106,496 transitions. The archived APN
and residual-PPO comparisons used the former broad proximity criterion, so their
100/100 result is not current controller evidence after the physical 1 m contact
criterion was adopted.

Therefore:

- no current ML performance advantage is claimed;
- residual-PPO training is deferred until a calibrated sensor-in-loop scenario
  demonstrates a repeatable APN limitation;
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

