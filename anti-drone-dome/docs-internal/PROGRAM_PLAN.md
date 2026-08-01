# Project LARP — Program Plan

> **Internal document. Not published in the MkDocs site nav.**
> Single source of truth for program scope, staging, and open engineering work.
> Created 2026-07-31. Update the **Status** column in §2 as stages close.

## Context

The repo is far more real than "vibe-coded": ~24.6k lines of first-party Python, a genuine 9-state constant-acceleration Kalman filter with a correct white-jerk process-noise matrix, a real augmented-PN guidance law with terminal blending, a working PyBullet loop, 106 tests, a UE 5.8 C++ viewer with three packaged builds, and a 40-page MkDocs site that is unusually honest about its own limits (`documentation/system/implementation-status.md` has a dedicated "not implemented" list). That honesty is the project's biggest asset and must be preserved.

The goal is to hand work packages to **RF, CAD, acoustics, and simulation specialists**, and to survive scrutiny from a **technical design review board** and **investors** simultaneously. Committed decisions:

- **Vision:** kinetic interceptor + C2 — the full dome. Ground segment cues; onboard dual-mode seeker closes.
- **RF scope:** modeled RF only — link budget, antenna selection, frequency plan, jamming/EW resilience, regulatory. **No SDR, no signal processing.** State this explicitly so an RF expert doesn't arrive expecting GNU Radio.
- **Compute:** Jetson **Orin Nano** on the interceptor, **Orin NX** on the coordinator. See §7.
- **Sim goal:** real-time and faster-than-real-time at scale (20 interceptors vs 50 threats).
- **Auth:** Herman is handling Cloudflare access control. This plan does not build auth; it defines **what gets gated** (§4) and keeps authenticated transport as a specced Stage-3 item.

---

## 0. Three credibility defects to fix before anything is handed to an expert

These are the things that, if a specialist finds them first, cost us the room.

**0.1 — The swarm runs on omniscient sensors.** This is the serious one. `main.py:2095-2100` and `swarm/runner.py:135-138,195` feed **ground truth** positions and velocities straight into `coordinator.plan()`. The reason is structural: `sensors/radar.py:RadarNode.scan()` handles exactly one target — one `self._tracker`, one `_locked`/`_hits`/`_miss_count` state machine. So the headline claim "coordinated interceptor swarm vs saturation attack" currently has no sensing in the loop at all. Fixing this is Workstream A4 and is a prerequisite for any swarm claim in any document.

**0.2 — The test count is stated three different ways.** `implementation-status.md:31` says 99; `results/current-evidence.md:7` says 42; the repo actually has 106 `def test_` functions and 113 collected node IDs. A reviewer who runs `pytest` and gets a fourth number concludes the docs are decorative. Fix: CI emits the count; docs cite the CI artifact, never a hand-typed number.

**0.3 — Live Roboflow API key on disk.** `anti-drone-dome/.env` contains a plaintext `ROBOFLOW_API_KEY`. It is gitignored so it probably never reached a remote, but it has been read — **rotate it.** Also remove the retrieval commands from `.claude/settings.local.json:147-148` and fix `documentation/development/gpu-setup.md:25`, which instructs readers to copy the key "from .env on old laptop."

**Also, a judgment call worth stating:** the 800/800, 8-for-8 regression campaign is currently presented as a strength. To a review board, a stress campaign that nothing ever fails reads as a campaign that isn't stressing anything. The Wilson lower bound partially covers this, but the honest move is to build scenarios hard enough to produce a real P_k curve *with failures*. Reintroducing real sensing (0.1) will do a lot of this automatically, and the before/after should be published deliberately as evidence of rigor, not hidden.

---

## 1. The narrowed vision (goes at the top of every package)

> **Project LARP is a layered counter-UAS system with a clean authority split. The ground segment — radar, EO, fusion, weapon-target assignment, and the operator command center — detects, tracks, and commits. The airborne segment is a low-cost kinetic interceptor carrying its own dual-mode seeker: a four-microphone acoustic array for wide-field cueing and a strapdown EO camera for terminal lock, so the interceptor completes the engagement even if the datalink degrades.** The system is validated in a physics-based digital twin with a published regression campaign, cross-verified against independent MATLAB models, before any airframe flies. Today the ground and simulation layers are implemented and measurable; the interceptor and its seeker exist as a specification and a simulation model, not as flown hardware.

That last clause is the whole pitch: **the ground segment hands over a cued volume; the seeker closes the loop autonomously.** It is a real answer to "what happens when you jam the link," it justifies onboard compute on its own merits, and it is the sentence that makes this a system rather than a drone with a camera.

**System boundary — state explicitly what we do NOT do:** no RF signal interception or SDR-based detection; no jamming or electronic attack; no autonomous weapon release (human-on-the-loop commit is a design constraint — the seeker completes an engagement already authorized, it does not select targets); no regulatory or range certification. Naming the boundary is what separates a serious program from a pitch deck.

**Write this file first:** `documentation/system/concept-of-operations.md` — CONOPS with the engagement timeline (detect → track → classify → assign → launch → midcourse → terminal → assess), the authority model (Unreal is receive-only; ML residual capped at 5–25%; human authorization gate), and the explicit non-goals above.

---

## 1b. The onboard dual-mode seeker — architecture and corrections

The "cue-and-review" concept is sound and committed. The following corrections must land before it goes in front of an acoustics or GNC specialist.

### The one architectural change that matters most: fuse, don't mode-switch

