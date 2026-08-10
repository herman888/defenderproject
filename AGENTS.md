# AGENTS.md — scope guardrails for AI coding agents

Read this before proposing or writing code in this repository. It exists because
multiple agents and tools work on this project, and deferred scope has been
independently re-introduced more than once by agents that had no way to know it
was cut.

The authoritative plan is **`anti-drone-dome/docs-internal/PROGRAM_PLAN.md`**.
This file is the short version.

---

## What this project is

**Project LARP** is a layered counter-UAS system. The ground segment — radar, EO,
fusion, weapon-target assignment, operator command center — detects, tracks, and
commits. The airborne segment is a **low-cost kinetic quadcopter interceptor**
carrying a dual-mode seeker: a four-microphone acoustic array for wide-field
cueing and a strapdown EO camera for terminal lock, so it completes the
engagement even if the datalink degrades.

Everything is validated in a physics-based digital twin before any airframe
flies.

## What this project is NOT

- **No munitions.** One effector class only: the kinetic quadcopter.
- **No SDR or RF signal processing.** RF scope is *modelled only* — link budget,
  antenna selection, frequency plan, EW resilience, regulatory.
- **No jamming or electronic attack.**
- **No autonomous weapon release.** Human-on-the-loop commit is a design
  constraint. The seeker completes an engagement that was already authorised; it
  does not select targets.
- **No regulatory, range, or safety certification claims.**

---

## Deferred workstreams — do not build on these

Each is retained as a costed option, not live scope. **Do not extend, wire in,
add assets or VFX for, add hardware for, or cite these in external
documentation.** If a task seems to require one, stop and say so instead.

| Item | Where | Revisit trigger |
|---|---|---|
| Micro-rocket effector | `anti-drone-dome/sim/rocket_effector.py` | Monte Carlo shows quad-only defence failing a defined saturation case |
| MATLAB / Simulink | — | External funding, or a reviewer requires independent toolbox verification |
| PPO / RL residual guidance | `anti-drone-dome/ml/policy.py` | A measured scenario class where APN demonstrably underperforms |
| Unreal viewer development | `unreal/AegisTacticalViewer/` | A specific demo requirement the current packaged build cannot meet |
| Embedded Coder autocode | — | Flight hardware exists **and** the control law is changing weekly |

`anti-drone-dome/swarm/cpk_optimizer.py` **is** in scope — the cost-per-kill
question determines whether the rocket trigger ever fires.

The Unreal viewer is **frozen at current quality**: three packaged Win64 builds
already work. Fix bugs, but do not add rendering features, plugins, or content
pipelines to it.

---

## How work is judged here

1. **Perfect the chain, not a layer.** The unit of progress is one *complete
   engagement* — one real sensor, one real track, one real decision, one real
   intercept — measured end to end. A perfect simulator with no hardware is a
   video game; perfect hardware with no C2 is a toy drone.
2. **"Perfect" means measured, not beautiful.** A number with provenance beats
   clean code. Do not gold-plate.
3. **Calibrated honesty is the deliverable.** This project's documentation is
   unusually candid about its own limits, and that is its single biggest
   credibility asset with reviewers. Never inflate a claim to fill a gap — name
   the gap and state what would close it. Publish deltas, including ones that
   make results look worse.

---

## Conventions

- **Python is authoritative.** No tool may sit in the runtime or CI path.
- **Physical parameters carry an `evidence.status`** of `design-placeholder` or
  `measured`. Never silently promote one to the other; `validation/workbench.py`
  and `integration/tactical_stream.py` enforce this at runtime.
- **The Unreal viewer is receive-only.** There is no command path from the
  viewer back into the simulation. Do not add one.
- **Data contracts are versioned** (`aegis.*.v1`) and documented in
  `anti-drone-dome/documentation/system/data-contracts.md`. New interfaces get a
  schema name, not an ad-hoc dict.
- **Tests use `venv312`.** Run from `anti-drone-dome/`:
  `venv312\Scripts\python.exe -m pytest -q`
- **Do not commit `anti-drone-dome/data/`** (~353 MB of refetchable public
  datasets; gitignored).
- **Never commit secrets.** `anti-drone-dome/.env` is gitignored and must stay
  that way.

## Known constraints

See the program plan's credibility section. The swarm paths now use
`sensors/radar_batch.py:MultiTargetRadar`: scenario state is used only to create
noisy measurements, and the coordinator receives anonymous, Mahalanobis-gated
sensor tracks. Target type and threat priority are deliberately `unclassified` /
`MEDIUM` until a real classification path exists.

That removes the previous ground-truth injection, but it does **not** validate
swarm performance: the radar budget, measurement covariance, airframe profiles,
and contact geometry remain synthetic or placeholder evidence. Do not make a
field-performance claim from swarm results until a calibrated sensor-in-loop
campaign is published.
