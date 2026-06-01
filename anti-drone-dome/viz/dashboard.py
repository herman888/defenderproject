"""Real-time matplotlib dashboard: radar top-down + altitude side view + controls."""

import math
import time
import numpy as np
import matplotlib
matplotlib.use("TkAgg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.widgets import Button


class SimControl:
    def __init__(self):
        self.paused  = False
        self.stopped = False
        self.speed   = 1  # 0=half, 1=normal, 2=double


class Dashboard:
    def __init__(self, dome_radius: float = 10.0, sim_control: SimControl = None):
        self._dome_radius = dome_radius
        self._ctrl        = sim_control
        self._event_log   = []
        self._intruder_trail        = []
        self._interceptor_trail     = []
        self._intruder_alt_trail    = []
        self._interceptor_alt_trail = []
        self._radar_angle  = 0.0
        self._last_draw    = 0.0
        self._speed_labels = ["0.5x", "1x", "2x"]
        self._speed_values = [0, 1, 2]
        self._speed_idx    = 1

        plt.ion()
        self._fig = plt.figure(figsize=(16, 9))
        self._fig.patch.set_facecolor((0.05, 0.05, 0.08))
        self._fig.suptitle(
            "ANTI-DRONE DOME — ACTIVE DEFENSE SYSTEM",
            color="lime", fontsize=13, fontweight="bold", fontfamily="monospace"
        )

        gs = self._fig.add_gridspec(
            2, 2,
            height_ratios=[8, 1],
            hspace=0.4, wspace=0.3,
            left=0.05, right=0.97, top=0.92, bottom=0.06
        )
        self._ax_radar = self._fig.add_subplot(gs[0, 0])
        self._ax_side  = self._fig.add_subplot(gs[0, 1])

        self._setup_radar_ax()
        self._setup_side_ax()
        self._setup_buttons(gs)
        self._init_artists()
        plt.pause(0.01)

    # ------------------------------------------------------------------
    def _setup_radar_ax(self):
        ax = self._ax_radar
        ax.set_facecolor((0.03, 0.05, 0.1))
        ax.set_xlim(-22, 22)
        ax.set_ylim(-22, 22)
        ax.set_aspect("equal")
        ax.set_title("RADAR — TOP DOWN (X/Y)", color="lime", fontfamily="monospace", fontsize=10)
        ax.tick_params(colors="gray")
        for spine in ax.spines.values():
            spine.set_color("gray")
        for r in [5, 10, 15, 20]:
            ax.add_patch(plt.Circle((0, 0), r, color=(0.25, 0.25, 0.25),
                                    fill=False, linewidth=0.7, linestyle="--"))
            ax.text(r * 0.707, r * 0.707, f"{r}m", color="gray",
                    fontsize=7, fontfamily="monospace")
        for lbl, pos in [("N",(0,21)),("S",(0,-21)),("E",(21,0)),("W",(-21,0))]:
            ax.text(pos[0], pos[1], lbl, color="gray", fontsize=8,
                    ha="center", va="center", fontfamily="monospace")

    def _setup_side_ax(self):
        ax = self._ax_side
        ax.set_facecolor((0.03, 0.05, 0.1))
        ax.set_xlim(-22, 22)
        ax.set_ylim(-1, 18)
        ax.set_title("ALTITUDE VIEW (X/Z)", color="cyan", fontfamily="monospace", fontsize=10)
        ax.set_xlabel("X position (m)", color="gray", fontsize=8)
        ax.set_ylabel("Altitude (m)",   color="gray", fontsize=8)
        ax.tick_params(colors="gray")
        for spine in ax.spines.values():
            spine.set_color("gray")
        for r in [5, 10]:
            ax.add_patch(plt.Circle((0, 0), r, color=(0.25, 0.25, 0.25),
                                    fill=False, linewidth=0.7, linestyle="--"))
        ax.axhline(0, color=(0.3, 0.3, 0.3), linewidth=0.8)
        ax.text(0, -0.5, "GROUND", color="gray", fontsize=7,
                ha="center", fontfamily="monospace")

    def _init_artists(self):
        """Create all dynamic artists once — update() only calls set_data/set_text."""
        ax = self._ax_radar

        # Dome circle
        self._dome_circle = mpatches.Circle((0, 0), self._dome_radius,
                                             color="lime", fill=False, linewidth=2)
        ax.add_patch(self._dome_circle)

        # Radar sweep line
        self._radar_sweep, = ax.plot([], [], color=(0, 0.6, 0), linewidth=1.5, alpha=0.7)

        # Radar station marker + label
        self._radar_marker, = ax.plot([], [], "gs", markersize=8)
        self._radar_label   = ax.text(0, 0, "RADAR", color="lime", fontsize=6,
                                      fontfamily="monospace", visible=False)

        # Intruder trail + dot + label  (radar view)
        self._intruder_trail_r,  = ax.plot([], [], color="red",  alpha=0.5, linewidth=1.5)
        self._intruder_dot_r,    = ax.plot([], [], "ro", markersize=12)
        self._intruder_label_r   = ax.text(0, 0, "INTRUDER", color="red",
                                            fontsize=7, fontfamily="monospace", visible=False)

        # Interceptor trail + dot + label  (radar view)
        self._intercept_trail_r, = ax.plot([], [], color="cyan", alpha=0.5, linewidth=1.5)
        self._intercept_dot_r,   = ax.plot([], [], "c^", markersize=12)
        self._intercept_label_r  = ax.text(0, 0, "INTERCEPTOR", color="cyan",
                                            fontsize=7, fontfamily="monospace", visible=False)

        # Prediction line + marker
        self._pred_line, = ax.plot([], [], color="yellow", linewidth=1,
                                   linestyle="--", alpha=0.8)
        self._pred_dot,  = ax.plot([], [], "y+", markersize=10)

        # Status box
        self._status_text = ax.text(
            22, 22, "STATUS: CLEAR", color="lime", fontsize=10,
            ha="right", va="top", fontweight="bold", fontfamily="monospace",
            bbox=dict(facecolor=(0.05, 0.05, 0.08), alpha=0.8, edgecolor="lime", pad=3)
        )

        # Paused overlay (hidden until paused)
        self._paused_text = ax.text(
            0, 0, "-- PAUSED --", color="yellow", fontsize=16,
            ha="center", va="center", fontweight="bold", fontfamily="monospace",
            bbox=dict(facecolor="black", alpha=0.7, edgecolor="yellow"), visible=False
        )

        # ── Side view ──────────────────────────────────────────────────────
        ax = self._ax_side

        # Dome arc (drawn once, color updated)
        theta = np.linspace(0, math.pi, 60)
        self._dome_arc,  = ax.plot(self._dome_radius * np.cos(theta),
                                    self._dome_radius * np.sin(theta),
                                    color="lime", linewidth=2, alpha=0.8)
        self._dome_base, = ax.plot([-self._dome_radius, self._dome_radius], [0, 0],
                                    color="lime", linewidth=2, alpha=0.8)

        # Intruder trail + dot + label  (side view)
        self._intruder_trail_s,  = ax.plot([], [], color="red",  alpha=0.5, linewidth=1.5)
        self._intruder_dot_s,    = ax.plot([], [], "ro", markersize=12)
        self._intruder_label_s   = ax.text(0, 0, "", color="red",
                                            fontsize=7, fontfamily="monospace", visible=False)

        # Interceptor trail + dot + label  (side view)
        self._intercept_trail_s, = ax.plot([], [], color="cyan", alpha=0.5, linewidth=1.5)
        self._intercept_dot_s,   = ax.plot([], [], "c^", markersize=12)
        self._intercept_label_s  = ax.text(0, 0, "", color="cyan",
                                            fontsize=7, fontfamily="monospace", visible=False)

        # Info text block
        self._info_text = ax.text(
            0.02, 0.98, "", transform=ax.transAxes,
            color="white", fontsize=7, fontfamily="monospace",
            va="top", ha="left",
            bbox=dict(facecolor=(0.03, 0.05, 0.1), alpha=0.85, edgecolor="gray", pad=4)
        )

    def _setup_buttons(self, gs):
        btn_row = gs[1, :]
        btn_gs  = btn_row.subgridspec(1, 3, wspace=0.4)

        ax_pause = self._fig.add_subplot(btn_gs[0, 0])
        ax_stop  = self._fig.add_subplot(btn_gs[0, 1])
        ax_speed = self._fig.add_subplot(btn_gs[0, 2])

        self._btn_pause = Button(ax_pause, "|| PAUSE",    color=(0.1,0.3,0.1), hovercolor=(0.2,0.5,0.2))
        self._btn_stop  = Button(ax_stop,  "[] STOP",     color=(0.3,0.1,0.1), hovercolor=(0.6,0.1,0.1))
        self._btn_speed = Button(ax_speed, ">> 1x SPEED", color=(0.1,0.1,0.3), hovercolor=(0.2,0.2,0.5))

        for btn in (self._btn_pause, self._btn_stop, self._btn_speed):
            btn.label.set_color("white")
            btn.label.set_fontfamily("monospace")
            btn.label.set_fontsize(9)

        self._btn_pause.on_clicked(self._on_pause)
        self._btn_stop.on_clicked(self._on_stop)
        self._btn_speed.on_clicked(self._on_speed)

    def _on_pause(self, _):
        if not self._ctrl: return
        self._ctrl.paused = not self._ctrl.paused
        self._btn_pause.label.set_text(">  RESUME" if self._ctrl.paused else "|| PAUSE")
        self._btn_pause.ax.set_facecolor((0.4,0.1,0.1) if self._ctrl.paused else (0.1,0.3,0.1))
        self._fig.canvas.draw_idle()

    def _on_stop(self, _):
        if not self._ctrl: return
        self._ctrl.stopped = True
        self._btn_stop.label.set_text("[] STOPPED")
        self._btn_stop.ax.set_facecolor((0.6,0.0,0.0))
        self._fig.canvas.draw_idle()

    def _on_speed(self, _):
        if not self._ctrl: return
        self._speed_idx = (self._speed_idx + 1) % len(self._speed_labels)
        self._ctrl.speed = self._speed_values[self._speed_idx]
        self._btn_speed.label.set_text(f">> {self._speed_labels[self._speed_idx]} SPEED")
        self._fig.canvas.draw_idle()

    # ------------------------------------------------------------------
    def update(self, sim_state: dict):
        now = time.time()
        if now - self._last_draw < 0.20:
            return
        self._last_draw = now

        status          = sim_state.get("dome_status", "CLEAR")
        intruder_pos    = sim_state.get("intruder_pos")
        interceptor_pos = sim_state.get("interceptor_pos")
        radar_return    = sim_state.get("radar_return", {})
        predicted_ic    = sim_state.get("predicted_intercept")
        events          = sim_state.get("events", [])

        for ev in events:
            self._event_log.append(f"[{time.strftime('%H:%M:%S')}] {ev}")
        self._event_log = self._event_log[-6:]

        dome_color = {"CLEAR":"lime","TRACKING":"yellow","BREACH":"orange",
                      "INTERCEPTED":"red"}.get(status, "lime")

        # ── Dome color ────────────────────────────────────────────────────
        self._dome_circle.set_color(dome_color)
        self._dome_arc.set_color(dome_color)
        self._dome_base.set_color(dome_color)

        # ── Radar sweep ───────────────────────────────────────────────────
        self._radar_angle = (self._radar_angle + 15) % 360
        rad = math.radians(self._radar_angle)
        rs  = sim_state.get("radar_station", [0, -self._dome_radius, 3])
        self._radar_sweep.set_data(
            [rs[0], rs[0] + 22 * math.cos(rad)],
            [rs[1], rs[1] + 22 * math.sin(rad)]
        )
        self._radar_marker.set_data([rs[0]], [rs[1]])
        self._radar_label.set_position((rs[0] + 0.5, rs[1] + 0.5))
        self._radar_label.set_visible(True)

        # ── Intruder (radar view) ─────────────────────────────────────────
        if intruder_pos:
            self._intruder_trail.append(intruder_pos[:2])
            self._intruder_trail = self._intruder_trail[-40:]
            xs = [p[0] for p in self._intruder_trail]
            ys = [p[1] for p in self._intruder_trail]
            self._intruder_trail_r.set_data(xs, ys)
            self._intruder_dot_r.set_data([intruder_pos[0]], [intruder_pos[1]])
            self._intruder_label_r.set_position((intruder_pos[0] + 0.6, intruder_pos[1] + 0.6))
            self._intruder_label_r.set_visible(True)
        else:
            self._intruder_trail_r.set_data([], [])
            self._intruder_dot_r.set_data([], [])
            self._intruder_label_r.set_visible(False)

        # ── Interceptor (radar view) ──────────────────────────────────────
        if interceptor_pos:
            self._interceptor_trail.append(interceptor_pos[:2])
            self._interceptor_trail = self._interceptor_trail[-40:]
            xs = [p[0] for p in self._interceptor_trail]
            ys = [p[1] for p in self._interceptor_trail]
            self._intercept_trail_r.set_data(xs, ys)
            self._intercept_dot_r.set_data([interceptor_pos[0]], [interceptor_pos[1]])
            self._intercept_label_r.set_position((interceptor_pos[0] + 0.6, interceptor_pos[1] + 0.6))
            self._intercept_label_r.set_visible(True)
        else:
            self._intercept_trail_r.set_data([], [])
            self._intercept_dot_r.set_data([], [])
            self._intercept_label_r.set_visible(False)

        # ── Prediction line ───────────────────────────────────────────────
        if interceptor_pos and predicted_ic:
            self._pred_line.set_data(
                [interceptor_pos[0], predicted_ic[0]],
                [interceptor_pos[1], predicted_ic[1]]
            )
            self._pred_dot.set_data([predicted_ic[0]], [predicted_ic[1]])
        else:
            self._pred_line.set_data([], [])
            self._pred_dot.set_data([], [])

        # ── Status text ───────────────────────────────────────────────────
        self._status_text.set_text(f"STATUS: {status}")
        self._status_text.set_color(dome_color)
        self._status_text.get_bbox_patch().set_edgecolor(dome_color)

        # ── Paused overlay ────────────────────────────────────────────────
        self._paused_text.set_visible(bool(self._ctrl and self._ctrl.paused))

        # ── Intruder (side view) ──────────────────────────────────────────
        if intruder_pos:
            self._intruder_alt_trail.append((intruder_pos[0], intruder_pos[2]))
            self._intruder_alt_trail = self._intruder_alt_trail[-40:]
            self._intruder_trail_s.set_data(
                [p[0] for p in self._intruder_alt_trail],
                [p[1] for p in self._intruder_alt_trail]
            )
            self._intruder_dot_s.set_data([intruder_pos[0]], [intruder_pos[2]])
            self._intruder_label_s.set_text(f"INTRUDER\n{intruder_pos[2]:.1f}m")
            self._intruder_label_s.set_position((intruder_pos[0] + 0.3, intruder_pos[2] + 0.3))
            self._intruder_label_s.set_visible(True)
        else:
            self._intruder_trail_s.set_data([], [])
            self._intruder_dot_s.set_data([], [])
            self._intruder_label_s.set_visible(False)

        # ── Interceptor (side view) ───────────────────────────────────────
        if interceptor_pos:
            self._interceptor_alt_trail.append((interceptor_pos[0], interceptor_pos[2]))
            self._interceptor_alt_trail = self._interceptor_alt_trail[-40:]
            self._intercept_trail_s.set_data(
                [p[0] for p in self._interceptor_alt_trail],
                [p[1] for p in self._interceptor_alt_trail]
            )
            self._intercept_dot_s.set_data([interceptor_pos[0]], [interceptor_pos[2]])
            self._intercept_label_s.set_text(f"INTERCEPTOR\n{interceptor_pos[2]:.1f}m")
            self._intercept_label_s.set_position((interceptor_pos[0] + 0.3, interceptor_pos[2] + 0.3))
            self._intercept_label_s.set_visible(True)
        else:
            self._intercept_trail_s.set_data([], [])
            self._intercept_dot_s.set_data([], [])
            self._intercept_label_s.set_visible(False)

        # ── Info text ─────────────────────────────────────────────────────
        lines = []
        if intruder_pos:
            dist  = math.sqrt(sum(v**2 for v in intruder_pos))
            speed = sim_state.get("intruder_speed", 0.0)
            lines.append(f"INTRUDER  rng:{dist:.1f}m  alt:{intruder_pos[2]:.1f}m  {speed:.1f}m/s")
        if interceptor_pos and intruder_pos:
            sep   = math.sqrt(sum((interceptor_pos[i] - intruder_pos[i])**2 for i in range(3)))
            tti   = sim_state.get("tti", float("inf"))
            ispd  = sim_state.get("interceptor_speed", 0.0)
            tti_s = f"{tti:.1f}s" if tti < 999 else "---"
            lines.append(f"INTERCEPT sep:{sep:.1f}m  TTI:{tti_s}  {ispd:.1f}m/s")
        if radar_return.get("detected"):
            conf = sim_state.get("track_confidence", 0.0)
            lines.append(f"RADAR  conf:{conf*100:.0f}%  snr:{radar_return.get('snr', 0):.1f}dB")
        lines += [""] + self._event_log
        self._info_text.set_text("\n".join(lines))

        try:
            self._fig.canvas.draw_idle()
            self._fig.canvas.flush_events()
        except Exception:
            pass

    def close(self):
        try:
            plt.close(self._fig)
        except Exception:
            pass
