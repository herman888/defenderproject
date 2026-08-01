# Project LARP — Program Plan

> **Internal document. Not published in the MkDocs site nav.**
> Single source of truth for scope, staging, and open engineering work.
> Created 2026-07-31. Re-cut 2026-08-01 around a single-engagement focus.
> Update the **Status** column in §3 and the **Deferred** table in §4 as things move.

---

## 1. Strategy

### 1.1 What we are

> **Project LARP is a layered counter-UAS system with a clean authority split. The ground segment — radar, EO, fusion, weapon-target assignment, and the operator command center — detects, tracks, and commits. The airborne segment is a low-cost kinetic interceptor carrying its own dual-mode seeker: a four-microphone acoustic array for wide-field cueing and a strapdown EO camera for terminal lock, so the interceptor completes the engagement even if the datalink degrades.** The system is validated in a physics-based digital twin with a published regression campaign before any airframe flies.

That last clause is the pitch: **the ground segment hands over a cued volume; the seeker closes the loop autonomously.** It answers "what happens when you jam the link," it justifies onboard compute on its own merits, and it is what makes this a system rather than a drone with a camera.

### 1.2 The focus doctrine

The failure mode for this project is not running out of ideas — it is having too many. The repo already spans a simulator, a swarm coordinator, an Unreal viewer, RL training, vision training, a rocket effector, and a hardware track. That breadth reads as unfocused to a reviewer and is unaffordable for a small team.

**Three rules govern what gets worked on:**

1. **Perfect the chain, not a layer.** A perfect simulator with no hardware is a video game. Perfect hardware with no C2 is a toy drone. The unit of progress is one *complete engagement* — one real sensor, one real track, one real decision, one real intercept — measured end to end. A crude version of the whole chain beats a polished version of any single link.
2. **"Perfect" means measured, not beautiful.** A number with provenance beats clean code. Do not gold-plate.
3. **Anything not on the chain gets a written trigger, not a backlog slot.** See §4. A deferred item with a stated revisit condition is a defensible answer to a reviewer; an item sitting in a backlog is scope you are still paying for.

**Why this focus is de-risked:** Stage 1 — sensing, tracking, C2, and an honest P<sub>k</sub> curve — is sellable on its own. Detect-and-track is a product without an effector, and the simulator is a product as a C-UAS test-and-evaluation platform. If the interceptor slips two years, there is still a company. That is not true of any deferred item in §4.

### 1.3 What we are not

State these explicitly in every external document:

- No RF signal interception or SDR-based detection. **RF scope is modelled only** — link budget, antenna selection, frequency plan, EW resilience, regulatory.
- No jamming or electronic attack.
- No autonomous weapon release. Human-on-the-loop commit is a design constraint; the seeker completes an engagement that was already authorised, it does not select targets.
- No munitions. We are an **aircraft** programme, not an explosives programme — see §4.1 for why that line is load-bearing.
- No regulatory, range, or safety certification.

### 1.4 Committed decisions

| Decision | Value |
|---|---|
| Effector | Kinetic quadcopter interceptor. One effector class. |
| Seeker | Onboard acoustic array (cue) + strapdown EO (terminal), fused |
| RF | Modelled only — no SDR, no signal processing |
| Interceptor compute | Jetson Orin Nano 8GB |
| Coordinator compute | Jetson Orin NX 16GB |
| Sim performance target | 20 interceptors vs 50 threats, RTF ≥ 1.0 live / ≥ 5× headless |
| Auth | Cloudflare, owned by Herman. We define the public/gated split only. |

---

## 2. Credibility defects to close first

These block handing documentation to any specialist. If a reviewer finds them first, the room is lost.

**2.1 — The swarm runs on omniscient sensors.** `main.py:2095-2100` and `swarm/runner.py:135-138,195` feed **ground-truth** positions and velocities straight into `coordinator.plan()`. The cause is structural: `sensors/radar.py:RadarNode.scan()` handles exactly one target — one `self._tracker`, one `_locked`/`_hits`/`_miss_count` state machine. The headline "coordinated swarm vs saturation attack" claim currently has no sensing in the loop. **No swarm claim belongs in any document until this is fixed.** Status: OPEN.