A two-state machine (SEARCH ↔ TRACK) with a hard handoff will chatter at the boundary, and it throws away acoustic information the moment CV locks — exactly when the target is closest and most likely to break lock by banking.

**We already have the right machinery.** `sensors/fusion.py:TrackFusion` is a time-aligned, innovation-gated, reliability-weighted multi-source fuser with exponential age decay. Acoustics and EO are just two more sources with very different angular covariances: acoustic bearing is wide (σ ≈ 5–15°) but omnidirectional and always available; EO is narrow (σ ≈ 0.2°) but has a ~40–60° FOV and drops out under motion blur or occlusion. Feed both into the fuser with their real covariances and **the mode switch falls out of the weights automatically** — no state machine, no chatter, graceful degradation. Keep an explicit COAST behavior (propagate the last LOS rate) rather than snapping back to wide search.

This also means the whole thing is simulable *today*, before any hardware exists, with code we already have.

### The seeker's output should be LOS rate, not a pixel PID

A pixel-offset P-loop (`Kp = 0.15`) has two problems: the gain is in pixels, so it silently changes meaning if resolution or lens changes; and it is **pursuit guidance**, which has materially worse miss distance against a maneuvering target than proportional navigation.

`guidance/intercept.py` is an augmented PN law whose natural input is line-of-sight rate λ̇. A strapdown camera's natural *output* is LOS rate: `λ̇ ≈ d/dt[atan(pixel_error / f_px)]`, with body-rate compensation from the FC gyro (**strapdown seekers must subtract own-body rotation — the #1 implementation bug in this class of system**). So:

> **camera centroid → angular error via focal length → body-rate-compensated LOS rate → the same APN law the simulator already validates.**

Onboard terminal guidance becomes the same algorithm as simulated guidance, so the regression campaign already covers it.

### Corrections to the specific design

| # | Issue | Correction |
|---|---|---|
| 1 | **Spatial aliasing.** 15 cm mic spacing aliases above `c/2d` ≈ 1.14 kHz, but the target band is 1–8 kHz — nearly all of it ambiguous. | ~2 cm spacing (alias-free to ~8.5 kHz) with sub-sample GCC-PHAT peak interpolation (parabolic fit ≈ 0.1 sample ≈ 1–2° at broadside), or a sparse non-uniform array with explicit alias resolution. **The acoustics specialist owns this trade — state the constraint, don't pick a number.** |
| 2 | **Planar cross has up/down ambiguity.** `acos(r)` always returns positive elevation, silently assuming the target is above the plane. | **Tetrahedral array.** Same four mics, unambiguous 3D DoA, zero extra cost. |
| 3 | **Azimuth convention wrong.** `atan2(y, x)` with x from the L/R pair gives an angle from the right axis, CCW. | Aviation azimuth is from the nose, CW: `atan2(right_component, forward_component)`. Also state the Δt sign convention (which mic leads) — that's where the other half of these bugs live. |
| 4 | **No propagation-lag compensation.** Sound takes 146 ms to cover 50 m; a 30 m/s target has moved 4.4 m — **~5° systematic trailing bearing error at 50 m**, plus own-motion during the correlation window. | Compensate both; carry the residual as an explicit error-budget term. Most likely thing a GNC reviewer catches. |
| 5 | **Own-noise dominates.** Props at 15–30 cm and 100–110 dB SPL vs a target at ~35–40 dB SPL at 50 m — a **−60 to −70 dB SNR** problem. Broadband prop noise covers 1–8 kHz, exactly the target band. | Notches must **track RPM** → requires **bidirectional DShot RPM telemetry from ESCs to the Teensy** (a BOM/wiring requirement). Treat 10–50 m as an open question answered by a ~$200 experiment: bench SNR-vs-range, then hovering, then forward flight. Publish the measured curve. |
| 6 | **Wind noise** scales steeply with flow velocity; at intercept airspeeds the mics need windscreens and recessed/ported mounting. | Mechanical constraint → belongs in the CAD package (§3.2). |
| 7 | **MOG2 background subtraction assumes a static camera.** On a maneuvering interceptor every pixel is foreground. | **Use our own trained YOLO detector** — ~50k images, `scripts/finetune.py`, weights in `models/finetuned/`, live path in `integration/vision_model.py`. Keep a motion/contour tracker only as an inter-frame fallback. |
| 8 | **"Pi 5 at 30–40 FPS for YOLOv8n without a GPU" is not accurate** — realistic is 5–8 FPS at 640×640. | Orin Nano + TensorRT INT8, or Pi 5 + Hailo-8L (~30+ FPS). Settles §7. |
| 9 | **Bearing-only observability.** Both acoustics and monocular CV give bearing, no range — range-unobservable without maneuver or a second source. | Uplink the ground radar track as the range channel; bbox-height-derived range as a degraded fallback. Must be stated — "our seeker tracks the target" is not true in range without it. |
| 10 | **ASCII serial framing** (`Serial.print("CUE_DATA,AZ:...")`) is slow and unrecoverable under corruption. Prose says 100 Hz; `delay(50)` gives 20 Hz. | Versioned binary frame — magic, schema version, monotonic sequence, timestamp, az/el, per-axis variance, SNR, validity, CRC16 — named **`aegis.acoustic-cue.v1`** to match `system/data-contracts.md`. Pick one rate and make it a requirement with a measured jitter bound. |

