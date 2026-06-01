"""Real-time matplotlib radar dashboard with sim controls."""

import math
import time
import matplotlib
matplotlib.use("TkAgg")
import matplotlib.pyplot as plt
import matplotlib.patches as patches
from matplotlib.widgets import Button
import numpy as np


class SimControl:
    """Shared state between dashboard buttons and the main sim loop."""
    def __init__(self):
        self.paused = False
        self.stopped = False
        self.speed = 1  # physics steps per visual frame: 1=normal, 2=fast, 0=half


class Dashboard:
    def __init__(self, dome_radius: float = 10.0, sim_control: SimControl = None):
        self._dome_radius = dome_radius
        self._ctrl = sim_control
        self._event_log = []
        self._intruder_trail = []
        self._interceptor_trail = []
        self._radar_angle = 0.0
        self._step_count = 0
        self._speed_labels = ["0.5x", "1x", "2x"]
        self._speed_values = [0, 1, 2]
        self._speed_idx = 1

        plt.ion()
        self._fig = plt.figure(figsize=(14, 8))
        self._fig.patch.set_facecolor((0.05, 0.05, 0.08))
        self._fig.suptitle(
            "ANTI-DRONE DOME — ACTIVE DEFENSE SYSTEM",
            color="lime", fontsize=13, fontweight="bold", fontfamily="monospace"
        )

        # Main layout: radar left, status right, buttons bottom
        gs = self._fig.add_gridspec(2, 2, height_ratios=[9, 1], hspace=0.35, wspace=0.3)
        self._ax_radar = self._fig.add_subplot(gs[0, 0])
        self._ax_status = self._fig.add_subplot(gs[0, 1])

        self._setup_radar_ax()
        self._setup_status_ax()
        self._setup_buttons(gs)

        plt.pause(0.01)

    def _setup_radar_ax(self):
        ax = self._ax_radar
        ax.set_facecolor((0.05, 0.05, 0.1))
        ax.set_xlim(-22, 22)
        ax.set_ylim(-22, 22)
        ax.set_aspect("equal")
        ax.set_title("RADAR DISPLAY", color="lime", fontfamily="monospace", fontsize=10)
        ax.tick_params(colors="gray")
        for spine in ax.spines.values():
            spine.set_color("gray")
        for r in [5, 10, 15, 20]:
            circle = plt.Circle((0, 0), r, color=(0.3, 0.3, 0.3), fill=False, linewidth=0.7, linestyle="--")
            ax.add_patch(circle)
            ax.text(r * 0.7071, r * 0.7071, f"{r}m", color="gray", fontsize=7, fontfamily="monospace")
        for label, pos in [("N", (0, 21)), ("S", (0, -21)), ("E", (21, 0)), ("W", (-21, 0))]:
            ax.text(pos[0], pos[1], label, color="gray", fontsize=9, ha="center", va="center",
                    fontfamily="monospace")

    def _setup_status_ax(self):
        ax = self._ax_status
        ax.set_facecolor((0.05, 0.05, 0.08))
        ax.set_xlim(0, 1)
        ax.set_ylim(0, 1)
        ax.axis("off")

    def _setup_buttons(self, gs):
        btn_row = gs[1, :]
        btn_gs = btn_row.subgridspec(1, 3, wspace=0.4)

        ax_pause = self._fig.add_subplot(btn_gs[0, 0])
        ax_stop  = self._fig.add_subplot(btn_gs[0, 1])
        ax_speed = self._fig.add_subplot(btn_gs[0, 2])

        self._btn_pause = Button(ax_pause, "⏸  PAUSE", color=(0.1, 0.3, 0.1), hovercolor=(0.2, 0.5, 0.2))
        self._btn_stop  = Button(ax_stop,  "⏹  STOP",  color=(0.3, 0.1, 0.1), hovercolor=(0.6, 0.1, 0.1))
        self._btn_speed = Button(ax_speed, "▶▶ 1x SPEED", color=(0.1, 0.1, 0.3), hovercolor=(0.2, 0.2, 0.5))

        for btn in (self._btn_pause, self._btn_stop, self._btn_speed):
            btn.label.set_color("white")
            btn.label.set_fontfamily("monospace")
            btn.label.set_fontsize(9)

        self._btn_pause.on_clicked(self._on_pause)
        self._btn_stop.on_clicked(self._on_stop)
        self._btn_speed.on_clicked(self._on_speed)

    def _on_pause(self, _event):
        if self._ctrl is None:
            return
        self._ctrl.paused = not self._ctrl.paused
        label = "▶  RESUME" if self._ctrl.paused else "⏸  PAUSE"
        color = (0.3, 0.1, 0.1) if self._ctrl.paused else (0.1, 0.3, 0.1)
        self._btn_pause.label.set_text(label)
        self._btn_pause.ax.set_facecolor(color)
        self._fig.canvas.draw_idle()

    def _on_stop(self, _event):
        if self._ctrl is None:
            return
        self._ctrl.stopped = True
        self._btn_stop.label.set_text("■  STOPPED")
        self._btn_stop.ax.set_facecolor((0.6, 0.0, 0.0))
        self._fig.canvas.draw_idle()

    def _on_speed(self, _event):
        if self._ctrl is None:
            return
        self._speed_idx = (self._speed_idx + 1) % len(self._speed_labels)
        self._ctrl.speed = self._speed_values[self._speed_idx]
        label = f"▶▶ {self._speed_labels[self._speed_idx]} SPEED"
        self._btn_speed.label.set_text(label)
        self._fig.canvas.draw_idle()

    def _clear_radar(self):
        self._ax_radar.cla()
        self._setup_radar_ax()

    def update(self, sim_state: dict):
        status = sim_state.get("dome_status", "CLEAR")
        intruder_pos = sim_state.get("intruder_pos")
        interceptor_pos = sim_state.get("interceptor_pos")
        radar_return = sim_state.get("radar_return", {})
        predicted_intercept = sim_state.get("predicted_intercept")
        events = sim_state.get("events", [])

        for ev in events:
            ts = time.strftime("%H:%M:%S")
            self._event_log.append(f"[{ts}] {ev}")
        self._event_log = self._event_log[-5:]

        self._clear_radar()

        dome_color = {"CLEAR": "lime", "TRACKING": "yellow", "BREACH": "orange", "INTERCEPTED": "red"}.get(status, "lime")
        dome_circle = plt.Circle((0, 0), self._dome_radius, color=dome_color, fill=False, linewidth=2)
        self._ax_radar.add_patch(dome_circle)

        self._radar_angle = (self._radar_angle + 15) % 360
        rad = math.radians(self._radar_angle)
        self._ax_radar.plot([0, 20 * math.cos(rad)], [0, 20 * math.sin(rad)],
                            color=(0.0, 0.5, 0.0), linewidth=1, alpha=0.7)

        if intruder_pos:
            self._intruder_trail.append(intruder_pos)
            if len(self._intruder_trail) > 20:
                self._intruder_trail = self._intruder_trail[-20:]
            if len(self._intruder_trail) > 1:
                trail = self._intruder_trail
                for i in range(1, len(trail)):
                    alpha = 0.1 + 0.9 * i / len(trail)
                    self._ax_radar.plot([trail[i-1][0], trail[i][0]], [trail[i-1][1], trail[i][1]],
                                        color="red", alpha=alpha, linewidth=1.2)
            self._ax_radar.plot(intruder_pos[0], intruder_pos[1], "r.", markersize=12)
            self._ax_radar.text(intruder_pos[0] + 0.5, intruder_pos[1] + 0.5, "INTRUDER",
                                color="red", fontsize=6, fontfamily="monospace")

        if interceptor_pos:
            self._interceptor_trail.append(interceptor_pos)
            if len(self._interceptor_trail) > 20:
                self._interceptor_trail = self._interceptor_trail[-20:]
            if len(self._interceptor_trail) > 1:
                trail = self._interceptor_trail
                for i in range(1, len(trail)):
                    alpha = 0.1 + 0.9 * i / len(trail)
                    self._ax_radar.plot([trail[i-1][0], trail[i][0]], [trail[i-1][1], trail[i][1]],
                                        color="cyan", alpha=alpha, linewidth=1.2)
            self._ax_radar.plot(interceptor_pos[0], interceptor_pos[1], "c^", markersize=10)
            self._ax_radar.text(interceptor_pos[0] + 0.5, interceptor_pos[1] + 0.5, "INTERCEPTOR",
                                color="cyan", fontsize=6, fontfamily="monospace")

        if interceptor_pos and predicted_intercept:
            self._ax_radar.plot(
                [interceptor_pos[0], predicted_intercept[0]],
                [interceptor_pos[1], predicted_intercept[1]],
                color="yellow", linewidth=1, linestyle="--", alpha=0.8,
            )

        # Status panel
        self._ax_status.cla()
        self._ax_status.set_facecolor((0.05, 0.05, 0.08))
        self._ax_status.set_xlim(0, 1)
        self._ax_status.set_ylim(0, 1)
        self._ax_status.axis("off")

        status_color = {"CLEAR": "lime", "TRACKING": "yellow", "BREACH": "orange", "INTERCEPTED": "red"}.get(status, "white")
        self._ax_status.text(0.5, 0.92, f"● {status}", color=status_color, fontsize=18,
                             ha="center", va="top", fontweight="bold", fontfamily="monospace")

        y = 0.80
        if intruder_pos:
            dist = math.sqrt(sum(v**2 for v in intruder_pos))
            speed = sim_state.get("intruder_speed", 0.0)
            self._ax_status.text(0.05, y, "INTRUDER", color="red", fontsize=9, fontfamily="monospace", fontweight="bold")
            self._ax_status.text(0.05, y - 0.05, f"  Range: {dist:.1f}m", color="white", fontsize=8, fontfamily="monospace")
            self._ax_status.text(0.05, y - 0.10, f"  Alt:   {intruder_pos[2]:.1f}m", color="white", fontsize=8, fontfamily="monospace")
            self._ax_status.text(0.05, y - 0.15, f"  Speed: {speed:.1f}m/s", color="white", fontsize=8, fontfamily="monospace")
            y -= 0.25

        if interceptor_pos and intruder_pos:
            sep = math.sqrt(sum((interceptor_pos[i] - intruder_pos[i])**2 for i in range(3)))
            tti = sim_state.get("tti", float("inf"))
            i_speed = sim_state.get("interceptor_speed", 0.0)
            tti_str = f"{tti:.1f}s" if tti < 999 else "N/A"
            self._ax_status.text(0.05, y, "INTERCEPTOR", color="cyan", fontsize=9, fontfamily="monospace", fontweight="bold")
            self._ax_status.text(0.05, y - 0.05, f"  Sep:   {sep:.1f}m", color="white", fontsize=8, fontfamily="monospace")
            self._ax_status.text(0.05, y - 0.10, f"  TTI:   {tti_str}", color="white", fontsize=8, fontfamily="monospace")
            self._ax_status.text(0.05, y - 0.15, f"  Speed: {i_speed:.1f}m/s", color="white", fontsize=8, fontfamily="monospace")
            y -= 0.25

        if radar_return.get("detected"):
            snr = radar_return.get("snr", 0)
            confidence = sim_state.get("track_confidence", 0.0)
            ldt = sim_state.get("last_detection_time")
            ldt_str = time.strftime("%H:%M:%S", time.localtime(ldt)) if ldt else "—"
            self._ax_status.text(0.05, y, "RADAR", color="lime", fontsize=9, fontfamily="monospace", fontweight="bold")
            self._ax_status.text(0.05, y - 0.05, f"  SNR:   {snr:.1f}dB", color="white", fontsize=8, fontfamily="monospace")
            self._ax_status.text(0.05, y - 0.10, f"  Conf:  {confidence*100:.0f}%", color="white", fontsize=8, fontfamily="monospace")
            self._ax_status.text(0.05, y - 0.15, f"  Last:  {ldt_str}", color="white", fontsize=8, fontfamily="monospace")
            y -= 0.25

        self._ax_status.text(0.05, y, "EVENT LOG", color="gray", fontsize=8, fontfamily="monospace", fontweight="bold")
        for i, ev in enumerate(reversed(self._event_log)):
            self._ax_status.text(0.05, y - 0.06 * (i + 1), f"  {ev}", color="gray", fontsize=7, fontfamily="monospace")

        if self._ctrl and self._ctrl.paused:
            self._ax_radar.text(0, 0, "— PAUSED —", color="yellow", fontsize=16,
                                ha="center", va="center", fontweight="bold", fontfamily="monospace",
                                bbox=dict(facecolor="black", alpha=0.7, edgecolor="yellow"))

        try:
            self._fig.canvas.draw_idle()
            self._fig.canvas.flush_events()
        except Exception:
            pass

    def add_event(self, message: str):
        ts = time.strftime("%H:%M:%S")
        self._event_log.append(f"[{ts}] {message}")
        self._event_log = self._event_log[-5:]

    def close(self):
        try:
            plt.close(self._fig)
        except Exception:
            pass
