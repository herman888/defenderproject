"""
Real-time matplotlib dashboard — military-grade aesthetic.

Design language:
  Background  #080c10  (near-black blue-black)
  Primary     #00ff88  (military green)
  Warning     #ffaa00  (amber)
  Danger      #ff2200  (red)
  Info        #00ccff  (cyan)
  Font        monospace throughout

Layout (3 rows):
  Row 0  Radar top-down (X/Y)  |  Altitude side view (X/Z)
  Row 1  Mission Select: [STANDARD] [FAST LOW] [SPIRAL]  |  Speed: [0.25x]…[8x]
  Row 2  Controls: [|| PAUSE]  [[] STOP]
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

_SCENARIOS = {
    "standard": "■ STANDARD",
    "fast_low": "► FAST LOW",
    "spiral":   "◎ SPIRAL",
}

_SPEEDS = [
    (0.25, "0.25×"),
    (0.5,  "0.5×"),
    (1.0,  "1×"),
    (2.0,  "2×"),
    (4.0,  "4×"),
    (8.0,  "8×"),
]


class SimControl:
    def __init__(self):
        self.paused           = False
        self.stopped          = False
        self.speed            = 1          # legacy (unused by sim — kept for compat)
        self.selected_mission = None       # set when user clicks a scenario button
        self.selected_speed   = 1.0        # initial sim speed sent with mission


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
        self._blink_state  = False
        self._last_blink   = 0.0
        self._active_speed_btn = None   # Button currently highlighted as selected speed

        plt.ion()
        self._fig = plt.figure(figsize=(16, 9))
        self._fig.patch.set_facecolor(_BG)
        self._fig.suptitle(
            "ANTI-DRONE DEFENSE SYSTEM  |  ACTIVE  ●",
            color=_GREEN, fontsize=13, fontweight="bold", fontfamily="monospace",
        )

        gs = self._fig.add_gridspec(
            3, 2,
            height_ratios=[7, 1.8, 0.9],
            hspace=0.50, wspace=0.28,
            left=0.06, right=0.97, top=0.92, bottom=0.04,
        )
        self._ax_radar = self._fig.add_subplot(gs[0, 0])
        self._ax_side  = self._fig.add_subplot(gs[0, 1])

        self._setup_radar_ax()
        self._setup_side_ax()
        self._setup_mission_panel(gs)
        self._setup_controls(gs)
        self._init_artists()
        plt.pause(0.01)

    # ──────────────────────────────────────────────────────────────────
    def _setup_radar_ax(self):
        ax = self._ax_radar
        ax.set_facecolor(_RADAR_BG)
        ax.set_xlim(-22, 22)
        ax.set_ylim(-22, 22)
        ax.set_aspect("equal")
        ax.set_title(
            "RADAR  —  TOP DOWN",
            color=_GREEN, fontfamily="monospace", fontsize=10,
        )

        # Axis labels encode both coordinate and cardinal direction
        ax.set_xlabel(
            "◄ W (−X)  ·  X position (m)  ·  E (+X) ►",
            color="#557755", fontsize=7, fontfamily="monospace", labelpad=3,
        )
        ax.set_ylabel(
            "▼ S (−Y)  ·  Y (m)  ·  N (+Y) ▲",
            color="#557755", fontsize=7, fontfamily="monospace", labelpad=3,
        )

        # Tick marks at regular intervals
        ticks = [-20, -10, 0, 10, 20]
        ax.set_xticks(ticks)
        ax.set_yticks(ticks)
        ax.tick_params(axis="both", colors="#334433", labelsize=6, labelcolor="#557755")
        for spine in ax.spines.values():
            spine.set_color("#223322")

        # Crosshair axes through origin
        ax.axhline(0, color="#1e2e1e", linewidth=0.6, zorder=0)
        ax.axvline(0, color="#1e2e1e", linewidth=0.6, zorder=0)

        # Subtle dot-grid
        ax.grid(True, color="#111a11", linewidth=0.3, linestyle=":", alpha=0.9, zorder=0)

        # Range rings with distance labels
        for r, col, lw in [
            (5,  "#223322", 0.7),
            (10, _GREEN,    1.5),   # dome boundary
            (15, "#223322", 0.7),
            (20, "#223322", 0.7),
        ]:
            ax.add_patch(plt.Circle(
                (0, 0), r, color=col, fill=False, linewidth=lw, linestyle="--", zorder=1,
            ))
            label_col = _GREEN if r == 10 else "#3a5a3a"
            ax.text(
                r * 0.707, r * 0.707, f"{r}m",
                color=label_col, fontsize=6, fontfamily="monospace", zorder=2,
            )

        # Bidirectional cardinal compass labels (inside plot at ±21)
        _card = dict(fontfamily="monospace", fontsize=8, fontweight="bold",
                     ha="center", va="center", zorder=3)
        ax.text( 0,   21.0, "N ▲",  color="#446644", **_card)
        ax.text( 0,  -21.0, "▼ S",  color="#446644", **_card)
        ax.text( 21.0, 0,   "E ►",  color="#446644", ha="left",  va="center",
                 fontfamily="monospace", fontsize=8, fontweight="bold", zorder=3)
        ax.text(-21.0, 0,   "◄ W",  color="#446644", ha="right", va="center",
                 fontfamily="monospace", fontsize=8, fontweight="bold", zorder=3)

    def _setup_side_ax(self):
        ax = self._ax_side
        ax.set_facecolor(_RADAR_BG)
        ax.set_xlim(-22, 22)
        ax.set_ylim(-1, 18)
        ax.set_title(
            "ALTITUDE VIEW  (X / Z)",
            color=_CYAN, fontfamily="monospace", fontsize=10,
        )
        ax.set_xlabel(
            "◄ W (−X)  ·  X position (m)  ·  E (+X) ►",
            color="#446655", fontsize=7, fontfamily="monospace", labelpad=3,
        )
        ax.set_ylabel("Altitude Z (m)", color="#446655", fontsize=7, fontfamily="monospace")
        ax.tick_params(colors="#334433", labelsize=6, labelcolor="#557755")
        for spine in ax.spines.values():
            spine.set_color("#223322")
        ax.grid(True, color="#111a11", linewidth=0.3, linestyle=":", alpha=0.7)
        for r in [5, 10]:
            ax.add_patch(plt.Circle(
                (0, 0), r, color="#223322", fill=False, linewidth=0.7, linestyle="--"
            ))
        ax.axhline(0, color="#334433", linewidth=0.8)
        ax.text(0, -0.5, "GROUND", color="#446644",
                fontsize=7, ha="center", fontfamily="monospace")

    # ──────────────────────────────────────────────────────────────────
    def _setup_mission_panel(self, gs):
        """Mission select row: scenario buttons (left) + speed buttons (right)."""
        mission_row = gs[1, :]
        # 10 columns: 3 scenarios | 1 gap | 6 speeds
        mgs = mission_row.subgridspec(1, 10, wspace=0.10)

        _scn_cols  = {"standard": 0, "fast_low": 1, "spiral": 2}
        _scn_color = (0.04, 0.14, 0.06)
        _scn_hover = (0.08, 0.26, 0.10)
        self._mission_btns = {}
        for key, col in _scn_cols.items():
            ax = self._fig.add_subplot(mgs[0, col])
            label = _SCENARIOS[key]
            btn = Button(ax, label, color=_scn_color, hovercolor=_scn_hover)
            btn.label.set_color(_GREEN)
            btn.label.set_fontfamily("monospace")
            btn.label.set_fontsize(8)
            btn.on_clicked(lambda _, k=key: self._on_mission(k))
            self._mission_btns[key] = btn

        # Speed buttons (columns 4–9; col 3 is gap)
        _spd_base  = (0.06, 0.08, 0.20)
        _spd_sel   = (0.18, 0.22, 0.50)
        _spd_hover = (0.12, 0.14, 0.36)
        self._speed_btns = {}
        for i, (spd, lbl) in enumerate(_SPEEDS):
            ax  = self._fig.add_subplot(mgs[0, 4 + i])
            col = _spd_sel if spd == 1.0 else _spd_base
            btn = Button(ax, lbl, color=col, hovercolor=_spd_hover)
            btn.label.set_color("white")
            btn.label.set_fontfamily("monospace")
            btn.label.set_fontsize(8)
            btn.on_clicked(lambda _, s=spd: self._on_speed_select(s))
            self._speed_btns[spd] = btn
            if spd == 1.0:
                self._active_speed_btn = btn   # 1× selected by default

        # Row label overlays (text axes behind buttons)
        ax_lbl_l = self._fig.add_axes([0.06, 0.0, 0.01, 0.01])   # invisible
        ax_lbl_l.set_visible(False)

    def _setup_controls(self, gs):
        """Bottom control row: Pause + Stop."""
        ctrl_row = gs[2, :]
        cgs = ctrl_row.subgridspec(1, 2, wspace=0.30)

        ax_pause = self._fig.add_subplot(cgs[0, 0])
        ax_stop  = self._fig.add_subplot(cgs[0, 1])

        self._btn_pause = Button(ax_pause, "|| PAUSE", color=(0.06, 0.16, 0.06), hovercolor=(0.12, 0.30, 0.12))
        self._btn_stop  = Button(ax_stop,  "[] STOP",  color=(0.20, 0.05, 0.05), hovercolor=(0.40, 0.08, 0.08))

        for btn in (self._btn_pause, self._btn_stop):
            btn.label.set_color("white")
            btn.label.set_fontfamily("monospace")
            btn.label.set_fontsize(9)

        self._btn_pause.on_clicked(self._on_pause)
        self._btn_stop.on_clicked(self._on_stop)

    # ──────────────────────────────────────────────────────────────────
    def _on_pause(self, _):
        if not self._ctrl:
            return
        self._ctrl.paused = not self._ctrl.paused
        self._btn_pause.label.set_text(">  RESUME" if self._ctrl.paused else "|| PAUSE")
        self._btn_pause.ax.set_facecolor((0.35, 0.08, 0.08) if self._ctrl.paused else (0.06, 0.16, 0.06))
        self._fig.canvas.draw_idle()

    def _on_stop(self, _):
        if not self._ctrl:
            return
        self._ctrl.stopped = True
        self._btn_stop.label.set_text("[] STOPPED")
        self._btn_stop.ax.set_facecolor((0.50, 0.00, 0.00))
        self._fig.canvas.draw_idle()

    def _on_mission(self, key: str):
        if not self._ctrl:
            return
        self._ctrl.selected_mission = key
        # Brief visual flash on the clicked button
        btn = self._mission_btns[key]
        btn.ax.set_facecolor((0.10, 0.40, 0.15))
        self._fig.canvas.draw_idle()

    def _on_speed_select(self, speed: float):
        if not self._ctrl:
            return
        self._ctrl.selected_speed = speed
        # Update button highlights
        for spd, btn in self._speed_btns.items():
            btn.ax.set_facecolor((0.18, 0.22, 0.50) if spd == speed else (0.06, 0.08, 0.20))
        self._fig.canvas.draw_idle()

    # ──────────────────────────────────────────────────────────────────
    def _init_artists(self):
        ax = self._ax_radar

        # Dome circle
        self._dome_circle = mpatches.Circle(
            (0, 0), self._dome_radius,
            color=_GREEN, fill=False, linewidth=2, zorder=4,
        )
        ax.add_patch(self._dome_circle)

        # Phosphor sweep: 6 fan lines with alpha decay
        self._sweep_fans = []
        for i in range(6):
            alpha = max(0.08, 0.75 - i * 0.13)
            g_val = max(0.20, 0.70 - i * 0.09)
            line, = ax.plot([], [], color=(0, g_val, 0.10),
                            linewidth=max(0.8, 2.0 - i * 0.25), alpha=alpha, zorder=3)
            self._sweep_fans.append(line)

        # Radar station marker + label
        self._radar_marker, = ax.plot([], [], "gs", markersize=8, zorder=5)
        self._radar_label   = ax.text(
            0, 0, "RADAR", color=_GREEN, fontsize=6,
            fontfamily="monospace", visible=False, zorder=5,
        )

        # Intruder: red diamond trail + dot
        self._intruder_trail_r, = ax.plot([], [], color="#cc1100", alpha=0.55, linewidth=1.5, zorder=5)
        self._intruder_dot_r,   = ax.plot([], [], "D", color=_RED, markersize=11, zorder=6)
        self._intruder_label_r  = ax.text(
            0, 0, "INTRUDER", color=_RED,
            fontsize=7, fontfamily="monospace", visible=False, zorder=6,
        )

        # Interceptor: cyan triangle trail + marker
        self._intercept_trail_r, = ax.plot([], [], color="#009999", alpha=0.55, linewidth=1.5, zorder=5)
        self._intercept_dot_r,   = ax.plot([], [], "^", color=_CYAN, markersize=12, zorder=6)
        self._intercept_label_r  = ax.text(
            0, 0, "INTERCEPTOR", color=_CYAN,
            fontsize=7, fontfamily="monospace", visible=False, zorder=6,
        )

        # Prediction line + X marker
        self._pred_line, = ax.plot(
            [], [], color=_AMBER, linewidth=1.2, linestyle="--", alpha=0.85, zorder=5,
        )
        self._pred_dot, = ax.plot([], [], "x", color=_AMBER, markersize=12, mew=2, zorder=6)

        # Status box (top-right)
        self._status_text = ax.text(
            22, 22, "STATUS: CLEAR",
            color=_GREEN, fontsize=11, ha="right", va="top",
            fontweight="bold", fontfamily="monospace", zorder=7,
            bbox=dict(
                facecolor=_STATUS_BG["CLEAR"], alpha=0.92,
                edgecolor=_GREEN, pad=5,
            ),
        )

        # Paused overlay
        self._paused_text = ax.text(
            0, 0, "── PAUSED ──",
            color=_AMBER, fontsize=17, ha="center", va="center",
            fontweight="bold", fontfamily="monospace", zorder=8,
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

    # ──────────────────────────────────────────────────────────────────
    def update(self, sim_state: dict):
        # Handle mission reset / menu signal — clear trails only
        if sim_state.get("type") in ("reset", "show_menu"):
            self._intruder_trail.clear()
            self._interceptor_trail.clear()
            self._intruder_alt_trail.clear()
            self._interceptor_alt_trail.clear()
            self._event_log.clear()
            # Re-arm mission buttons (undo green flash)
            for btn in self._mission_btns.values():
                btn.ax.set_facecolor((0.04, 0.14, 0.06))
            try:
                self._fig.canvas.draw_idle()
            except Exception:
                pass
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
            self._intruder_label_r.set_position((intruder_pos[0] + 0.6, intruder_pos[1] + 0.6))
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
            self._intercept_label_r.set_position((interceptor_pos[0] + 0.6, interceptor_pos[1] + 0.6))
            self._intercept_label_r.set_visible(True)
        else:
            self._intercept_trail_r.set_data([], [])
            self._intercept_dot_r.set_data([], [])
            self._intercept_label_r.set_visible(False)

        # ── Prediction line (interceptor → current target) ─────────────
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
            self._intruder_label_s.set_position((intruder_pos[0] + 0.3, intruder_pos[2] + 0.3))
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
            self._intercept_label_s.set_position((interceptor_pos[0] + 0.3, interceptor_pos[2] + 0.3))
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
            sep  = math.sqrt(sum((interceptor_pos[i] - intruder_pos[i])**2 for i in range(3)))
            tti  = sim_state.get("tti", float("inf"))
            ispd = sim_state.get("interceptor_speed", 0.0)
            tti_s = f"{tti:.1f}s" if tti < 999 else "---"
            lines.append(f"INTERCEPT sep:{sep:.1f}m  TTI:{tti_s}  {ispd:.1f}m/s")

        if radar_return.get("detected"):
            conf = sim_state.get("track_confidence", 0.0)
            lines.append(f"RADAR  conf:{conf*100:.0f}%  snr:{radar_return.get('snr',0):.1f}dB")

        # Threat level bar
        if intruder_pos:
            threat = max(0.0, 1.0 - math.sqrt(sum(v**2 for v in intruder_pos)) / (2 * self._dome_radius))
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
