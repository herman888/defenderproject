"""
Real-time matplotlib dashboard — military-grade aesthetic.

Design language:
  Background  #080c10  (near-black blue-black)
  Primary     #00ff88  (military green)
  Warning     #ffaa00  (amber)
  Danger      #ff2200  (red)
  Info        #00ccff  (cyan)
  Font        monospace throughout

New in V2:
  - Phosphor sweep: 6-line green fan with alpha decay
  - Intruder marker: red diamond; interceptor: cyan upward triangle
  - Status box: coloured background matching dome state
  - Threat-level and mission-time bars (ASCII) in info panel
  - Blinking header indicator
"""

import math
import time
import numpy as np
import matplotlib
matplotlib.use("TkAgg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.widgets import Button

# ── Colour palette ─────────────────────────────────────────────────────
_BG       = (0.031, 0.047, 0.063)   # #080c10
_RADAR_BG = (0.020, 0.031, 0.051)
_GREEN    = "#00ff88"
_AMBER    = "#ffaa00"
_RED      = "#ff2200"
_CYAN     = "#00ccff"
_DIM      = "#445544"

_STATUS_BG = {
    "CLEAR"      : (0.00, 0.14, 0.06),
    "TRACKING"   : (0.15, 0.11, 0.00),
    "BREACH"     : (0.20, 0.07, 0.00),
    "INTERCEPTED": (0.18, 0.00, 0.00),
}
_STATUS_FG = {
    "CLEAR"      : _GREEN,
    "TRACKING"   : _AMBER,
    "BREACH"     : "#ff6600",
    "INTERCEPTED": _RED,
}


class SimControl:
    def __init__(self):
        self.paused  = False
        self.stopped = False
        self.speed   = 1   # 0=half, 1=normal, 2=double


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
        self._blink_state  = False
        self._last_blink   = 0.0

        plt.ion()
        self._fig = plt.figure(figsize=(16, 9))
        self._fig.patch.set_facecolor(_BG)
        self._fig.suptitle(
            "ANTI-DRONE DEFENSE SYSTEM  |  ACTIVE  ●",
            color=_GREEN, fontsize=13, fontweight="bold", fontfamily="monospace",
        )

        gs = self._fig.add_gridspec(
            2, 2,
            height_ratios=[8, 1],
            hspace=0.40, wspace=0.28,
            left=0.05, right=0.97, top=0.92, bottom=0.06,
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
        ax.set_facecolor(_RADAR_BG)
        ax.set_xlim(-22, 22)
        ax.set_ylim(-22, 22)
        ax.set_aspect("equal")
        ax.set_title(
            "RADAR  —  TOP DOWN  (X / Y)",
            color=_GREEN, fontfamily="monospace", fontsize=10,
        )
        ax.tick_params(colors="#334433", labelsize=7)
        for spine in ax.spines.values():
            spine.set_color("#223322")

        # Range rings with distance labels
        for r, col, lw in [
            (5,  "#223322", 0.7),
            (10, _GREEN,    1.5),  # dome boundary
            (15, "#223322", 0.7),
            (20, "#223322", 0.7),
        ]:
            ax.add_patch(plt.Circle(
                (0, 0), r, color=col, fill=False, linewidth=lw, linestyle="--"
            ))
            label_col = _GREEN if r == 10 else "#3a5a3a"
            ax.text(
                r * 0.707, r * 0.707, f"{r}m",
                color=label_col, fontsize=7, fontfamily="monospace",
            )

        # Compass labels
        for lbl, pos in [
            ("N", (0, 21)), ("S", (0, -21)),
            ("E", (21, 0)), ("W", (-21, 0)),
        ]:
            ax.text(
                pos[0], pos[1], lbl, color="#446644",
                fontsize=8, ha="center", va="center", fontfamily="monospace",
            )

    def _setup_side_ax(self):
        ax = self._ax_side
        ax.set_facecolor(_RADAR_BG)
        ax.set_xlim(-22, 22)
        ax.set_ylim(-1, 18)
        ax.set_title(
            "ALTITUDE VIEW  (X / Z)",
            color=_CYAN, fontfamily="monospace", fontsize=10,
        )
        ax.set_xlabel("X position (m)", color="#446644", fontsize=8)
        ax.set_ylabel("Altitude (m)",   color="#446644", fontsize=8)
        ax.tick_params(colors="#334433", labelsize=7)
        for spine in ax.spines.values():
            spine.set_color("#223322")
        for r in [5, 10]:
            ax.add_patch(plt.Circle(
                (0, 0), r, color="#223322", fill=False, linewidth=0.7, linestyle="--"
            ))
        ax.axhline(0, color="#334433", linewidth=0.8)
        ax.text(0, -0.5, "GROUND", color="#446644",
                fontsize=7, ha="center", fontfamily="monospace")

    def _init_artists(self):
        ax = self._ax_radar

        # Dome circle
        self._dome_circle = mpatches.Circle(
            (0, 0), self._dome_radius,
            color=_GREEN, fill=False, linewidth=2,
        )
        ax.add_patch(self._dome_circle)

        # Phosphor sweep: 6 fan lines with decreasing alpha
        self._sweep_fans = []
        for i in range(6):
            alpha  = max(0.08, 0.75 - i * 0.13)
            g_val  = max(0.20, 0.70 - i * 0.09)
            line,  = ax.plot([], [], color=(0, g_val, 0.10),
                             linewidth=max(0.8, 2.0 - i*0.25), alpha=alpha)
            self._sweep_fans.append(line)

        # Radar station marker + label
        self._radar_marker, = ax.plot([], [], "gs", markersize=8)
        self._radar_label   = ax.text(
            0, 0, "RADAR", color=_GREEN, fontsize=6,
            fontfamily="monospace", visible=False,
        )

        # Intruder: red diamond trail + dot
        self._intruder_trail_r, = ax.plot([], [], color="#cc1100", alpha=0.55, linewidth=1.5)
        self._intruder_dot_r,   = ax.plot([], [], "D", color=_RED, markersize=11)
        self._intruder_label_r  = ax.text(
            0, 0, "INTRUDER", color=_RED,
            fontsize=7, fontfamily="monospace", visible=False,
        )

        # Interceptor: cyan triangle trail + marker
        self._intercept_trail_r, = ax.plot([], [], color="#009999", alpha=0.55, linewidth=1.5)
        self._intercept_dot_r,   = ax.plot([], [], "^", color=_CYAN, markersize=12)
        self._intercept_label_r  = ax.text(
            0, 0, "INTERCEPTOR", color=_CYAN,
            fontsize=7, fontfamily="monospace", visible=False,
        )

        # Prediction line + X marker
        self._pred_line, = ax.plot(
            [], [], color=_AMBER, linewidth=1.2, linestyle="--", alpha=0.85
        )
        self._pred_dot, = ax.plot([], [], "x", color=_AMBER, markersize=12, mew=2)

        # Status box (top-right)
        self._status_text = ax.text(
            22, 22, "STATUS: CLEAR",
            color=_GREEN, fontsize=11, ha="right", va="top",
            fontweight="bold", fontfamily="monospace",
            bbox=dict(
                facecolor=_STATUS_BG["CLEAR"], alpha=0.92,
                edgecolor=_GREEN, pad=5,
            ),
        )

        # Paused overlay
        self._paused_text = ax.text(
            0, 0, "── PAUSED ──",
            color=_AMBER, fontsize=17, ha="center", va="center",
            fontweight="bold", fontfamily="monospace",
            bbox=dict(facecolor="black", alpha=0.75, edgecolor=_AMBER),
            visible=False,
        )

        # ── Side view ──────────────────────────────────────────────────
        ax = self._ax_side
        theta = np.linspace(0, math.pi, 60)
        self._dome_arc,  = ax.plot(
            self._dome_radius * np.cos(theta),
            self._dome_radius * np.sin(theta),
            color=_GREEN, linewidth=2, alpha=0.8,
        )
        self._dome_base, = ax.plot(
            [-self._dome_radius, self._dome_radius], [0, 0],
            color=_GREEN, linewidth=2, alpha=0.8,
        )

        self._intruder_trail_s,  = ax.plot([], [], color="#cc1100", alpha=0.55, linewidth=1.5)
        self._intruder_dot_s,    = ax.plot([], [], "D", color=_RED, markersize=11)
        self._intruder_label_s   = ax.text(0, 0, "", color=_RED,
                                            fontsize=7, fontfamily="monospace", visible=False)

        self._intercept_trail_s, = ax.plot([], [], color="#009999", alpha=0.55, linewidth=1.5)
        self._intercept_dot_s,   = ax.plot([], [], "^", color=_CYAN, markersize=12)
        self._intercept_label_s  = ax.text(0, 0, "", color=_CYAN,
                                            fontsize=7, fontfamily="monospace", visible=False)

        # Info text (military monospace)
        self._info_text = ax.text(
            0.02, 0.98, "",
            transform=ax.transAxes,
            color="white", fontsize=7, fontfamily="monospace",
            va="top", ha="left",
            bbox=dict(facecolor=_RADAR_BG, alpha=0.90, edgecolor="#334433", pad=5),
        )

    def _setup_buttons(self, gs):
        btn_row = gs[1, :]
        btn_gs  = btn_row.subgridspec(1, 3, wspace=0.40)

        ax_pause = self._fig.add_subplot(btn_gs[0, 0])
        ax_stop  = self._fig.add_subplot(btn_gs[0, 1])
        ax_speed = self._fig.add_subplot(btn_gs[0, 2])

        self._btn_pause = Button(ax_pause, "|| PAUSE",    color=(0.06,0.16,0.06), hovercolor=(0.12,0.30,0.12))
        self._btn_stop  = Button(ax_stop,  "[] STOP",     color=(0.20,0.05,0.05), hovercolor=(0.40,0.08,0.08))
        self._btn_speed = Button(ax_speed, ">> 1x SPEED", color=(0.06,0.08,0.20), hovercolor=(0.12,0.14,0.36))

        for btn in (self._btn_pause, self._btn_stop, self._btn_speed):
            btn.label.set_color("white")
            btn.label.set_fontfamily("monospace")
            btn.label.set_fontsize(9)

        self._btn_pause.on_clicked(self._on_pause)
        self._btn_stop.on_clicked(self._on_stop)
        self._btn_speed.on_clicked(self._on_speed)

    # ------------------------------------------------------------------
    def _on_pause(self, _):
        if not self._ctrl: return
        self._ctrl.paused = not self._ctrl.paused
        self._btn_pause.label.set_text(">  RESUME" if self._ctrl.paused else "|| PAUSE")
        self._btn_pause.ax.set_facecolor((0.35,0.08,0.08) if self._ctrl.paused else (0.06,0.16,0.06))
        self._fig.canvas.draw_idle()

    def _on_stop(self, _):
        if not self._ctrl: return
        self._ctrl.stopped = True
        self._btn_stop.label.set_text("[] STOPPED")
        self._btn_stop.ax.set_facecolor((0.50,0.00,0.00))
        self._fig.canvas.draw_idle()

    def _on_speed(self, _):
        if not self._ctrl: return
        self._speed_idx = (self._speed_idx + 1) % len(self._speed_labels)
        self._ctrl.speed = self._speed_values[self._speed_idx]
        self._btn_speed.label.set_text(f">> {self._speed_labels[self._speed_idx]} SPEED")
        self._fig.canvas.draw_idle()

    # ------------------------------------------------------------------
    def update(self, sim_state: dict):
        # Handle mission reset signal
        if sim_state.get("type") == "reset":
            self._intruder_trail.clear()
            self._interceptor_trail.clear()
            self._intruder_alt_trail.clear()
            self._interceptor_alt_trail.clear()
            self._event_log.clear()
            return

        now = time.time()
        if now - self._last_draw < 0.20:
            return
        self._last_draw = now

        # Blink header indicator every ~1 s
        if now - self._last_blink >= 1.0:
            self._blink_state = not self._blink_state
            self._last_blink  = now
            dot = "●" if self._blink_state else "○"
            try:
                self._fig.suptitle(
                    f"ANTI-DRONE DEFENSE SYSTEM  |  ACTIVE  {dot}",
                    color=_GREEN, fontsize=13, fontweight="bold",
                    fontfamily="monospace",
                )
            except Exception:
                pass

        status          = sim_state.get("dome_status", "CLEAR")
        intruder_pos    = sim_state.get("intruder_pos")
        interceptor_pos = sim_state.get("interceptor_pos")
        radar_return    = sim_state.get("radar_return", {})
        predicted_ic    = sim_state.get("predicted_intercept")
        events          = sim_state.get("events", [])

        for ev in events:
            ts = time.strftime("%H:%M:%S")
            if "detect" in ev.lower() or "radar" in ev.lower() or "launch" in ev.lower():
                self._event_log.append(f"[{ts}] + {ev}")
            elif "breach" in ev.lower():
                self._event_log.append(f"[{ts}] ! {ev}")
            else:
                self._event_log.append(f"[{ts}]   {ev}")
        self._event_log = self._event_log[-6:]

        dome_fg = _STATUS_FG.get(status, _GREEN)
        dome_bg = _STATUS_BG.get(status, _STATUS_BG["CLEAR"])

        # ── Dome colour ────────────────────────────────────────────────
        self._dome_circle.set_color(dome_fg)
        self._dome_arc.set_color(dome_fg)
        self._dome_base.set_color(dome_fg)

        # ── Phosphor sweep ────────────────────────────────────────────
        self._radar_angle = (self._radar_angle + 18) % 360
        rs = sim_state.get("radar_station", [0, -self._dome_radius, 3])
        for i, fan in enumerate(self._sweep_fans):
            angle = (self._radar_angle - i * 12) % 360
            rad   = math.radians(angle)
            fan.set_data(
                [rs[0], rs[0] + 22 * math.cos(rad)],
                [rs[1], rs[1] + 22 * math.sin(rad)],
            )

        self._radar_marker.set_data([rs[0]], [rs[1]])
        self._radar_label.set_position((rs[0] + 0.5, rs[1] + 0.5))
        self._radar_label.set_visible(True)

        # ── Intruder (radar view) ──────────────────────────────────────
        if intruder_pos:
            self._intruder_trail.append(intruder_pos[:2])
            self._intruder_trail = self._intruder_trail[-50:]
            self._intruder_trail_r.set_data(
                [p[0] for p in self._intruder_trail],
                [p[1] for p in self._intruder_trail],
            )
            self._intruder_dot_r.set_data([intruder_pos[0]], [intruder_pos[1]])
            self._intruder_label_r.set_position((intruder_pos[0]+0.6, intruder_pos[1]+0.6))
            self._intruder_label_r.set_visible(True)
        else:
            self._intruder_trail_r.set_data([], [])
            self._intruder_dot_r.set_data([], [])
            self._intruder_label_r.set_visible(False)

        # ── Interceptor (radar view) ───────────────────────────────────
        if interceptor_pos:
            self._interceptor_trail.append(interceptor_pos[:2])
            self._interceptor_trail = self._interceptor_trail[-50:]
            self._intercept_trail_r.set_data(
                [p[0] for p in self._interceptor_trail],
                [p[1] for p in self._interceptor_trail],
            )
            self._intercept_dot_r.set_data([interceptor_pos[0]], [interceptor_pos[1]])
            self._intercept_label_r.set_position((interceptor_pos[0]+0.6, interceptor_pos[1]+0.6))
            self._intercept_label_r.set_visible(True)
        else:
            self._intercept_trail_r.set_data([], [])
            self._intercept_dot_r.set_data([], [])
            self._intercept_label_r.set_visible(False)

        # ── Prediction line ────────────────────────────────────────────
        if interceptor_pos and predicted_ic:
            self._pred_line.set_data(
                [interceptor_pos[0], predicted_ic[0]],
                [interceptor_pos[1], predicted_ic[1]],
            )
            self._pred_dot.set_data([predicted_ic[0]], [predicted_ic[1]])
        else:
            self._pred_line.set_data([], [])
            self._pred_dot.set_data([], [])

        # ── Status box ────────────────────────────────────────────────
        self._status_text.set_text(f"STATUS: {status}")
        self._status_text.set_color(dome_fg)
        bb = self._status_text.get_bbox_patch()
        bb.set_facecolor(dome_bg)
        bb.set_edgecolor(dome_fg)

        # ── Paused overlay ────────────────────────────────────────────
        self._paused_text.set_visible(bool(self._ctrl and self._ctrl.paused))

        # ── Side view ─────────────────────────────────────────────────
        if intruder_pos:
            self._intruder_alt_trail.append((intruder_pos[0], intruder_pos[2]))
            self._intruder_alt_trail = self._intruder_alt_trail[-50:]
            self._intruder_trail_s.set_data(
                [p[0] for p in self._intruder_alt_trail],
                [p[1] for p in self._intruder_alt_trail],
            )
            self._intruder_dot_s.set_data([intruder_pos[0]], [intruder_pos[2]])
            self._intruder_label_s.set_text(f"INTR\n{intruder_pos[2]:.1f}m")
            self._intruder_label_s.set_position((intruder_pos[0]+0.3, intruder_pos[2]+0.3))
            self._intruder_label_s.set_visible(True)
        else:
            self._intruder_trail_s.set_data([], [])
            self._intruder_dot_s.set_data([], [])
            self._intruder_label_s.set_visible(False)

        if interceptor_pos:
            self._interceptor_alt_trail.append((interceptor_pos[0], interceptor_pos[2]))
            self._interceptor_alt_trail = self._interceptor_alt_trail[-50:]
            self._intercept_trail_s.set_data(
                [p[0] for p in self._interceptor_alt_trail],
                [p[1] for p in self._interceptor_alt_trail],
            )
            self._intercept_dot_s.set_data([interceptor_pos[0]], [interceptor_pos[2]])
            self._intercept_label_s.set_text(f"INT\n{interceptor_pos[2]:.1f}m")
            self._intercept_label_s.set_position((interceptor_pos[0]+0.3, interceptor_pos[2]+0.3))
            self._intercept_label_s.set_visible(True)
        else:
            self._intercept_trail_s.set_data([], [])
            self._intercept_dot_s.set_data([], [])
            self._intercept_label_s.set_visible(False)

        # ── Info text ─────────────────────────────────────────────────
        lines = []
        sim_time  = sim_state.get("mission_time", 0.0)
        sim_speed = sim_state.get("sim_speed", 1.0)

        if intruder_pos:
            dist  = math.sqrt(sum(v**2 for v in intruder_pos))
            speed = sim_state.get("intruder_speed", 0.0)
            lines.append(f"INTRUDER  rng:{dist:.1f}m alt:{intruder_pos[2]:.1f}m  {speed:.1f}m/s")

        if interceptor_pos and intruder_pos:
            sep  = math.sqrt(sum((interceptor_pos[i]-intruder_pos[i])**2 for i in range(3)))
            tti  = sim_state.get("tti", float("inf"))
            ispd = sim_state.get("interceptor_speed", 0.0)
            tti_s = f"{tti:.1f}s" if tti < 999 else "---"
            lines.append(f"INTERCEPT sep:{sep:.1f}m  TTI:{tti_s}  {ispd:.1f}m/s")

        if radar_return.get("detected"):
            conf = sim_state.get("track_confidence", 0.0)
            lines.append(f"RADAR  conf:{conf*100:.0f}%  snr:{radar_return.get('snr',0):.1f}dB")

        # Threat level bar
        if intruder_pos:
            threat = max(0.0, 1.0 - math.sqrt(sum(v**2 for v in intruder_pos)) / (2*self._dome_radius))
            filled = int(threat * 20)
            bar    = "█" * filled + "░" * (20 - filled)
            lines.append(f"THREAT [{bar}] {threat*100:.0f}%")

        # Mission time bar
        MAX_TIME = 120.0
        t_frac = min(1.0, sim_time / MAX_TIME)
        t_fill = int(t_frac * 20)
        t_bar  = "█" * t_fill + "░" * (20 - t_fill)
        spd_str = f"{sim_speed:.2g}x"
        lines.append(f"TIME  [{t_bar}] {sim_time:.0f}s  {spd_str}")

        if self._event_log:
            lines.append("")
            lines += self._event_log

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
