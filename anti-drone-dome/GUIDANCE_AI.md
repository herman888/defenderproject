# Adaptive guidance and optional AI

The default interceptor controller is deterministic adaptive augmented
proportional navigation (APN). It recalculates navigation gain, command speed,
longitudinal response, and terminal blending from the current:

- relative position and signed closing speed;
- line-of-sight angular rate;
- estimated target acceleration;
- track confidence;
- target speed and remaining interceptor energy.

Those decisions are sent to Unreal as display telemetry. Unreal never computes
or sends flight commands.

## Learned policy boundary

`--ml-model PATH` can load a compatible Stable-Baselines3 PPO policy. By
default, its output is only a residual on top of adaptive APN:

- model output must be finite and is clipped to its trained action range;
- residual authority scales from 5% to 25% with track confidence;
- the combined command is capped to the configured acceleration envelope;
- invalid model output becomes zero residual;
- the adaptive velocity and yaw setpoints remain active.

Absolute ML actions remain an explicit research option
(`--ml-absolute-actions`) and are not used by the packaged demo.

This is still a software-in-loop training environment. The interceptor profile
is marked `design-placeholder` until measured mass, thrust, inertia, battery,
and flight-test data replace the representative values.

## Motion validation

After a recorded mission:

```powershell
python scripts\validate_unreal_motion_recording.py missions\renderer\unreal-demo.jsonl
```

The check fails unless both authoritative tracks move through at least 95% of
their engagement intervals.