**The Teensy 4.1 choice is good** — 600 MHz M7 with CMSIS-DSP, two hardware I2S buses for four ICS-43434s, deterministic DMA. A 1024-pt real FFT is ~50–100 µs; four forward transforms plus six cross-spectra and inverse transforms lands ~1.5 ms/frame, so 100 Hz is ~15% duty. Keep it, and keep acoustics off the Nano so a CV stall can't blind the cue path.

### What this adds to the simulator

- `sensors/acoustic.py` — bearing-only sensor with propagation delay, own-noise floor vs throttle, wind-noise term, angular covariance vs SNR, spatial-aliasing ambiguity model.
- `sensors/eo_seeker.py` — strapdown camera: FOV, focal length, P_d vs subtended pixels, motion blur vs body rate, dropout, latency.
- Both feed the existing `TrackFusion`; fused LOS rate feeds the existing APN.
- Monte Carlo then answers what actually matters — **at what acoustic detection range does the handoff still work? what CV dropout rate breaks the intercept? how much link loss can the seeker absorb?** — before anyone buys a microphone.

---

## 2. Stage ladder

Each stage has an exit gate that is a **published artifact**, not an opinion. TRL claims are per-subsystem, never system-wide.

| Stage | Name | Exit gate (the artifact) | TRL | Status |
|---|---|---|---|---|
| **S0** | Foundation hardening | CI green on every commit; determinism harness passes; §0 defects closed; docs split public/gated | — | not started |
| **S1** | Sensing & C2 at scale | 20v50 with **real multi-target sensing** (no ground truth), headless RTF ≥ 5×, Monte Carlo campaign with a genuine P_k curve and confidence intervals | 4 | not started |
| **S1b** | Seeker in simulation | `sensors/acoustic.py` + `sensors/eo_seeker.py` feeding the existing `TrackFusion` → APN; Monte Carlo answers the handoff questions **before any hardware is bought** | 4 | not started |
| **S2** | Independent cross-verification | MATLAB cross-check report published as a release gate: radar P_d, tracker OSPA, RF link budget agree within stated tolerances | 4–5 | not started |
| **S2b** | Seeker bench validation | Measured acoustic detection-range-vs-SNR curve on a hovering airframe; measured glass-to-command latency on the selected compute | 4–5 | not started |
| **S3** | Interceptor design freeze | Airframe CAD + itemized mass budget (incl. array, Teensy, mics, windscreens) + measured Jetson benchmarks + authenticated datalink spec, all feeding validated sim profiles (`evidence.status` → `measured`) | 5 | not started |
| **S4** | Captive-carry & HIL | Flight-log-identified dynamics replacing `design-placeholder`; HIL loss-of-link and latency qualification | 5–6 | not started |
| **S5** | Instrumented live intercept | Range-safety-approved intercept of a cooperative target, telemetry-recorded | 6 | not started |

Publish as `documentation/system/roadmap.md` with **cost and schedule per stage** and an explicit statement of what is funded vs. proposed. Investors and review boards both read the honesty of the TRL claim as the primary quality signal.

---

## 3. The four specialist work packages

Each is a directory under `documentation/specialists/`, self-contained, structured identically: **Scope → Interfaces → Current state (with file paths) → Deliverables → Acceptance criteria → Open questions we cannot answer without you.** The "open questions" section is what makes it a work package rather than a brochure.

### 3.1 RF specialist — `documentation/specialists/rf/`

Lead with the scope discipline: **modeled RF only, no SDR.**

Current state: `swarm/rf_link.py:71` implements `margin_db = link_budget_margin_db + 20·log10(max_range/r)` — FSPL *slope* only. **No frequency term**, so the model cannot distinguish 900 MHz from 5.8 GHz; no antenna gain or pattern; no polarization loss; no two-ray ground reflection (which dominates below ~50 m AGL and directly affects the coordinator↔interceptor link); no noise floor or receiver sensitivity. `packet_loss_probability` (line 77) is a logistic curve-fit standing in for a BER-vs-Eb/N0 curve.

Deliverables:
- **Frequency plan & regulatory posture** — ISM 900 MHz / 2.4 / 5.8 GHz vs licensed; ISED/FCC constraints; coexistence with the threat's own control links.
- **Link budget** — TX power, feedline, antenna gain, FSPL at declared frequency, two-ray ground reflection, LNA NF, receiver sensitivity → `margin_dB(range, altitude, attitude)`.
- **Antenna selection** with gain-vs-angle patterns, so link margin becomes attitude-dependent (currently it is not — a real fidelity gap for a maneuvering interceptor).
- **EW resilience** — J/S ratio vs jammer power/range/antenna discrimination, burn-through range table, loss-of-link behavior contract. **No Python analogue today; directly load-bearing for a C-UAS story.**
- **Authenticated datalink spec** — HMAC-SHA256 + monotonic nonce + replay window for telemetry, mTLS for command, on a separate safety-gated path. (Specced at S3, implemented later.)

Sim-consumed artifact: `sensor_models/rf_link_budget_v1.json` — `{frequency_hz, tx_dbm, gains, nf_db, sensitivity_dbm, margin_table[range][alt], per_curve, antenna_pattern}`. `RfLinkModel.from_budget_table(path)` replaces the closed-form. Acceptance: free-space case matches closed-form FSPL to ±0.05 dB; publish the delta between today's `20log10` model and the two-ray model at 10/50/200 m AGL.

### 3.2 CAD / mechanical specialist — `documentation/specialists/cad/`