**2.2 — Test count stated three ways.** `implementation-status.md:31` says 99; `results/current-evidence.md:7` says 42; the suite is now **136**. Fix: CI emits the count as an artifact; docs cite the artifact, never a hand-typed number. Status: OPEN.

**2.3 — Live Roboflow API key in `anti-drone-dome/.env`.** Gitignored and untracked, so it likely never reached a remote, but it has been read — **rotate it.** Remove the retrieval commands from `.claude/settings.local.json:147-148` and fix `documentation/development/gpu-setup.md:25`. Status: OPEN.

**2.4 — MEGAPROMPT_V2/V3/V4 linked from the published nav.** AI build prompts, currently in main navigation — the loudest "vibe-coded" signal on the site. Move to `docs-internal/`. Status: OPEN.

**2.5 — Stale content.** macOS paths (`/Users/hermanisayenka/...`) in `anti-drone-dome/README.md`; `Side Projects\anti-drone-dome` in `MEGAPROMPT.md`; `Python 3.14.2` in `reference/detection-pipeline-reference.md` (venvs are 3.12). Status: OPEN.

**2.6 — No CI, no packaging, no lockfile.** The only workflow belongs to vendored `gym-pybullet-drones`. No `pyproject.toml`, so imports are cwd-dependent. `requirements.txt` is `>=`-only. Status: OPEN.

**A judgment call worth stating:** the 800/800, 8-for-8 regression campaign is presented as a strength. A campaign nothing ever fails is not stressing anything. Closing 2.1 will lower measured intercept rates — **publish that before/after deliberately.** A result that got worse for a principled reason is stronger evidence than one that was always perfect.

---

## 3. Stage ladder — cut along the engagement chain

Each stage completes *more of one engagement*, rather than polishing one layer. Every exit gate is a published artifact, not an opinion. TRL claims are per-subsystem, never system-wide.

| Stage | The chain link it closes | Exit gate (the artifact) | TRL | Status |
|---|---|---|---|---|
| **S0** | Foundation | CI green per commit; determinism harness passes; §2 defects closed; docs split public/gated | — | not started |
| **S1** | **Sense → track, for real** | Multi-target radar + association replacing ground truth; 20v50 headless RTF ≥ 5×; Monte Carlo P<sub>k</sub> curve with real failures and Wilson intervals | 4 | not started |
| **S2** | **Seeker in the loop (simulated)** | `sensors/acoustic.py` + `sensors/eo_seeker.py` → existing `TrackFusion` → existing APN. Answers: what acoustic range is needed, what CV dropout breaks the intercept, how much link loss the seeker absorbs | 4 | not started |
| **S3** | **Seeker on the bench** | Measured acoustic detection-range-vs-SNR on a hovering airframe; measured glass-to-command latency on Orin Nano. **Go/no-go on the differentiator.** | 4–5 | not started |
| **S4** | **One airframe** | Interceptor CAD + itemised mass budget + integrated seeker; sim profiles flip `evidence.status` to `measured` | 5 | not started |
| **S5** | **One captive-carry engagement** | Flight-log-identified dynamics replacing `design-placeholder`; HIL loss-of-link and latency qualification | 5–6 | not started |
| **S6** | **One live intercept** | Range-safety-approved intercept of a cooperative target, telemetry-recorded end to end | 6 | not started |

**S3 is the real gate.** The acoustic seeker is the differentiator, and whether it works from a *moving* airframe is genuinely unknown (§6.2). Do not freeze CAD around a mic array before the bench test. If acoustics underperforms, the architecture degrades gracefully — acoustics becomes a break-lock recovery sensor rather than the primary cue — but that must be known before S4, not after.

Publish as `documentation/system/roadmap.md` with cost and schedule per stage, and an explicit statement of what is funded versus proposed.

---

## 4. Deferred workstreams — with triggers, not backlog slots

Each item below is **out of scope until its trigger fires**. This section is an asset: "we modelled it, here is the condition under which we would add it" is a stronger answer to a reviewer than either building it or having no view.

| # | Item | Trigger to revisit |
|---|---|---|
| 4.1 | Micro-rocket effector | Monte Carlo shows quad-only defence fails a defined saturation case |
| 4.2 | MATLAB / Simulink toolchain | External funding, **or** a reviewer specifically requires independent toolbox verification |
| 4.3 | PPO / RL residual guidance | A measured scenario class where APN demonstrably underperforms |
| 4.4 | Unreal viewer development | A specific demo requirement the current build cannot meet |
| 4.5 | Embedded Coder autocode | Flight hardware exists **and** the control law is changing weekly |

