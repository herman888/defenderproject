# Consistency-pass report — 2026-08-10

This report records the reconciliation work completed in this pass. It does not
promote a synthetic result to a measured claim.

## Changed material

- `documentation/system/edge-platform-and-integration.md` — Pi 5 + Hailo is the first measurement platform; all Pi/Hailo performance cells are `NOT MEASURED`; Orin alternatives now have an evidence-gate trigger.
- `documentation/hardware/overview.md` — records the confirmed Pi/Hailo, Mamba, camera, motor, receiver, and camera-limit inventory.
- `documentation/briefing/stakeholder-reassessment-pack.md` — changes the three product layer names to LARP and makes the camera/optics request specific.
- `documentation/system/parameter-register.md` — adds camera crop/tile and target-device evidence entries.
- `documentation/results/claims-register.md` — records the 1 m synthetic campaign and marks the legacy Claim A `SUPERSEDED, RERUN REQUIRED`.
- `scripts/measure_camera.py` — standalone UVC enumeration/configuration measurement scaffold.
- `scripts/measure_pipeline.py` — explicit `NOT MEASURED` target-device evidence-gate template.
- `tests/test_measure_camera.py` — validates the measurement artifact structures without hardware.
- `hardware_profiles/raspberry_pi5_companion.json` — records Pi/Hailo and read-only UART/MAVLink intent.

## Claim provenance

- Claim A (sub-20 cm versus 51–748 m) is not present in a committed result artifact. Legacy test sources identify `fpv_attack`/`spiral` and a 748 m miss; their old broad-proximity result cannot be reused under the 1 m criterion. Status: **SUPERSEDED, RERUN REQUIRED**.
- Claim B traces to `validation_reports/regression_campaign.json` and the corrective contact-criterion commit `17f3788`. Status: **VERIFIED (synthetic only)**.

## Remaining contradictions requiring a follow-up rename pass

The existing tree still contains legacy `aegis.*` schema names, Aegis Unreal
project/class names, `swarm` module/schema names, and retired interceptor/
rocket material. They were not mechanically renamed in this pass because a
schema/interface migration requires a versioned alias and consumer migration,
not a text replacement. Existing historical/generated artifacts were retained.
The inventory should be completed before that migration; no external or
third-party term should be renamed without classification.

## Verification

- Focused measurement/profile tests: `11 passed`.
- Full Python suite after changes: `228 passed in 52.86s`.
- Strict documentation build after changes: passed (`mkdocs build --strict`).

## Human decisions still required

1. Confirm Claim A's old contact criterion and commission its 1 m rerun.
2. Confirm the TOA 2306 build's pack voltage.
3. Select the exact Pi AI HAT+/AI Kit and Hailo-8 versus Hailo-8L configuration.
4. Select and calibrate the first crop/tile configuration for the InnoMaker camera.
5. Approve the public-interface version/alias policy before renaming `aegis.*` and `swarm` schemas.
