# Evidence-first roadmap

Project LARP is developed as a sequence of evidence gates, not as a list of
features. A stage only advances when its artifact exists and its limits are
published.

| Stage | Objective | Exit evidence | Status |
| --- | --- | --- | --- |
| S0 | Reproducible software foundation | CI, deterministic-run manifest, parameter register, public/gated documentation split | Implemented locally; public deployment pending |
| S1 | Real sensing and tracking in simulation | Multi-target radar, association, fusion, and sensor-in-loop Monte Carlo | In progress: synthetic radar and anonymous-track association implemented; calibration and campaign evidence pending |
| S2 | Simulated onboard seeker | Acoustic and EO observations fused into the existing track path | Not started |
| S3 | Bench validation of differentiators | Acoustic SNR/range/bearing and target-compute latency measurements | Not started |
| S4 | One measured airframe | CAD, mass budget, thrust, inertia, and thermal evidence | Not started |
| S5 | Captive-carry/HIL integration | Flight-log-calibrated dynamics and loss-of-link timing evidence | Not started |
| S6 | Cooperative, range-approved demonstration | End-to-end recorded engagement under approved safety controls | Not started |

## Immediate priorities

1. Restore the public documentation deployment and make the repository’s
   public/private boundary intentional.
2. Remove any invalid swarm-performance claim until multi-target sensing and
   association replace ground-truth inputs.
3. Record parameter provenance and lock the exact artifacts used for every
   result.
4. Make determinism, performance, Python tests, Unreal package verification,
   and documentation checks routine release gates.
5. Use measured camera/acoustic/airframe data to revise the simulation before
   considering more guidance-policy training.

## Deliberate non-priorities

Residual reinforcement-learning guidance and additional Unreal rendering work
are not current milestones. The existing APN baseline has not yet been
challenged in a calibrated sensor-in-loop scenario, and the packaged viewer is
already sufficient to present measured results.