Be blunt: **there is currently zero mechanical design.** No STL/STEP/F3D, no PCB, no schematic, no BOM. `assets/` contains only CC-BY Sketchfab visual models for the simulator. The interceptor exists as `scenario_data/airframe_profiles_v1.json` with `evidence.status = "design-placeholder"`. Saying this plainly is stronger than implying otherwise.

Deliverables:
- **Itemized mass budget** replacing the lumped `rigid_body.mass_kg = 1.5`, with `validate_airframe_profile` asserting components sum to gross mass within 1 g. Compute/seeker mass then propagates automatically into `Drone._mass_kg` (`sim/drone.py:203`), `_hover_ff`, and every acceleration in `_resolve_vtol_thrust` — so the seeker stack *visibly costs acceleration in the sim*.
- **Airframe concept + CAD** (STEP + native), propulsion/prop selection with thrust-stand data, structural margin under terminal maneuver loads, CG and inertia tensor → replacing placeholder `inertia_kg_m2 = [0.045, 0.045, 0.08]`.
- **Acoustic array integration** — tetrahedral mic mounting, vibration isolation, windscreens, ported/recessed housings (§1b items 5–6).
- **Thermal design for onboard compute** at altitude and airspeed (§7).
- **Launch/recovery mechanics**, EO sensor vibration isolation.
- **Manufacturability & unit cost target** — the dominant constraint for an expendable effector.

Sanity check to hand them: the profile has `energy_capacity_wh = 180.0` on a 1.5 kg vehicle → ~0.9 kg of Li-ion at 200 Wh/kg, i.e. 60% of gross mass. Separately, `swarm/runner.py:35` hard-codes `_INTERCEPTOR_ENDURANCE_S = 180.0` and never consults the profile. Reconcile both, driven from the mass budget.

### 3.3 Simulation specialist — `documentation/specialists/simulation/`

Hand over: `system/architecture.md`, `system/data-contracts.md` (7 versioned schemas, though only `aegis.tactical.v1` has a formal JSON Schema — the rest should get one), the fidelity-tier design and performance budget from §5, and the **measured-vs-assumed parameter register** — every physical constant in the sim, its value, its provenance (measured / datasheet / estimated / placeholder), and what would upgrade it. That register is the single most reviewer-persuasive document we can produce, and it can be produced in a week.

Deliverables: validated 6-DOF replacing the placeholder FC, error budgets, Monte Carlo methodology with confidence intervals, and the V&V matrix mapping each requirement → verification method (A/T/D/I) → evidence artifact.

### 3.4 Acoustic seeker & embedded DSP specialist — `documentation/specialists/acoustics/`

Hand over: the array geometry trade (§1b), the GCC-PHAT pipeline, the own-noise cancellation problem, and the Teensy↔Nano contract.

Deliverables: array geometry and mic spacing with the aliasing/resolution trade resolved and justified; measured own-noise spectra at throttle sweep with the airframe's actual props; adaptive notch design driven by bidirectional DShot RPM; windscreen and vibration-isolation design (with §3.2); a **measured detection-range-vs-SNR curve** replacing the asserted 10–50 m; angular accuracy vs SNR and vs off-boresight angle; the `aegis.acoustic-cue.v1` frame spec with a jitter bound.

Open questions to put in writing: what is the achievable detection range from a *moving* airframe? Can adaptive notching recover enough SNR against broadband prop noise, or is the useful band narrower than 1–8 kHz? Does a 2 cm alias-free array retain enough angular accuracy after sub-sample interpolation to cue a 40° camera FOV? If the answer to the last is no, the architecture degrades gracefully — acoustics becomes a break-lock recovery sensor rather than the primary cue — but we need the number before CAD freezes.

---

## 4. Documentation restructure (and what Cloudflare gates)

Split into a **public tier** (vision, CONOPS, architecture, TRL roadmap, implementation status, evidence summary) and a **gated tier** (specialist packages, RF link budget and EW analysis, CAD and mass budgets, performance budgets, cross-check reports, benchmark data). Herman's Cloudflare layer fronts the gated tier; this defines the split so the build produces two site trees.

Changes to `mkdocs.yml` nav:
- Add top-level **Program** (CONOPS, roadmap/TRL, non-goals), **Specialists** (the four packages), **Verification** (V&V matrix, cross-check reports, parameter register).
- **Move `archive/MEGAPROMPT_V2/V3/V4` out of the published nav entirely.** These are AI build prompts, currently linked from main navigation — the single loudest "vibe-coded" signal on the site. Keep them under `docs-internal/`.
- Fix stale content: macOS paths (`/Users/hermanisayenka/...`) in `anti-drone-dome/README.md`; the `C:\Users\aclie\Documents\Side Projects\anti-drone-dome` path in `MEGAPROMPT.md`; `Python 3.14.2` in `reference/detection-pipeline-reference.md` (the venvs on disk are 3.12).
- Add an **export-control / handling posture** page (ITAR/EAR assessment, release-review process).

---

## 5. Workstream A — Simulation performance and scale

Target: **20 interceptors vs 50 threats; RTF ≥ 1.0 with the live command center; ≥ 5× headless; ≥ 10× Monte Carlo.**

Reproduce the baseline with `venv312\Scripts\python.exe scripts\measure_perf_baseline.py`; committed output in `reports/perf/baseline_pre_refactor.json`. Figures below are from an i7-9750H / Python 3.12.2 / NumPy 2.4.6 host — **host-relative, so re-run the script rather than comparing against these numbers on a different machine** (the report records a `host_normalization_us` microbenchmark for scaling). Run-to-run variance on the microbenchmarks is roughly ±20%, so treat sub-2× changes as noise.

