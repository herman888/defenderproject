"""Small 2D radar + coordinate readout for multi-drone PyBullet runs (GUI mode).

Uses Matplotlib in a separate figure so it works with the stock PyBullet GUI
(no OpenGL overlay hooks). Top row: **Pause** / **Play** toggle and **Stop**.
The radar axes sit below; numeric XYZ for each drone is listed at the bottom.
"""

from __future__ import annotations

import numpy as np
import matplotlib.pyplot as plt
from matplotlib.widgets import Button


class RadarHUD:
    """Top-down (X–Y) polar view with per-drone world-frame XYZ text + transport controls."""

    def __init__(
        self,
        num_drones: int,
        max_range: float = 2.5,
        figsize=(4.2, 5.0),
    ):
        if num_drones < 1:
            raise ValueError("RadarHUD requires num_drones >= 1")
        self.num_drones = num_drones
        self.max_range = float(max_range)
        self.paused = False
        self.stop_requested = False
        plt.ion()
        self._fig = plt.figure(figsize=figsize, constrained_layout=False)
        self._fig.canvas.manager.set_window_title("Drone radar / coordinates")
        # Top: Pause (toggles to Play when paused) and Stop
        ax_pause = self._fig.add_axes([0.08, 0.905, 0.38, 0.072])
        ax_stop = self._fig.add_axes([0.50, 0.905, 0.42, 0.072])
        self._btn_pause = Button(ax_pause, "Pause")
        self._btn_pause.on_clicked(self._on_toggle_pause)
        self._btn_stop = Button(ax_stop, "Stop")
        self._btn_stop.on_clicked(self._on_stop)
        # Polar radar (figure coordinates: left, bottom, width, height)
        self._ax = self._fig.add_axes([0.12, 0.28, 0.76, 0.60], projection="polar")
        self._ax.set_theta_zero_location("N")
        self._ax.set_theta_direction(-1)
        self._ax.set_ylim(0, self.max_range)
        self._ax.set_yticklabels([])
        self._ax.grid(True, linestyle=":", alpha=0.6)
        self._ax.set_title("Planar radar (world XY)", fontsize=9, pad=8)
        # Coordinate block under radar
        self._text = self._fig.text(
            0.03,
            0.02,
            "",
            fontsize=8,
            family="monospace",
            verticalalignment="bottom",
            horizontalalignment="left",
        )
        self._cmap = plt.get_cmap("tab10")

    def _on_toggle_pause(self, event) -> None:
        self.paused = not self.paused
        self._btn_pause.label.set_text("Play" if self.paused else "Pause")

    def _on_stop(self, event) -> None:
        self.stop_requested = True

    def update(self, positions: np.ndarray) -> None:
        """Update display from (NUM_DRONES, 3) array of world [x, y, z]."""
        if self._fig is None:
            return
        pos = np.asarray(positions, dtype=float).reshape(self.num_drones, 3)
        xy = pos[:, 0:2]
        r = np.linalg.norm(xy, axis=1)
        theta = np.arctan2(xy[:, 1], xy[:, 0])
        self._ax.clear()
        self._ax.set_theta_zero_location("N")
        self._ax.set_theta_direction(-1)
        self._ax.set_ylim(0, self.max_range)
        self._ax.set_yticklabels([])
        self._ax.grid(True, linestyle=":", alpha=0.6)
        self._ax.set_title("Planar radar (world XY)", fontsize=9, pad=8)
        for i in range(self.num_drones):
            c = self._cmap(i % 10)
            self._ax.scatter(theta[i], r[i], s=55, color=c, edgecolor="k", linewidths=0.4, zorder=3)
        lines = [
            f"drone {i}:  x={pos[i, 0]:+7.3f}  y={pos[i, 1]:+7.3f}  z={pos[i, 2]:+7.3f}"
            for i in range(self.num_drones)
        ]
        self._text.set_text("\n".join(lines))
        self._fig.canvas.draw_idle()
        self._fig.canvas.flush_events()
        plt.pause(0.0001)

    def close(self) -> None:
        if self._fig is not None:
            plt.close(self._fig)
            self._fig = None