### 4.1 Micro-rocket effector — deferred

`sim/rocket_effector.py` models a 2.2 kg boost-sustain rocket to ~Mach 1.6 with a 4 m fragmentation radius at ~$1,800/unit. The code is correct and tested (23 tests in `tests/test_new_effector_modules.py`). **It stays out of S1–S6 for a reason that is not scope:**

- **It changes what company we are.** A quadcopter that rams a drone is an *aircraft* — Part 107-adjacent, a test field, props off, a writable safety case. A supersonic rocket with a fragmentation warhead is a *munition* — ITAR, explosives licensing, a range with a surface danger zone, different customers, different investors, different hires. A pre-seed team cannot be both, and `hardware/safety.md`'s "props removed, actuation disabled" posture does not survive contact with a rocket motor.
- **It inverts the cost story.** The pitch is "cheaper than the threat it defeats." At $1,800 expended against a $500 decoy, it is not.

**Keep `swarm/cpk_optimizer.py` in scope regardless.** The cost-per-kill question is the differentiator, it is answerable in simulation today, and it is precisely what determines whether 4.1's trigger ever fires.

### 4.2 MATLAB / Simulink — deferred, with a Python path that gets most of the value

For a funded programme the independent cross-verification story is worth ~$15k of licences. At pre-seed it is not, yet. **Do the physics in Python instead:**

- `sensors/radar_model.py` — the radar range equation plus Shnidman's P<sub>d</sub>(SNR, P<sub>fa</sub>, N, Swerling) approximation. ~150 lines, no licence, runs in CI. This replaces the hand-drawn piecewise curve at `sensors/radar.py:360-372`, which has no radar equation behind it: no transmit power, no antenna gain, no wavelength, no noise figure, no integration gain, and a `false_alarm_probability` that is a free scenario parameter rather than derived from a detection threshold — **so P<sub>d</sub> and P<sub>fa</sub> are currently decoupled, which is physically impossible.**
- Cross-check APN against a closed-form analytic solution for a non-maneuvering target — free, and a stronger check than a Simulink block diagram of the same algebra.
- Verify WTA against a reference solver in a test, not at runtime.

What MATLAB would still buy later, in priority order: Phased Array System Toolbox once we model an actual antenna aperture and beam scheduling for 50 tracks; Sensor Fusion & Tracking for multi-target association; Simulink + Aerospace Blockset for a real 6-DOF plant with Dryden turbulence. **When it does come back, the rule is absolute: MATLAB produces committed offline artifacts, and is never in the runtime or CI path.** A ~1 ms `matlab.engine` round trip would destroy the entire §5 performance budget and make a licence a hard dependency for every contributor.

### 4.3 PPO / RL residual — parked

`documentation/ml-training/evaluation.md` already records that PPO **did not outperform APN**. That is our own evidence that the track is not paying. Keep `ml/environment.py` — it is the Monte Carlo substrate and earns its place. Park `ml/policy.py`, the residual authority path, and further training runs.

### 4.4 Unreal viewer — frozen at current quality

Three packaged Win64 builds exist and work. It is a genuine sales asset with near-zero engineering value. Ship what exists; stop investing.

---

## 5. Workstream A — simulation performance and scale

Target: **20 interceptors vs 50 threats; RTF ≥ 1.0 with the live command center; ≥ 5× headless; ≥ 10× Monte Carlo.**

Reproduce the baseline with `venv312\Scripts\python.exe scripts\measure_perf_baseline.py`; committed output in `reports/perf/baseline_pre_refactor.json`. Figures are from an i7-9750H / Python 3.12.2 / NumPy 2.4.6 host — **host-relative, so re-run rather than comparing across machines** (the report records `host_normalization_us` for scaling). Run-to-run variance is roughly ±20%; treat sub-2× changes as noise.

**Measured end-to-end headless RTF today:** `saturation_6v4` (4v6) = **14.8×**; `overwhelm_8v3` (3v8) = **16.5×**. An earlier figure of 4.6× was measured under cProfile, which inflates microsecond-scale NumPy calls 3–5×. **A profiled RTF is not a baseline.**