**Measured end-to-end headless RTF today:** `saturation_6v4` (4 interceptors vs 6 threats) = **14.8×**; `overwhelm_8v3` (3 vs 8) = **16.5×**. Note: an earlier profiled figure of 4.6× was measured under cProfile, which inflates microsecond-scale NumPy calls by 3–5×. **A profiled RTF is not a baseline** — always measure unprofiled.

| Call | Cost | Cause |
|---|---|---|
| `guidance/intercept.py:compute_guidance` | **~275 µs** | `np.cross` on 3-vectors = 26 µs each (×2); `np.clip` on Python scalars = 4.3 µs each (~16 of them) |
| `swarm/assignment.py:build_cost_matrix` @20×50 | **60.6 ms** | nested Python loop calling `time_to_intercept` (60 µs) per cell |
| `swarm/assignment.py:hungarian_assignment` @20×50 | **50.8 ms** | numpy-scalar indexing in the Kuhn-Munkres inner loop |
| `sensors/radar.py:KalmanTracker.step` | **~50 µs** | per-track F/H/Q/R copies; dense 3×9 matmuls implementing a pure selector |
| PyBullet `stepSimulation` @70 bodies | 50.8 µs | the solver is **not** the bottleneck |
| PyBullet Python API round trip | **1.65 µs** | ~19 calls/vehicle/step → ~2 ms/step at 70 entities, 43× the solver cost |

**The scaling wall is WTA, not the current scenarios.** At today's 4v6 the assignment cost is negligible; at the 20v50 target, `build_cost_matrix` + `hungarian_assignment` is **~110 ms per plan call**, and `main.py:2106` calls `plan()` at 240 Hz. That is ~26 seconds of compute per simulated second from one subsystem. Rate-gating to 10 Hz (A1.2) and batching the cost matrix (A2) are the two changes that matter.

The primitive measurements are the whole vectorization argument in three numbers: `np.clip` on a Python scalar costs **15×** a plain `min/max` clamp (4.27 vs 0.27 µs); `np.linalg.norm` on a 3-vector costs **19×** a `math.sqrt` (1.76 vs 0.09 µs); and `np.cross` on **1000 rows costs only 1.3× what it costs on 3 elements** (34.7 vs 26.4 µs). Nearly all of the cost is interpreter dispatch, not arithmetic — so batching is close to free and scalar NumPy is pure overhead.

At 20 interceptors × 100 Hz, `compute_guidance` alone is 529 ms per simulated second. That is the budget, gone, before any sensing.

**Key structural finding:** PyBullet is not the bottleneck, and the vehicles don't need it. `sim/drone.py:_compute_vtol` (444) and `apply_setpoint` (635) call `resetBasePositionAndOrientation` + `resetBaseVelocity` **every step** — orientation overwritten, angular velocity zeroed, rotor torques discarded. Bullet provides translational Euler integration and nothing else for the swarm tier. What it legitimately provides — terrain/building collision and the rendered EO camera — matters for exactly one engagement at a time.

**Stage A1 — free wins (~2–3 days, no architecture change, all existing tests pass unchanged)**
1. `guidance/_fastmath.py` — scalar `cross3`/`norm3`/`clamp`/`dot3`; mechanically replace `np.clip`-on-scalars and `np.cross`-on-3-vectors in `_adaptive_parameters`, `_lead_solution`, `_confidence`, `compute_guidance`, `_cap_accel`. Behavior-identical; expect **265 µs → ~60 µs** (the ~16 clips and 2 crosses account for ~120 µs of the 265).
2. **Rate-gate `SwarmCoordinator.plan()` to 10 Hz** with an internal cache. It runs at 240 Hz today (`main.py:2106`) but the coordinator is datalink-limited at 10 Hz (`_offer_interval_s`, line 81) — re-solving WTA at 240 Hz was never physically meaningful. **~24× on its own.**
3. Replace `threat_ids.index()` O(N) scans in `coordinator.plan` (136-137) with the `threat_by_id` dict already built at line 109.
4. `Drone.get_state` → 2 API calls + per-step memo; gate `_spin_rotors` (cosmetic, 4 calls/vehicle/step) on GUI/Tier-0.
5. Exploit `H = [I|0|0]` in `KalmanTracker.step` — `H@x` is `x[:3]`, `H@P@H.T` is `P[:3,:3]`. 84.5 → ~50 µs; applies even unbatched.
6. Add `sim/perfcounters.py` + `scripts/profile_engagement.py` so every later stage is measured.
   *Gate:* re-run `scripts/measure_perf_baseline.py --label after-a1`. `compute_guidance` ≤ 100 µs, `KalmanTracker.step` ≤ 60 µs, 4v6 RTF ≥ 25× (from 14.8×). `test_intercept.py`, `test_apn_comparison.py`, `test_radar.py`, `test_tracking_accuracy.py` unchanged and green.

