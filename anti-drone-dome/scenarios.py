"""Attack scenario definitions — 200 m dome scale."""

# ── Waypoint paths ─────────────────────────────────────────────────────────
# All coordinates in metres.  Dome centre = (0, 0, 0).  North = +Y.

_DIRECT_APPROACH = [
    (550.0,  550.0, 120.0),   # ~778 m diagonal — well outside radar
    (360.0,  420.0,  95.0),
    (240.0,  280.0,  80.0),
    (150.0,  180.0,  65.0),
    ( 90.0,  100.0,  55.0),
    ( 40.0,   45.0,  45.0),
    (  0.0,    0.0,  40.0),   # dome centre
]

_LOW_FAST_APPROACH = [
    (800.0,   0.0, 30.0),     # 800 m due east, nap-of-earth
    (560.0,   0.0, 25.0),
    (360.0,   0.0, 22.0),
    (180.0,   0.0, 18.0),
    ( 60.0,   0.0, 15.0),
    (  0.0,   0.0, 12.0),
]

_SPIRAL_DESCENT = [
    ( 650.0,    0.0, 260.0),
    ( 360.0,  440.0, 210.0),
    (-300.0,  380.0, 160.0),
    (-380.0, -300.0, 110.0),
    ( 180.0, -300.0,  70.0),
    (  60.0,   60.0,  45.0),
    (   0.0,    0.0,  40.0),
]

_WAYPOINTS = {
    "direct_approach":   _DIRECT_APPROACH,
    "low_fast_approach": _LOW_FAST_APPROACH,
    "spiral_descent":    _SPIRAL_DESCENT,
}

# ── Scenario table ─────────────────────────────────────────────────────────
# interceptor_start is NO LONGER here — it comes from the pad-distance
# selection made by the operator in the dashboard.

SCENARIOS = {
    "standard": {
        "intruder_start":            (550.0, 550.0, 120.0),
        "intruder_speed":             55.0,    # m/s — loitering-munition cruise
        "intruder_path":              "direct_approach",
        "interceptor_response_delay":  4.0,    # s — alert → arm → launch
        "wind":                       False,
        "description": "Single intruder direct approach — standard conditions",
    },
    "fast_low": {
        "intruder_start":            (800.0, 0.0, 30.0),
        "intruder_speed":             88.0,    # m/s — ~320 km/h, nap-of-earth
        "intruder_path":              "low_fast_approach",
        "interceptor_response_delay":  2.5,
        "wind":                       True,
        "description": "High-speed nap-of-earth approach — radar challenged",
    },
    "spiral": {
        "intruder_start":            (650.0, 0.0, 260.0),
        "intruder_speed":             45.0,
        "intruder_path":              "spiral_descent",
        "interceptor_response_delay":  6.0,    # harder timing — tests limits
        "wind":                       False,
        "description": "Spiralling descent — evasive attack pattern",
    },
}

# Operator-selectable interceptor pad offsets (metres south of dome edge)
PAD_OFFSETS = {
    "near": 50.0,    # (0, -250, 5)  — quick launch, easy intercept
    "mid":  180.0,   # (0, -380, 5)  — balanced [DEFAULT]
    "far":  380.0,   # (0, -580, 5)  — long-range challenge
}


def get_waypoints_for_path(path_name: str) -> list:
    return list(_WAYPOINTS.get(path_name, _DIRECT_APPROACH))
