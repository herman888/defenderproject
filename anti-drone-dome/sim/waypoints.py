"""Waypoint navigator: advances through an ordered list of 3D targets."""

import math


_DEFAULT_ATTACK_PATH = [
    (15.0, 15.0, 8.0),
    (10.0, 12.0, 7.0),
    (8.0,  8.0,  6.0),
    (5.0,  6.0,  5.5),
    (4.0,  4.0,  5.0),
    (2.0,  2.0,  4.0),
    (1.0,  1.0,  4.0),
    (0.0,  0.0,  3.0),
]


class WaypointNavigator:
    def __init__(self, waypoints=None, proximity_threshold: float = 1.5):
        self._waypoints = waypoints if waypoints is not None else list(_DEFAULT_ATTACK_PATH)
        self._index = 0
        self._threshold = proximity_threshold

    def get_current_target(self) -> tuple:
        if self._index >= len(self._waypoints):
            return self._waypoints[-1]
        return self._waypoints[self._index]

    def update(self, drone_position: tuple):
        if self._index >= len(self._waypoints):
            return
        target = self._waypoints[self._index]
        dist = math.sqrt(sum((drone_position[i] - target[i]) ** 2 for i in range(3)))
        if dist < self._threshold:
            self._index += 1

    def is_complete(self) -> bool:
        return self._index >= len(self._waypoints)

    def progress(self) -> float:
        return self._index / len(self._waypoints)
