"""
Intruder types and attack patterns for the anti-drone dome simulation.

Two independent axes:
  INTRUDER_TYPES   — what the drone is (physics, RCS, threat level)
  ATTACK_PATTERNS  — how it attacks (waypoint path, start position)

Any type can fly any pattern.  The dashboard lets the operator choose both
independently before launching a mission.
"""

# ── Waypoint paths (metres, dome centre = 0,0,0, North = +Y) ──────────────

_DIRECT_APPROACH = [
    (550.0,  550.0, 220.0),
    (360.0,  420.0,  180.0),
    (240.0,  280.0,  150.0),
    (150.0,  180.0,  110.0),
    ( 90.0,  100.0,   80.0),
    ( 40.0,   45.0,   55.0),
    (  0.0,    0.0,   40.0),
]

_LOW_FAST_APPROACH = [
    (800.0,   0.0,  30.0),
    (560.0,   0.0,  25.0),
    (360.0,   0.0,  22.0),
    (180.0,   0.0,  18.0),
    ( 60.0,   0.0,  15.0),
    (  0.0,   0.0,  12.0),
]

_SPIRAL_DESCENT = [
    ( 650.0,    0.0, 280.0),
    ( 360.0,  440.0, 230.0),
    (-300.0,  380.0, 175.0),
    (-380.0, -300.0, 120.0),
    ( 180.0, -300.0,  75.0),
    (  60.0,   60.0,  45.0),
    (   0.0,    0.0,  40.0),
]

_WAYPOINTS = {
    "direct_approach":   _DIRECT_APPROACH,
    "low_fast_approach": _LOW_FAST_APPROACH,
    "spiral_descent":    _SPIRAL_DESCENT,
}


# ── Intruder type definitions ──────────────────────────────────────────────
#
# aero dict keys:
#   cd            profile drag coefficient
#   a             frontal area (m²)
#   cl            lift coefficient  (0 for pure quadrotors — no wings)
#   a_w           effective wing area (m²)  tuned so lift≈weight at cruise speed
#   max_h_force   max horizontal force cap (N)
#   fz_min/max    vertical force clamp (N)
#
# Physics note — wing sizing formula for fixed-wing types:
#   a_w = (mass * 9.81) / (0.5 * 1.225 * cl * cruise_speed²)
#   Shahed-136 (1.4 kg, 51 m/s): a_w = 13.73 / (0.5*1.225*0.65*2601) ≈ 0.013 m²
#   Below stall speed (~35 m/s) lift < weight → thrust must compensate (realistic).

INTRUDER_TYPES = {
    "shahed136": {
        "label":              "■ SHAHED-136",
        "description":        "Shahed-136 loitering munition — 51 m/s cruise, delta wing, low RCS",
        "max_speed":          51.0,          # m/s  (~185 km/h cruise)
        "rcs":                0.05,          # m²   composite/fibreglass body
        "threat":             "HIGH",
        "response_delay":     4.0,           # s    alert + arm + launch
        "mass":               1.4,           # kg   (real ~200 kg, sim-scaled)
        "aero": {
            "cd": 0.20, "a": 0.030,          # streamlined delta-wing profile
            "cl": 0.65, "a_w": 0.013,        # lift ≈ weight at 51 m/s
            "max_h_force": 160.0,
            "fz_min": -60.0, "fz_max": 90.0,
        },
        "urdf":               "intruder.urdf",
        "scaling":            18.0,   # visible at 200 m dome scale
        "color_rgba":         [0.85, 0.12, 0.08, 1.0],   # blood red
    },

    "consumer_quad": {
        "label":              "⬡ CONSUMER",
        "description":        "Consumer quadrotor (DJI Mavic type) — 16 m/s, ISR or small payload",
        "max_speed":          16.0,          # m/s  (~58 km/h)
        "rcs":                0.003,         # m²   small plastic/composite frame
        "threat":             "MEDIUM",
        "response_delay":     6.0,           # s    harder to detect — more hesitation
        "mass":               0.9,
        "aero": {
            "cd": 0.45, "a": 0.012,
            "cl": 0.0,  "a_w": 0.001,        # no wings — pure thrust
            "max_h_force": 28.0,
            "fz_min": -18.0, "fz_max": 40.0,
        },
        "urdf":               "drone.urdf",
        "scaling":            10.0,
        "color_rgba":         [0.82, 0.84, 0.90, 1.0],   # light grey
    },

    "fpv_attack": {
        "label":              "✕ FPV ATTACK",
        "description":        "Modified FPV racer — 32 m/s, agile, carbon-fibre frame, near-zero RCS",
        "max_speed":          32.0,          # m/s  (~115 km/h)
        "rcs":                0.001,         # m²   carbon fibre, minimal metal
        "threat":             "HIGH",
        "response_delay":     3.0,           # s    fast attacker — must react quickly
        "mass":               1.0,
        "aero": {
            "cd": 0.38, "a": 0.008,
            "cl": 0.0,  "a_w": 0.001,        # no wings — pure thrust
            "max_h_force": 55.0,
            "fz_min": -30.0, "fz_max": 62.0,
        },
        "urdf":               "drone.urdf",
        "scaling":            7.0,
        "color_rgba":         [0.90, 0.45, 0.05, 1.0],   # dark orange
    },
}

# ── Attack pattern definitions ─────────────────────────────────────────────

ATTACK_PATTERNS = {
    "direct": {
        "label":       "→ DIRECT",
        "description": "Direct approach from NE bearing, cruise altitude",
        "path":        "direct_approach",
        "start":       (550.0, 550.0, 220.0),
        "wind":        False,
    },
    "nap_earth": {
        "label":       "↘ NAP-EARTH",
        "description": "Low-altitude sprint — minimises radar exposure",
        "path":        "low_fast_approach",
        "start":       (800.0, 0.0, 30.0),
        "wind":        True,
    },
    "spiral": {
        "label":       "◎ SPIRAL",
        "description": "High-altitude spiral descent — evasive profile",
        "path":        "spiral_descent",
        "start":       (650.0, 0.0, 280.0),
        "wind":        False,
    },
}

# ── Operator-selectable interceptor pad offsets (m south of dome edge) ────

PAD_OFFSETS = {
    "near": 50.0,    # 250 m from centre — quick launch, easy geometry
    "mid":  180.0,   # 380 m — balanced  [DEFAULT]
    "far":  380.0,   # 580 m — long-range challenge
}


def get_waypoints_for_path(path_name: str) -> list:
    return list(_WAYPOINTS.get(path_name, _DIRECT_APPROACH))