| Call | Cost | Cause |
|---|---|---|
| `guidance/intercept.py:compute_guidance` | **~275 µs** | `np.cross` on 3-vectors = 26 µs each (×2); `np.clip` on Python scalars = 4.3 µs each (~16) |
| `swarm/assignment.py:build_cost_matrix` @20×50 | **60.6 ms** | nested Python loop calling `time_to_intercept` (60 µs) per cell |
| `swarm/assignment.py:hungarian_assignment` @20×50 | **50.8 ms** | numpy-scalar indexing in the Kuhn-Munkres inner loop |
| `sensors/radar.py:KalmanTracker.step` | **~50 µs** | per-track F/H/Q/R copies; dense 3×9 matmuls implementing a pure selector |
| PyBullet `stepSimulation` @70 bodies | 50.8 µs | the solver is **not** the bottleneck |
| PyBullet Python API round trip | **1.65 µs** | ~19 calls/vehicle/step → ~2 ms/step at 70 entities, 43× the solver cost |

The primitives make the vectorisation case in three numbers: `np.clip` on a Python scalar costs **15×** a plain `min/max` clamp; `np.linalg.norm` on a 3-vector costs **19×** a `math.sqrt`; and `np.cross` on **1000 rows costs only 1.3× what it costs on 3 elements**. Almost all of it is interpreter dispatch, not arithmetic — so batching is nearly free and scalar NumPy is pure overhead.

**The scaling wall is WTA.** At 4v6 the assignment cost is irrelevant. At 20v50 it is ~110 ms per plan call, and `main.py:2106` calls `plan()` at 240 Hz — **~26 s of compute per simulated second from one subsystem.**

**Key structural finding:** PyBullet is not the bottleneck and the vehicles do not need it. `sim/drone.py:_compute_vtol` (444) and `apply_setpoint` (635) call `resetBasePositionAndOrientation` + `resetBaseVelocity` every step — orientation overwritten, angular velocity zeroed, rotor torques discarded. Bullet supplies translational Euler integration and nothing else for the swarm tier. What it legitimately supplies — terrain/building collision and the rendered EO camera — matters for exactly one engagement at a time.

**A1 — free wins (~2–3 days, no architecture change, all tests pass unchanged)**
1. `guidance/_fastmath.py` — scalar `cross3`/`norm3`/`clamp`/`dot3`; mechanically replace `np.clip`-on-scalars and `np.cross`-on-3-vectors in `_adaptive_parameters`, `_lead_solution`, `_confidence`, `compute_guidance`, `_cap_accel`. Behaviour-identical; expect **275 → ~60 µs**.
2. **Rate-gate `SwarmCoordinator.plan()` to 10 Hz** with an internal cache. It runs at 240 Hz but the coordinator is datalink-limited to 10 Hz (`_offer_interval_s`, line 81) — re-solving WTA at 240 Hz was never physically meaningful. **~24× on its own.**
3. Replace `threat_ids.index()` O(N) scans in `coordinator.plan` (136-137) with the `threat_by_id` dict already built at line 109.
4. `Drone.get_state` → 2 API calls + per-step memo; gate `_spin_rotors` on GUI/Tier-0.
5. Exploit `H = [I|0|0]` in `KalmanTracker.step` — `H@x` is `x[:3]`, `H@P@H.T` is `P[:3,:3]`. 50 → ~30 µs; applies even unbatched.
6. Add `sim/perfcounters.py` + `scripts/profile_engagement.py`.
   *Gate:* re-run `measure_perf_baseline.py --label after-a1`. `compute_guidance` ≤ 100 µs, 4v6 RTF ≥ 25×, existing tests green.

**A2 — batched kernels (~1–2 weeks).** `guidance/intercept_batch.py` (`apn_batch` over `(N,3)`, `compute_guidance` becomes an N=1 wrapper so callers are untouched); `sensors/kalman_batch.py` (`x (N,9)`, `P (N,9,9)`, shared F/Q/R, batched LAPACK `inv` on `(N,3,3)`, **keeping the Joseph form** — the PSD-stability comment at `radar.py:88-94` is load-bearing); `swarm/assignment_batch.py` (**preserving the deterministic id-string tie-breaks** pinned by `tests/test_swarm_assignment.py`); `sim/kinematics.py:resolve_contacts` replacing the O(N·M) loops at `main.py:2142` and `swarm/runner.py:255`. Each ships with an equivalence test.