**Stage A2 — batched kernels (~1–2 weeks).** `guidance/intercept_batch.py` (`apn_batch` over `(N,3)`, `PurePursuitGuidance.compute_guidance` becomes an N=1 wrapper so all callers are untouched); `sensors/kalman_batch.py` (`BatchedCAKalman` with `x (N,9)`, `P (N,9,9)`, shared F/Q/R, batched LAPACK `inv` on `(N,3,3)`, **keeping the Joseph form** — the PSD-stability comment at `radar.py:88-94` is load-bearing); `swarm/assignment_batch.py` (vectorized cost matrix and Hungarian inner loop, **preserving the deterministic id-string tie-breaks** pinned by `tests/test_swarm_assignment.py`); `sim/kinematics.py:resolve_contacts` replacing the O(N·M) contact loops at `main.py:2142` and `swarm/runner.py:255`. Each new module ships with an equivalence test against the scalar path.

**Stage A3 — fidelity tiers + rate groups (~2–3 weeks).** `sim/fidelity.py` with three tiers: **Tier 0 FULL_RIGID** (PyBullet, the engagement of interest — terrain collision + rendered EO), **Tier 1 REDUCED_6DOF** (batched port of `_resolve_vtol_thrust`/`_condition_force`/`_limit_force`, the swarm default), **Tier 2 POINT_MASS** (Monte Carlo). Promotion when an entity enters the contact window (< `taper_range` ≈ 125 m) or is the operator camera focus. Equivalence gate: same seeded 4v6 in Tier 0 vs Tier 1, trajectory RMSE < 2 m over 30 s — reusing `validation/flight_log.py:compare_flight_logs` and the existing `maximum_trajectory_rmse_m` gate in `hardware/profile.py`. Plus `sim/params.py` (kill the per-vehicle `deepcopy` in `get_airframe_profile`), `sim/scheduler.py` rate groups, and `PhysicsWorld(visuals=False)` for headless (`_draw_land_cover` and the visual halves of `_draw_terrain_relief`/`_draw_real_map` are not GUI-gated today).

**Stage A4 — real sensing, determinism, Monte Carlo (~2–3 weeks).** `sensors/radar_batch.py:MultiTargetRadar` with batched beam/Doppler/detection tests and **data association** (Mahalanobis-gated Hungarian using `KalmanTracker.P[:3,:3]`); `TrackFusion.update_batch`; **remove ground-truth injection from `_run_swarm_mission` and `swarm/runner.run_scenario`** (§0.1). Then `sim/runconfig.py` (frozen `RunConfig` replacing `main.py` module globals at 57-76, which block Monte Carlo workers) and `sim/determinism.py` + `scripts/check_determinism.py`.

Determinism bugs to fix specifically: unseeded global `random.uniform` for wind gusts (`main.py:941-943`); `RenderedCameraSensor` gets **no seed at all** (`main.py:656`) → OS entropy; `RadarNode`'s seed derives from **dict insertion order** in `scenarios.py` (`main.py:648-651`), so adding a scenario silently changes every historical seed; `time.time()` leaking into state via `Drone.get_state` (`sim/drone.py:674`), `dome/killzone.py:40,73,77,80`, `sensors/radar.py:332,403`. Also pin `pybullet.setPhysicsEngineParameter(deterministicOverlappingPairs=1, ...)` and set `OMP_NUM_THREADS=1` in Monte Carlo workers. Note honestly: vectorization changes float reduction order, so version the baseline as `determinism_schema: v2` rather than pretending bit-equality survives.

Then `scripts/run_monte_carlo.py` and parallelize `scripts/run_regression_campaign.py` (currently strictly serial at `--repeats 100`; every episode is already independently seeded — a `ProcessPoolExecutor` away from near-linear scaling).

**Stage A5.** Extend `scenario_data/swarm_scenarios_v1.json` (max today is `overwhelm_8v3`) with `saturation_50v20`, layered waves, mixed-RCS cases, and a spawn-distribution schema field so 50-threat scenarios don't need 50 hand-written entries.

**Foundation, do first:** GitHub Actions CI for `anti-drone-dome` (none today — the only workflow belongs to vendored upstream), a `pyproject.toml` so it's an installable package rather than cwd-dependent imports, and a pinned lockfile (`requirements.txt` is `>=`-only with no upper bounds). Add `tests/test_perf_budget.py` marked `@pytest.mark.perf`, host-normalized so it doesn't fail spuriously on a slower machine.

---

## 6. Workstream B — MATLAB/Simulink where it earns its place

**Principle: Python stays authoritative. MATLAB is never in the runtime or CI path.** MATLAB produces committed offline artifacts; Python consumes and verifies against them; verification runs everywhere without a MATLAB seat. A MATLAB model that merely reimplements our assumptions is worthless — every item below brings physics we do not currently have.

**B1 — Phased Array System Toolbox → radar P_d. Highest value; do first.** `sensors/radar.py:360-372` is a hand-drawn piecewise-linear detection curve with no radar equation behind it: no transmit power, no antenna gain, no wavelength, no noise figure, no integration gain. `false_alarm_probability` is a free scenario parameter rather than derived from a detection threshold — so P_d and P_fa are **decoupled, which is physically impossible.** Deliverable: `matlab/radar/export_pd_tables.m` using `radareqrng` + `shnidman`/`rocpfa` for true Swerling-I/II relations, exporting `sensor_models/radar_pd_table_v1.json`; Python gets `sensors/radar_model.py:PdTable` doing trilinear interpolation. Acceptance: tabulated max detection range at RCS 0.05 m², P_d 0.5, P_fa 1e-6 within ±5% of a closed-form hand calculation. **Publish the P_d-vs-range overlay of old-vs-physics-based — the most persuasive artifact in this workstream.** (~$2,650 + ~$2,500 perpetual.)

