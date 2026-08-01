# Overnight engineering audit

## Resolved in this iteration

- Raw `aegis.tactical.v1` packets from the local simulator now work without
  requiring the optional Unreal bridge metadata.  If the optional
  `heading_deg` field is absent, the viewer derives a display heading from the
  supplied ENU velocity; the packet's normalized quaternion is still used for
  the rendered attitude.
- Runtime hides the imported Shahed/interceptor map preview meshes.  The
  telemetry-driven actors are consequently the only vehicle representations,
  preventing a second static aircraft from appearing suspended in the scene.
- A fixed-wing vehicle that is first tasked while already airborne receives a
  forward cruise-entry velocity.  Subsequent route following remains governed
  by the existing force, lift, drag, disturbance, energy, and flight-envelope
  model.
- The nominal direct Shahed mission now evaluates terminal success at a real
  1.0 m contact radius rather than the former 18 m cinematic proximity gate.
  Its terminal controller begins capture at a closing-rate-aware range and
  regulates relative position and closing speed.  A clean seeded end-to-end
  run on 2026-07-30 reached 0.8 m closest approach at T+13.7 s.  This is a
  deterministic simulation result, not a field-performance claim.
- The missing-interceptor fallback now reflects the simulated vehicle: a
  body-X rocket fuselage, cruciform tail, and four tail-plane propulsors.  It
  uses the incoming quaternion directly, so visual nose direction and the
  physical thrust axis agree.

## Priority validation after opening the editor

1. Open `Maps/Aegis_Range`, press Play, and send either a bridge packet or
   `python main.py --telemetry-udp 127.0.0.1:8788` from the simulation
   environment.  Confirm that exactly one Shahed moves from the first packet.
2. Fly a full intercept recording and compare actor position/orientation with
   the emitted telemetry rather than with the static GLB orientation.  Adjust
   mesh-axis offsets only if the imported asset's forward axis differs from
   Unreal's +X convention.
3. Capture GPU frame time and VRAM use at 1080p on the GTX 1650 in Low,
   Medium, and High.  The 80% TSR screen percentage is a starting point, not a
   performance claim.
4. Verify `H` (clean HUD), target boxes/off-screen arrows, automatic camera
   cuts, and the radar pulse during acquisition/deployment/intercept events.

## High-value next work

### Presentation

- Replace the generated cylinders used as contrails with a GPU Niagara ribbon
  that samples telemetry speed and altitude.  Add pooling/limits before adding
  dust, debris, and smoke so the GTX 1650 frame budget remains explicit.
- Build a material instance landscape with dirt/rock/sand/slope masks and
  macro-colour variation.  Add service roads, radar compound dressing,
  instanced rocks, and sparse vegetation before high-density foliage.
- Give each authored vehicle mesh an explicit visual socket/offset data asset.
  That is the correct anchor for engine glow, navigation lights, propellers,
  and control surfaces; do not attach those effects to guessed world-space
  positions.
- Add attenuation/spatialization and live RPM/speed parameters before any
  cinematic sound design.  Lock warning, radar sweep, and intercept sounds
  should be event-driven from telemetry transitions.

### Fidelity and safety

- The Shahed and interceptor profiles are explicitly representative/unvalidated
  in `anti-drone-dome/scenario_data/airframe_profiles_v1.json`.  Greater physical
  realism requires documented mass/inertia, thrust-versus-speed, aerodynamic
  coefficients, actuator limits, and environmental validation data; visual
  polish cannot establish that fidelity.
- Add recorded-telemetry replay tests that assert continuity, bounded velocity,
  and quaternion validity across full missions.  Keep the viewer display-only:
  it must never send steering, intercept, or sensor commands back to Python.
- Replace broad telemetry-path `except: pass` handling in Python with scoped
  logging/counters where failures can otherwise make an input or stream appear
  frozen.

### Usability

- Add a scenario browser, pause/restart/rate controls, remappable bindings,
  and an in-game debrief backed by the existing recording data.  A replay
  scrubber with sensor/vehicle event markers would be the most valuable next
  operator-facing feature.
