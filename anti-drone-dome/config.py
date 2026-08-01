"""
Project-wide constants.

Centralizes values that were previously duplicated across modules
(home lat/lon in comms/datalink.py and viz/acmi_writer.py) or buried
inside guidance code where they did not belong (interceptor mass,
force/acceleration caps).
"""

# ── Home / reference site ────────────────────────────────────────────
# Local ENU/NED coordinates project onto this geodetic origin.
# Consumed by comms/datalink.py (track broadcast) and viz/acmi_writer.py
# (Tacview export). In Stage B, ArduPilot SITL home will be set here too.
#
# TODO_REAL_TEST_SITE: replace with actual test-flight field coordinates
# before any real SITL or hardware run. Current placeholder is a generic
# point in southern Ontario.
HOME_LAT = 43.0000   # deg
HOME_LON = -79.0000  # deg
HOME_ALT = 0.0       # m, AMSL


# ── Interceptor airframe ─────────────────────────────────────────────
# Mass of the interceptor (kg). Lives here, not in guidance, because the
# flight controller — not the guidance law — is what cares about mass.
# The placeholder FC inside sim/drone.py uses this when converting
# acceleration setpoints to PyBullet forces.
INTERCEPTOR_MASS = 1.5


# ── Guidance limits ──────────────────────────────────────────────────
# Maximum commanded acceleration magnitude (m/s²). Placeholder ~17 G,
# matching the previous _MAX_FORCE = 260 N at _MASS = 1.5 kg in
# guidance/intercept.py. Replace with the Chameleon LR's measured
# thrust-to-weight envelope once available.
MAX_ACCEL = 17.0 * 9.81   # m/s²  (≈ 166.77)


# ── Placeholder FC ──────────────────────────────────────────────────
# Velocity-loop P gain inside sim/drone.py:Drone.apply_setpoint.
# Zero for Stage A so the velocity field of GuidanceSetpoint is purely
# informational and the placeholder FC reproduces the old
# force-feed-through behaviour exactly. The real ArduPilot velocity
# loop runs onboard the FC in Stage B and this gain becomes moot.
PLACEHOLDER_FC_KV = 0.0

# Contact evaluation is deliberately separate from any cinematic effects.
INTERCEPT_CONTACT_RADIUS_M = 1.0


# ── Pad / takeoff ───────────────────────────────────────────────────
# Pad altitude the placeholder FC climbs to before guidance takes
# over (replaces the velocity-teleport launch). Stage B maps this to
# MAV_CMD_NAV_TAKEOFF altitude.
PAD_ALTITUDE_M    = 5.0
PAD_GROUND_Z_M    = 0.5      # interceptor spawn height (sits on pad)
TAKEOFF_TOL_M     = 0.6      # vertical tolerance to declare "at altitude"


# ── Setpoint stream rate ────────────────────────────────────────────
# Stream rate to the FC (Hz). Comfortably above ArduPilot's ~3 Hz
# revert threshold without flooding the link. Consumed by Stage B
# when comms/datalink.py grows a setpoint sender.
SETPOINT_RATE_HZ = 20.0