**A3 — fidelity tiers + rate groups (~2–3 weeks).** `sim/fidelity.py`: **Tier 0 FULL_RIGID** (PyBullet, engagement of interest — terrain collision + rendered EO), **Tier 1 REDUCED_6DOF** (batched port of `_resolve_vtol_thrust`/`_condition_force`/`_limit_force`, swarm default), **Tier 2 POINT_MASS** (Monte Carlo). Promote on entering the contact window (< `taper_range` ≈ 125 m) or operator camera focus. Gate: same seeded 4v6 Tier 0 vs Tier 1, trajectory RMSE < 2 m over 30 s, reusing `validation/flight_log.py:compare_flight_logs` and the `maximum_trajectory_rmse_m` gate in `hardware/profile.py`. Plus `sim/params.py` (kill the per-vehicle `deepcopy`), `sim/scheduler.py` rate groups, `PhysicsWorld(visuals=False)` for headless.

**A4 — real sensing, determinism, Monte Carlo (~2–3 weeks).** This is **S1**. `sensors/radar_batch.py:MultiTargetRadar` with batched beam/Doppler/detection and **data association** (Mahalanobis-gated Hungarian using `KalmanTracker.P[:3,:3]`); `TrackFusion.update_batch`; **remove ground-truth injection** (§2.1). Then `sim/runconfig.py` (frozen `RunConfig` replacing `main.py` module globals at 57-76, which block Monte Carlo workers) and `sim/determinism.py` + `scripts/check_determinism.py`.

Determinism bugs to fix: unseeded global `random.uniform` wind gusts (`main.py:941-943`); `RenderedCameraSensor` gets **no seed at all** (`main.py:656`); `RadarNode`'s seed derives from **dict insertion order** in `scenarios.py` (`main.py:648-651`), so adding a scenario silently changes every historical seed; `time.time()` leaking into state via `Drone.get_state` (`sim/drone.py:674`), `dome/killzone.py:40,73,77,80`, `sensors/radar.py:332,403`. Pin `setPhysicsEngineParameter(deterministicOverlappingPairs=1, ...)` and `OMP_NUM_THREADS=1` in workers. Note honestly: vectorisation changes float reduction order — version the baseline as `determinism_schema: v2` rather than pretending bit-equality survives.

Then `scripts/run_monte_carlo.py`, and parallelise `scripts/run_regression_campaign.py` (strictly serial today at `--repeats 100`, every episode already independently seeded — a `ProcessPoolExecutor` away from near-linear scaling).

**A5 — scale-out.** Extend `scenario_data/swarm_scenarios_v1.json` (max today `overwhelm_8v3`) with `saturation_50v20`, layered waves, mixed-RCS cases, and a spawn-distribution schema field.

**Foundation, first:** GitHub Actions CI for `anti-drone-dome`, a `pyproject.toml`, and a pinned lockfile. Add `tests/test_perf_budget.py` marked `@pytest.mark.perf`, host-normalised.

---

## 6. Specialist work packages

Each is a directory under `documentation/specialists/`, self-contained, structured identically: **Scope → Interfaces → Current state (with file paths) → Deliverables → Acceptance criteria → Open questions we cannot answer without you.** The last section is what makes it a work package rather than a brochure.

### 6.1 Simulation — `documentation/specialists/simulation/`

Hand over `system/architecture.md`, `system/data-contracts.md` (7 versioned schemas, only `aegis.tactical.v1` has a formal JSON Schema — the rest should get one), §5, and the **measured-vs-assumed parameter register**: every physical constant in the sim, its value, its provenance (measured / datasheet / estimated / placeholder), and what would upgrade it. That register is the single most reviewer-persuasive document available, and it can be produced in a week.

Deliverables: validated 6-DOF replacing the placeholder FC, error budgets, Monte Carlo methodology with confidence intervals, V&V matrix mapping requirement → method (A/T/D/I) → evidence artifact.

