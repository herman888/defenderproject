"""Dome kill zone: hemispherical boundary, status machine, breach and intercept detection."""

import math
import time


class DomeKillZone:
    def __init__(self, center=(0.0, 0.0, 0.0), radius: float = 10.0):
        self._center = center
        self._radius = radius
        self._status = "CLEAR"
        self._breach_history = []
        self._first_detection_time = None
        self._breach_time = None
        self._intercept_time = None

    def _dist(self, position: tuple) -> float:
        return math.sqrt(sum((position[i] - self._center[i]) ** 2 for i in range(3)))

    def is_inside(self, position: tuple) -> bool:
        return self._dist(position) < self._radius

    def distance_to_boundary(self, position: tuple) -> float:
        return self._radius - self._dist(position)

    def check_breach(self, intruder_position: tuple) -> dict:
        if self.is_inside(intruder_position):
            event = {
                "breached": True,
                "position": intruder_position,
                "time": time.time(),
                "distance_to_center": self._dist(intruder_position),
            }
            self._breach_history.append(event)
            return event
        return None

    def check_intercept(self, interceptor_position: tuple, intruder_position: tuple, intercept_radius: float = 3.0) -> bool:
        dist = math.sqrt(sum((interceptor_position[i] - intruder_position[i]) ** 2 for i in range(3)))
        return dist <= intercept_radius

    def update_status(self, intruder_position: tuple, intruder_detected: bool,
                      interceptor_position: tuple = None, intercept_radius: float = 3.0):
        old_status = self._status
        dist_from_center = self._dist(intruder_position)

        if self._status == "INTERCEPTED":
            pass
        elif interceptor_position is not None and self._status in ("TRACKING", "BREACH"):
            if self.check_intercept(interceptor_position, intruder_position, intercept_radius):
                self._status = "INTERCEPTED"
                self._intercept_time = time.time()
        elif self.is_inside(intruder_position) and intruder_detected:
            self._status = "BREACH"
            if self._breach_time is None:
                self._breach_time = time.time()
        elif intruder_detected and dist_from_center <= self._radius * 2:
            if self._status == "CLEAR":
                self._status = "TRACKING"
                self._first_detection_time = time.time()
        elif not intruder_detected and self._status in ("TRACKING",):
            self._status = "CLEAR"

        if self._status != old_status:
            print(f"DOME STATUS: {old_status} -> {self._status}")

    def get_status(self) -> str:
        return self._status

    def get_breach_history(self) -> list:
        return list(self._breach_history)

    def max_penetration_depth(self) -> float:
        if not self._breach_history:
            return 0.0
        return max(self._radius - e["distance_to_center"] for e in self._breach_history)

    @property
    def first_detection_time(self):
        return self._first_detection_time

    @property
    def breach_time(self):
        return self._breach_time

    @property
    def intercept_time(self):
        return self._intercept_time