**B2 — Sensor Fusion and Tracking Toolbox → the tracker and, critically, association.** `trackingKF` with `constacc` fed the exact same measurement sequence exported from Python; `trackerGNN`/`trackerJPDA` against the 50-target detection stream; score with `trackOSPAMetric` (invariant to track-ID permutation, far better than pointwise diff). Acceptance: single-target RMS position error within 2%; `trace(P)` within 1% (**not** elementwise — our Joseph form vs MATLAB's standard form differ in the last bits); multi-target OSPA (c=20 m, p=2) within 10%, track-swap count ±1. Earns its cost specifically because of **association**, which we haven't written and which is easy to get subtly wrong. (~$2,000.)

**B3 — Simulink + Aerospace Blockset → 6-DOF plant and control law.** Replaces the "placeholder FC" — currently a world-frame PD with kinematic attitude, no rotational dynamics, no rate loop, no motor mixer. Adds Dryden/von Kármán turbulence (vs today's bare Gaussian `turbulence_force_std_n`) and ISA atmosphere, which §7's thermal-at-altitude analysis needs. Acceptance: step-response settling within 10%, overshoot within 15%; closed-loop trajectory RMSE ≤ 2.0 m against the Simulink reference, reusing the existing `trajectory-rmse` gate in `validation/workbench.py:160`. (~$9,650 perpetual.)

**Defer Embedded Coder.** Its ~$22k marginal cost buys production-qualifiable autocode, which matters when you have flight hardware and a churning control law. Until then, hand-writing the controller from the block diagram is ~400 lines of C and free. Revisit at S4.

**B4 — Antenna Toolbox, conditionally.** FSPL and two-ray are ~30 lines of Python; RF Toolbox isn't needed. **Antenna Toolbox is the one that earns money**, because a method-of-moments antenna pattern is not something we're going to write. Buy it only when genuinely choosing between a patch and a helix. If the antenna is "a published datasheet gain figure," hard-code it and say so.

**Explicitly NOT MATLAB, and say so in the doc** (this list is itself a credibility signal): APN guidance (20 lines of vector algebra; cross-check against a closed-form analytic solution for a non-maneuvering target — free and stronger), WTA (verify against `scipy.optimize.linear_sum_assignment` for free), YOLO/EO perception, PPO/RL, the swarm state machine, Monte Carlo execution, and **runtime co-simulation** (a ~1 ms `matlab.engine` round trip would destroy the entire §5 budget).

**The harness** — `validation/crosscheck.py` + `scripts/run_crosscheck.py` + `tests/test_crosscheck_vectors.py`. Python emits seeded stimulus to `fixtures/crosscheck/` with a sha256; MATLAB consumes it and writes `matlab/out/` plus a **manifest recording MATLAB release, toolbox versions, license numbers, timestamp, and input/output hashes** — without that provenance record, "MATLAB agrees" is unfalsifiable. Python compares and emits `aegis.crosscheck-report.v1`, mirroring `validation/workbench.py:evaluate_gates`' existing `{id, passed, actual, limit, operator}` shape so cross-check evidence renders identically to the hardware report reviewers already see. Add `crosscheck-agreement` as a first-class release gate alongside `intercept-rate`. **Staleness detection stops this rotting:** the test fails if a fixture hash no longer matches the manifest, i.e. changing the Python model tells you the MATLAB reference must be regenerated.

**Purchase order:** Phased Array → Sensor Fusion & Tracking → Simulink + Aerospace Blockset → Antenna Toolbox (conditional) → Embedded Coder (S4 only).

---

## 7. Workstream C — Onboard compute

**C1 — `documentation/hardware/onboard-compute.md`,** a requirements spec with a **verification method per requirement** (A/T/D/I) — that's what makes it a spec rather than a datasheet transcription. Hard thresholds: sustained ≥ 60 fps post-throttle, glass-to-command p99 ≤ 30 ms, jitter σ ≤ 3 ms, mass ≤ 200 g, power ≤ 15 W, unit cost ≤ $X. Derive the 60 fps from closing rate and terminal geometry in `guidance/intercept.py:_adaptive_parameters` — it's the requirement most likely to decide the trade.

**Now that the seeker is onboard, the latency budget must be glass-to-actuator end-to-end:** camera exposure → readout → inference → centroid → body-rate compensation → LOS rate → APN → MSP/MAVLink command → FC rate loop. Each hop gets a p99 budget and a measurement method. The acoustic path gets its own parallel budget (I2S frame → FFT → GCC-PHAT → serial frame → fusion). A single end-to-end number with no breakdown collapses under one question.

**C2 — Benchmarks, measured not assumed.** `bench/jetson/bench_trt_latency.py` (TensorRT INT8/FP16 inference latency), `bench_glass_to_guidance.py` (end-to-end photon-to-command), `bench_thermal_soak.py` (sustained throttle behavior at each power mode). Results land in `scenario_data/airframe_profiles_v1.json` and flip `evidence.status` from `design-placeholder` toward `measured`.

**C3 — Make the sim reflect the real vehicle.** Itemized `mass_budget_kg` (§3.2) so compute mass propagates into thrust-to-weight automatically. New `sim/power_budget.py:HotelLoad` — `Drone._condition_force` (570-585) models only mechanical propulsion energy and has **no avionics hotel load at all**; adding it makes the state-of-charge → thrust derating reflect compute draw, so endurance actually changes when compute changes. Deliverable: `scripts/plot_endurance_vs_compute.py` → loiter endurance and terminal Δv vs compute power (7/10/15/25 W) and vs compute mass (50/100/185/300 g). **That one chart is the whole trade study made visible.**

**C4 — Compute selection.** For a 1.5 kg expendable running one 640×640 single-class detector plus a strapdown-seeker guidance loop, Orin NX's ~100 TOPS is 20–50× the requirement at ~$800 destroyed per intercept. **Orin Nano 8GB — ~40 TOPS (67 Super), 7/15 W, ~130–200 g flight-integrated, ~$250–400 — is the selected part for the interceptor**, and it comfortably runs YOLOv8n under TensorRT INT8 at terminal rates (unlike Pi 5 CPU-only, realistically 5–8 FPS at 640×640). **Orin NX goes on the coordinator aircraft** — recoverable, does 20-interceptor fusion + WTA, a genuine 100 TOPS non-expended workload.

Keep Pi 5 + Hailo-8L (~$150, ~110–160 g, ~13 TOPS) in the trade study as the cost floor and actually bench it, because two penalties still bite at Nano scale:

1. **Cost per expenditure.** Compute is destroyed on every successful intercept. For a system whose value proposition is being cheaper than the threat it defeats, recurring cost per shot may be the dominant design driver — ~$300 vs ~$150 is still 2×.
2. **Mass fraction.** Flight-integrated compute is ~130–200 g on a 1,500 g vehicle — ~10%, now *on top of* the acoustic array, Teensy, and four mics. Trading 60 g buys ~12 Wh of battery.

Where the Jetson justifies its premium over Hailo: **development velocity** (CUDA/TensorRT/PyTorch on-device vs Hailo's compile step and supported-op subset — debugging a model that won't compile costs weeks) and **headroom** for what this architecture will add — the strapdown-seeker LOS pipeline, onboard fusion of acoustic + EO + uplinked radar range, VIO for GPS-denied terminal, video encode for the downlink. A 13 TOPS part at 17 GB/s runs out fast. AGX Orin is not a candidate for the interceptor (15–60 W, >400 g integrated) but is plausible for the coordinator or ground station.

**Document it as a decision, not a preference.** `documentation/hardware/compute-trade-study.md` with weights declared **before** benchmarking (latency p99 25%, sustained post-throttle 20%, mass 20%, cost 15%, power 10%, ecosystem 10%), measured data on at least two candidates — buy the Pi5+Hailo-8L stack (~$150) and bench it, trivially cheaper than being wrong about a 10% mass fraction — a sensitivity analysis, and a decision record with an explicit revisit trigger. Feed both into the sim as two airframe profiles and **let the Monte Carlo campaign show the intercept-rate delta.** That is an answer, not an opinion.

---

## 8. Verification

- **CI (new):** GitHub Actions on `anti-drone-dome` — `pytest -q` (headless, no display), `mkdocs build --strict`, `check_determinism.py` on 2–3 scenarios, `test_crosscheck_vectors.py`, `test_perf_budget.py` on the perf-marked path. CI emits the test count as an artifact; docs cite it.
- **Performance:** `scripts/perf_sweep.py` over `Ni ∈ {1,4,8,20} × Nt ∈ {1,6,20,50} ×` tier → `reports/perf/sweep.csv` → `documentation/simulation/performance.md` with measured scaling exponent per subsystem. Gate: 20v50 headless RTF ≥ 5×, live command center ≥ 1.0.
- **Fidelity equivalence:** Tier 0 vs Tier 1 trajectory RMSE < 2 m on the same seed, via `compare_flight_logs`.
- **Determinism:** two runs of the same seed produce identical hash traces; `check_determinism.py` prints the first divergent tick and the offending array on failure.
- **Cross-verification:** `scripts/run_crosscheck.py` → `validation_reports/crosscheck/*.{json,html}`; `crosscheck-agreement` gate wired into `validate_hardware_profile`.
- **Campaign:** 1,000-episode Monte Carlo with **real sensing** completes in wall-clock/nproc and produces a P_k curve with Wilson intervals and **actual failures**. Publish the before/after against the current 800/800 deliberately.

---

## Execution order

1. §0 defects (rotate key, reconcile test counts, remove MEGAPROMPTs from nav, fix stale paths) — days.
2. CI + `pyproject.toml` + lockfile — days.
3. §1/§1b CONOPS + seeker architecture + §2 roadmap + parameter register + the **four** specialist package skeletons — the deliverable that unblocks hiring; depends on no code change.
4. Workstream A1 (free perf wins) — days, and it makes every demo feel different.
5. **S1b seeker-in-sim** (`sensors/acoustic.py`, `sensors/eo_seeker.py`, both into the existing `TrackFusion`, LOS rate into the existing APN). High-leverage: validates the dual-mode concept, produces the numbers the acoustics and CAD specialists need as inputs, and costs sim time instead of hardware.
6. A2–A4 in order; B1 in parallel once someone has a MATLAB seat; C1–C2 and the ~$200 acoustic bench experiment in parallel once parts arrive.

---

## Session tooling

- `/larp-status` — reads this file, runs the test suite and profiler, reports measured RTF and stage status against the §2 gates.
- `reports/perf/baseline_pre_refactor.json` — pre-refactor measurements, so every improvement claim has a documented before.
- Memory entries in `~/.claude/projects/c--Users-aclie-Documents-Side-Projects-defender-project/memory/` carry the committed decisions across sessions.