### 6.2 Acoustic seeker & embedded DSP — `documentation/specialists/acoustics/`

The differentiator, and the highest-uncertainty item in the programme. Gates S4.

Deliverables: array geometry with the aliasing/resolution trade resolved; measured own-noise spectra at throttle sweep with the actual props; adaptive notch design driven by bidirectional DShot RPM; windscreen and vibration isolation (with §6.4); a **measured detection-range-vs-SNR curve** replacing the asserted 10–50 m; angular accuracy vs SNR and off-boresight angle; the `aegis.acoustic-cue.v1` frame spec with a jitter bound.

Open questions we cannot answer alone: what detection range is achievable from a *moving* airframe? Can adaptive notching recover enough SNR against broadband prop noise, or is the useful band narrower than 1–8 kHz? Does a 2 cm alias-free array retain enough angular accuracy after sub-sample interpolation to cue a 40° camera FOV?

### 6.3 RF — `documentation/specialists/rf/`

Lead with the scope discipline: **modelled RF only, no SDR.**

Current state: `swarm/rf_link.py:71` is `margin_db = link_budget_margin_db + 20·log10(max_range/r)` — FSPL *slope* only. **No frequency term**, so it cannot distinguish 900 MHz from 5.8 GHz; no antenna gain or pattern; no polarisation loss; no two-ray ground reflection (which dominates below ~50 m AGL and directly affects the coordinator↔interceptor link); no noise floor or receiver sensitivity. `packet_loss_probability` (line 77) is a logistic curve-fit standing in for a BER-vs-Eb/N0 curve.

