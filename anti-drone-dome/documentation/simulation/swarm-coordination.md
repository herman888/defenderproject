# Autonomous swarm coordination

The swarm layer adds an **airborne coordinator** — a higher-compute, longer-range RF
node — that directs a swarm of interceptors to autonomously defeat a **saturation
attack** of many simultaneous threats. It sits on top of the single-target
interception core without changing it.

The coordination brain is **substrate independent**: it operates only on ENU state
dicts (the same shape as `Drone.get_state()`) and never imports PyBullet. The same
brain runs in the fast headless point-mass runner and in the PyBullet mission.

## What it models

- **Physical coordinator.** A real airborne node whose position sets the RF range to
  every interceptor. It is a single point of failure — interceptors beyond its range
  lose command link.
- **RF datalink** (`swarm/rf_link.py`). One-way free-space path loss
  (`20·log10(range)`), a logistic margin→packet-loss curve, a hard maximum range, and
  range-dependent latency with a per-interceptor delayed-delivery queue. Deterministic
  given a seed.
- **Weapon-target assignment** (`swarm/assignment.py`). A cost matrix of expected
  time-to-intercept (reusing `PurePursuitGuidance.time_to_intercept`) feeds a
  priority-greedy allocator (highest-value threats covered first, so a saturation
  attack degrades by leaking the *least* dangerous threats). A numpy-only Hungarian
  solver is included as a cost-optimal alternative.
- **Autonomous re-tasking** (`swarm/coordinator.py`). Each interceptor is `ASSIGNED`,
  `COASTING` (link stale, still pursuing its last order), `AUTONOMOUS_LOCAL` (link lost
  and last target gone — self-selects the nearest threat), or `RESERVE`. The
  coordinator re-plans when threats are neutralised or appear, with hysteresis (a
  minimum dwell and a margin-to-switch) to prevent assignment thrash.

## Run it standalone (headless, fast)

```powershell
python swarm\runner.py --scenario saturation_6v4 --seed 42
```

Prints a deterministic evidence report: per-threat outcome and time-to-neutralise,
leakage, interceptors expended, re-tasking events, and RF link health. Options:
`--policy {greedy,hungarian}`, `--seed`, `--output report.json`,
`--telemetry-udp HOST:PORT`.

## Run it in PyBullet (real dynamics)

```powershell
python main.py --swarm saturation_6v4
```

A headless PyBullet engagement that reuses the real `Drone` dynamics and APN guidance
with the same coordination brain, and optionally streams telemetry via
`--telemetry-udp`. This mode deliberately bypasses the single-target command-center
HUD and tactical camera; it prints a debrief and (optionally) streams the swarm feed.

## Scenarios

`scenario_data/swarm_scenarios_v1.json` (schema `aegis.swarm-scenarios.v1`, validated by
`swarm/scenario.py`):

- **`saturation_6v4`** — six mixed threats vs four interceptors; the four highest-value
  threats are neutralised and the two lowest-value leak.
- **`overwhelm_8v3`** — a deliberate over-saturation (eight threats, three
  interceptors) that exercises priority triage and leakage reporting.

## Telemetry

`swarm/telemetry.py` publishes `aegis.swarm-coordination.v1`: coordinator, interceptor
list (position, assigned threat, link state, margin, energy), threat list (position,
priority, status), the live assignment map, and RF link health — a multi-track sibling
of [`aegis.tactical.v1`](../operations/mission-recording.md), reusing its validators.

## Boundaries

Representative, unvalidated envelopes — not a validated device or doctrine. RF,
compute, and airframe parameters are placeholders to be replaced with measured data.
The feed is local research telemetry, not an authenticated command channel.
