"""Qt-free control-state helpers shared by the dashboard and tests."""

from __future__ import annotations

import math


class SimControl:
    def __init__(self):
        self.paused = False
        self.stopped = False
        self.restart = False
        self.speed = 1
        self.pending_intruder = "shahed136"
        self.selected_mission = None
        self.selected_speed = 1.0
        self.selected_pad = "mid"
        self.selected_pattern = "direct"
        self.runtime_speed = 1.0
        self.radar_failure = False
        self.camera_failure = False
        self.actuator_failure = False
        self.camera_zoom_pending = None
        self.camera_view_pending = None


def altitude_time_window(sim_time: float) -> tuple[float, float, list[tuple[float, str]]]:
    if sim_time <= 30.0:
        end = 30.0
        step = 5
    elif sim_time <= 60.0:
        end = 60.0
        step = 10
    elif sim_time <= 120.0:
        end = 120.0
        step = 20
    else:
        end = float(sim_time)
        step = 20
    start = max(0.0, end - 120.0)
    first_tick = int(math.ceil(start / step) * step)
    ticks = [
        (float(value), f"{value}s")
        for value in range(first_tick, int(end) + 1, step)
    ]
    return start, end, ticks


# Back-compat alias used by existing tests / dashboard helpers.
_altitude_time_window = altitude_time_window