Deliverables: frequency plan and regulatory posture (ISM vs licensed, ISED/FCC, coexistence with the threat's own control links); link budget → `margin_dB(range, altitude, attitude)`; antenna selection with gain-vs-angle patterns so margin becomes attitude-dependent; **EW resilience** — J/S vs jammer power/range/antenna discrimination, burn-through range, loss-of-link behaviour contract (no Python analogue today, and directly load-bearing for a C-UAS story); authenticated datalink spec (HMAC-SHA256 + monotonic nonce + replay window for telemetry, mTLS for command, separate safety-gated path).

Sim-consumed artifact: `sensor_models/rf_link_budget_v1.json`; `RfLinkModel.from_budget_table(path)` replaces the closed form. Acceptance: free-space case matches closed-form FSPL to ±0.05 dB; publish the delta between the current `20log10` model and two-ray at 10/50/200 m AGL.

### 6.4 CAD / mechanical — `documentation/specialists/cad/`

Be blunt: **there is currently zero mechanical design.** No STL/STEP/F3D, no PCB, no schematic, no BOM. `assets/` holds only CC-BY Sketchfab visual models. The interceptor exists as `scenario_data/airframe_profiles_v1.json` with `evidence.status = "design-placeholder"`. Saying so plainly is stronger than implying otherwise.

Deliverables: **itemised mass budget** replacing the lumped `rigid_body.mass_kg = 1.5`, with `validate_airframe_profile` asserting components sum to gross mass within 1 g — so seeker and compute mass propagate automatically into `Drone._mass_kg` (`sim/drone.py:203`), `_hover_ff`, and every acceleration in `_resolve_vtol_thrust`; airframe CAD (STEP + native); propulsion selection with thrust-stand data; CG and inertia tensor replacing placeholder `[0.045, 0.045, 0.08]`; acoustic array integration (tetrahedral mounting, vibration isolation, windscreens); thermal design for Orin Nano at altitude and airspeed; launch/recovery; manufacturability and unit cost.

Sanity check to hand them: `energy_capacity_wh = 180.0` on a 1.5 kg vehicle implies ~0.9 kg of Li-ion at 200 Wh/kg — 60% of gross mass. Separately `swarm/runner.py:35` hard-codes `_INTERCEPTOR_ENDURANCE_S = 180.0` and never consults the profile. Reconcile both from the mass budget.

---

## 7. The onboard seeker — settled design decisions

Corrections to the original "cue-and-review" draft. **Settled — do not relitigate.**

### Fuse, don't mode-switch

A SEARCH↔TRACK state machine chatters at the boundary and discards acoustics exactly when the target is closest and most likely to break lock. Instead feed both sensors into the existing `sensors/fusion.py:TrackFusion` with real angular covariances — acoustic σ ≈ 5–15° omnidirectional, EO σ ≈ 0.2° over a 40–60° FOV. **The mode switch falls out of the weights.** Keep an explicit COAST (propagate last LOS rate) rather than snapping back to wide search.

### The seeker outputs LOS rate, not a pixel PID

A pixel-offset P-loop is **pursuit guidance**, with materially worse miss distance than PN against a maneuvering target, and its gain silently changes meaning if resolution or lens changes. Convert centroid → angular error via focal length → **body-rate-compensated** LOS rate (subtracting own-body rotation from the FC gyro is the #1 strapdown seeker bug) → the existing APN. Onboard terminal guidance then *is* simulated guidance, so the regression campaign already covers it.

### Specific corrections

| # | Issue | Correction |
|---|---|---|
| 1 | 15 cm mic spacing aliases above ~1.14 kHz; target band is 1–8 kHz | ~2 cm spacing (alias-free to ~8.5 kHz) with sub-sample GCC-PHAT interpolation (~0.1 sample ≈ 1–2° at broadside), or a sparse array. §6.2 owns the trade. |
| 2 | Planar cross cannot separate above-plane from below-plane | **Tetrahedral array** — same four mics, unambiguous 3D |
| 3 | `atan2(y, x)` from the L/R pair gives azimuth from the right axis, CCW | Aviation azimuth is from the nose, CW: `atan2(right, forward)`. State the Δt sign convention. |
| 4 | No propagation-lag compensation | 146 ms at 50 m → **~5° systematic trailing bearing error** for a 30 m/s target, plus own-motion during the correlation window |
| 5 | Own-noise is −60 to −70 dB SNR; broadband prop noise covers the whole target band | Notches must **track RPM** → bidirectional DShot telemetry to the Teensy. The 10–50 m range is an assertion; settle it with the S3 bench→hover→forward-flight experiment. |
| 6 | Wind noise scales steeply with airspeed | Windscreens and recessed/ported mounting → §6.4 |
| 7 | MOG2 background subtraction assumes a static camera | Use the trained YOLO detector (`models/finetuned/`, `integration/vision_model.py`, ~50k images). Motion tracker only as an inter-frame fallback. |
| 8 | "Pi 5 at 30–40 FPS for YOLOv8n" is not accurate (~5–8 FPS at 640×640) | Orin Nano + TensorRT INT8 |
| 9 | Both sensors are bearing-only → range unobservable | Uplink the ground radar track as the range channel; `guidance/passive_optical.py` provides a degraded bbox-height fallback, explicitly flagged `range_observable: False` |
| 10 | ASCII serial framing; prose says 100 Hz, `delay(50)` gives 20 Hz | Versioned binary frame with CRC16 + monotonic sequence (`aegis.acoustic-cue.v1`); one rate, with a measured jitter bound |

**Teensy 4.1 is a good choice** — 600 MHz M7 with CMSIS-DSP, two I2S buses for four ICS-43434s, deterministic DMA. A 1024-pt real FFT is ~50–100 µs; ~1.5 ms/frame total, so 100 Hz is ~15% duty. Keep acoustics off the Nano so a CV stall cannot blind the cue path.

---

## 8. Onboard compute

**8.1 Requirements — `documentation/hardware/onboard-compute.md`,** a spec with a **verification method per requirement** (A/T/D/I). Hard thresholds: sustained ≥ 60 fps post-throttle, glass-to-command p99 ≤ 30 ms, jitter σ ≤ 3 ms, mass ≤ 200 g, power ≤ 15 W, unit cost ≤ $X. Derive the 60 fps from closing rate and terminal geometry in `guidance/intercept.py:_adaptive_parameters` — it is the requirement most likely to decide the trade.

The latency budget must be **glass-to-actuator end to end**: exposure → readout → inference → centroid → body-rate compensation → LOS rate → APN → MSP/MAVLink → FC rate loop, each hop with a p99 budget and a measurement method. The acoustic path gets its own parallel budget (I2S frame → FFT → GCC-PHAT → serial frame → fusion). A single end-to-end number with no breakdown collapses under one question.

**8.2 Benchmarks.** `bench/jetson/bench_trt_latency.py`, `bench_glass_to_guidance.py`, `bench_thermal_soak.py`. Results land in `scenario_data/airframe_profiles_v1.json` and flip `evidence.status` toward `measured`.

**8.3 Make the sim reflect the vehicle.** Itemised `mass_budget_kg` (§6.4). New `sim/power_budget.py:HotelLoad` — `Drone._condition_force` (570-585) models only mechanical propulsion energy and has **no avionics hotel load**; adding it makes state-of-charge → thrust derating reflect compute draw, so endurance changes when compute changes. Deliverable: `scripts/plot_endurance_vs_compute.py` → loiter endurance and terminal Δv vs compute power and mass. **That one chart is the trade study made visible.**

**8.4 Selection.** Orin Nano 8GB on the interceptor (~40 TOPS, 7/15 W, ~130–200 g integrated, ~$250–400); Orin NX 16GB on the coordinator (recoverable, 20-interceptor fusion + WTA, a genuine 100 TOPS non-expended workload). Keep Pi 5 + Hailo-8L (~$150, ~110–160 g) in the trade study as the cost floor and **actually bench it** — cheaper than being wrong about a 10% mass fraction. Publish `compute-trade-study.md` with weights declared **before** benchmarking (latency p99 25%, sustained post-throttle 20%, mass 20%, cost 15%, power 10%, ecosystem 10%), a sensitivity analysis, and a decision record with a revisit trigger. Feed both candidates into the sim as two airframe profiles and let Monte Carlo show the intercept-rate delta.

---

## 9. Verification

- **CI (new):** GitHub Actions on `anti-drone-dome` — `pytest -q` headless, `mkdocs build --strict`, `check_determinism.py` on 2–3 scenarios, `test_perf_budget.py`. CI emits the test count as an artifact; docs cite it.
- **Performance:** `scripts/perf_sweep.py` over `Ni ∈ {1,4,8,20} × Nt ∈ {1,6,20,50} ×` tier → `reports/perf/sweep.csv` → `documentation/simulation/performance.md` with measured scaling exponent per subsystem. Gate: 20v50 headless RTF ≥ 5×, live ≥ 1.0.
- **Fidelity equivalence:** Tier 0 vs Tier 1 trajectory RMSE < 2 m on the same seed.
- **Determinism:** same seed → identical hash traces; failures print the first divergent tick and offending array.
- **Detection physics:** `sensors/radar_model.py` P<sub>d</sub> validated against closed-form radar-equation hand calculations; publish the P<sub>d</sub>-vs-range overlay of the old synthetic curve against the physics-based one.
- **Campaign:** 1,000-episode Monte Carlo with **real sensing**, producing a P<sub>k</sub> curve with Wilson intervals and **actual failures**. Publish the before/after against the current 800/800 deliberately.

---

## 10. Execution order

1. **§2 defects** — rotate the key, reconcile test counts, MEGAPROMPTs out of nav, fix stale paths. Days.
2. **CI + `pyproject.toml` + lockfile.** Days.
3. **Docs**: CONOPS, §3 roadmap, parameter register, §4 deferred-workstream page, and the four specialist package skeletons. Unblocks hiring; depends on no code change.
4. **Workstream A1** — free perf wins. Days, and every demo feels different afterwards.
5. **`sensors/radar_model.py`** — physics-based P<sub>d</sub>. Closes the weakest physics in the repo and removes the MATLAB dependency from the critical path.
6. **S1 / A4** — real sensing in the loop, honest P<sub>k</sub> curve. The single biggest credibility item.
7. **S2** — seeker in sim. Produces the numbers §6.2 and §6.4 need as inputs.
8. **S3** — the ~$200 acoustic bench experiment. Go/no-go on the differentiator, before CAD freezes.

Everything in §4 stays out until its trigger fires.

---

## 11. Session tooling

- `/larp-status` — reads this file, runs the suite and profiler, verifies §2 defects by inspection, reports stage status against §3.
- `scripts/measure_perf_baseline.py` — reproducible per-subsystem timings; `--label` / `--output` after each stage.
- `reports/perf/baseline_pre_refactor.json` — the documented "before".
- Memory entries in `~/.claude/projects/c--Users-aclie-Documents-Side-Projects-defender-project/memory/` carry committed decisions across sessions.
