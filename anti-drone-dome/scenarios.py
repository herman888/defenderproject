"""Attack scenario definitions for the anti-drone dome simulation."""

_DIRECT_APPROACH = [
    (15.0, 15.0, 8.0),
    (10.0, 12.0, 7.0),
    (8.0,   8.0, 6.0),
    (5.0,   6.0, 5.5),
    (4.0,   4.0, 5.0),
    (2.0,   2.0, 4.0),
    (1.0,   1.0, 4.0),
    (0.0,   0.0, 3.0),
]

_LOW_FAST_APPROACH = [
    (20.0,  0.0, 3.0),
    (14.0,  0.0, 2.5),
    (10.0,  0.0, 2.0),
    (6.0,   0.0, 2.0),
    (3.0,   0.0, 2.0),
    (0.0,   0.0, 2.0),
]

_SPIRAL_DESCENT = [
    (18.0,   0.0, 10.0),
    (10.0,  12.0,  8.0),
    (-8.0,  10.0,  6.0),
    (-10.0, -8.0,  4.0),
    (5.0,   -8.0,  3.0),
    (2.0,    2.0,  3.0),
    (0.0,    0.0,  3.0),
]

_WAYPOINTS = {
    "direct_approach": _DIRECT_APPROACH,
    "low_fast_approach": _LOW_FAST_APPROACH,
    "spiral_descent": _SPIRAL_DESCENT,
}

SCENARIOS = {
    "standard": {
        "intruder_start": (15.0, 15.0, 8.0),
        "intruder_speed": 12.0,
        "intruder_path": "direct_approach",
        "interceptor_start": (3.0, -3.0, 0.3),
        "interceptor_response_delay": 2.0,
        "wind": False,
        "description": "Single intruder, direct approach, standard conditions",
    },
    "fast_low": {
        "intruder_start": (20.0, 0.0, 3.0),
        "intruder_speed": 22.0,
        "intruder_path": "low_fast_approach",
        "interceptor_start": (-2.0, 0.0, 0.3),
        "interceptor_response_delay": 1.0,
        "wind": True,
        "description": "Fast low-altitude intruder, harder to detect",
    },
    "spiral": {
        "intruder_start": (18.0, 0.0, 10.0),
        "intruder_speed": 10.0,
        "intruder_path": "spiral_descent",
        "interceptor_start": (0.0, 0.0, 0.3),
        "interceptor_response_delay": 3.0,
        "wind": False,
        "description": "Spiraling descent attack pattern",
    },
}


def get_waypoints_for_path(path_name: str) -> list:
    return list(_WAYPOINTS.get(path_name, _DIRECT_APPROACH))
