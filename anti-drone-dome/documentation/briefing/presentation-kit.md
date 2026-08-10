# Presentation and diligence kit

This is the operating plan for showing Project LARP to an investor, technical
partner, or range/safety stakeholder. It is deliberately built around
inspectable evidence, not a claim that the current research platform is field
ready.

## Ten-slide investor narrative

| Slide | Message | Evidence to show | Avoid saying |
| --- | --- | --- | --- |
| 1. Thesis | Project LARP makes counter-UAS engineering decisions reviewable before field integration | One sentence product thesis and system image | That a deployed system already exists |
| 2. Problem | Sensing, tracking, vehicle assumptions, and integration risk compound | Simple evidence-chain diagram | Unsupported market or threat statistics |
| 3. Product | A repeatable validation platform connects versioned inputs to replayable decisions | Architecture and data-contract diagram | That the viewer controls anything |
| 4. Demonstration | The simulator, telemetry bridge, and local viewer provide a transparent engagement walkthrough | Recorded Unreal replay with on-screen limitations | A live run as a performance proof |
| 5. Evidence | Tests, deterministic artifacts, parameter register, and strict docs build are routine quality gates | Verification matrix and one artifact hash | A unit-test count as field validation |
| 6. Current result | The corrected 1 m contact criterion exposes difficult scenarios and real failures | Regression result table | A broad proximity result or an all-success claim |
| 7. Defensibility | The moat is traceable data, calibrated models, partner measurements, and repeatable comparisons | Evidence-first roadmap | That an algorithm name alone is defensible |
| 8. Go-to-validation | Measurement partners create the next decision-quality evidence | Sensor, vehicle, compute, and HIL gates | A schedule that assumes approvals |
| 9. Partnership | Each partner supplies a bounded input and receives a clear decision artifact | Partner-opportunity table | Unbounded access to proprietary data |
| 10. Ask | Fund or partner around the next measured gate, not an undefined feature list | Specific first engagement and exit artifact | Field capability before the gate is complete |

Keep the spoken narrative under eight minutes. Leave at least seven minutes for
technical questions, and have the verification matrix open during discussion.

## Demonstration runbook

### Before the meeting

1. Use the packaged Unreal replay, not a live render-plus-physics session, as
   the primary visual demonstration.
2. Verify the package hash, JSONL input, and replay before the meeting.
3. Keep a locally saved PDF/export of the stakeholder brief and verification
   matrix in case the public site is unavailable.
4. Prepare the headless simulator as a secondary technical demonstration.
5. Do not use an unrecorded live result to make a performance claim.

### Suggested nine-minute flow

1. State the boundary: Python is authoritative; Unreal is a receive-only local
   presentation client.
2. Show the evidence chain from telemetry input through the validated replay.
3. Show one recorded mission in the packaged viewer.
4. Open the parameter register and identify which values are measured versus
   placeholders.
5. Show the regression table, including failed scenarios.
6. Close with the next partner measurement and the decision it unlocks.

### Fallback order

1. Packaged Unreal replay using a pre-validated JSONL recording.
2. Screen recording of that replay plus the accompanying telemetry artifact.
3. Headless Python swarm run with its JSON result.
4. Static screenshots only, labelled as captures from the simulator.

Never substitute concept art or a replay for a recorded claim. If a component
fails, say what is unavailable and switch to the next artifact in the list.

## Data-room checklist

### Share now

- Stakeholder brief and this presentation kit
- Architecture, data contracts, implementation status, and roadmap
- Verification matrix, parameter register, and current evidence
- Regression campaign method and selected versioned report
- Viewer release manifest, hash, and replay instructions
- Asset attribution and public dependency/license information

### Share under agreement or after review

- Raw partner sensor, vehicle, or field-test data
- Exact operating location, range plan, and safety documentation
- Credentials, service configuration, and unpublished security material
- Any data carrying third-party restrictions

### Release checklist

1. The strict documentation build passes.
2. Python tests and deterministic check pass.
3. The Unreal automation report and package hash are attached.
4. The public link has been checked from an unauthenticated browser.
5. Every stated metric links to an artifact and names its limitations.
6. The release owner has confirmed that no secrets or restricted partner data
   are included.

## Owner-facing action board

| Priority | Action | Owner needed | Completion condition |
| --- | --- | --- | --- |
| P0 | Restore Vercel deployment | Vercel project/domain owner | Public URL returns the strict-built site |
| P0 | Freeze baseline release | Repository release owner | Tag, artifact hashes, and data-room index exist |
| P1 | Pre-register next campaign | Technical lead | Scenario, seeds, metrics, thresholds, and failure criteria are locked |
| P1 | Secure one measurement partner | Founder/business lead | Data-rights and measurement plan are signed |
| P2 | Run calibrated comparison | Technical lead plus partner | Updated parameter provenance and rerun report are published |
| P2 | Conduct a controlled demo review | Safety/range partner | Approved recording and limitations package exists |

The first commercial milestone should be a partner-funded measurement and
validation engagement. It creates proprietary, reviewable evidence while
avoiding an unsupported promise of operational deployment.
