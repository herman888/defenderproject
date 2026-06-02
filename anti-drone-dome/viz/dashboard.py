"""
Real-time matplotlib dashboard — military-grade aesthetic.

Design language:
  Background  #080c10  near-black blue-black
  Primary     #00ff88  military green
  Warning     #ffaa00  amber
  Danger      #ff2200  red
  Info        #00ccff  cyan
  Font        monospace throughout

Layout (3 rows):
  Row 0  Radar top-down (X/Y axes + bidirectional cardinals)  |  Altitude (X/Z)
  Row 1  Mission Select: scenario buttons  |  Speed buttons
         Pad Select: [NEAR] [MID] [FAR]    |  (description label)
  Row 2  Controls: [|| PAUSE]  [↺ RESET]  [◼ ABORT]

All view ranges and range rings scale with dome_radius so the dashboard looks
correct whether the dome is 10 m or 200 m.
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
_BG       = (0.031, 0.047, 0.063)
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

_INTRUDER_LABELS = [
    ("shahed136",    "■ SHAHED-136",  "Loitering munition — 51 m/s, composite, low RCS"),
    ("consumer_quad","⬡ CONSUMER",    "DJI Mavic type — 16 m/s, ISR / light payload"),
    ("fpv_attack",   "✕ FPV ATTACK",  "Racing frame — 32 m/s, agile, near-zero RCS"),
]

_PATTERN_LABELS = [
    ("direct",    "→ DIRECT",    "NE bearing, cruise altitude"),
    ("nap_earth", "↘ NAP-EARTH", "Low-altitude sprint, hardest to detect"),
    ("spiral",    "◎ SPIRAL",    "High-alt evasive descent"),
]

_SPEEDS = [
    (0.5,  "0.5×"),
    (1.0,  "1×"),
    (2.0,  "2×"),
    (4.0,  "4×"),
    (8.0,  "8×"),
]

_PADS = [
    ("near", "NEAR  50m"),
    ("mid",  "MID  180m"),
    ("far",  "FAR  380m"),
]


class SimControl:
    def __init__(self):
        self.paused           = False
        self.stopped          = False      # ABORT → ends mission
        self.restart          = False      # RESET → restart same mission
        self.speed            = 1          # legacy (unused by sim physics)
        self.selected_mission = None       # intruder type key — triggers launch
        self.selected_speed   = 1.0
        self.selected_pad     = "mid"
        self.selected_pattern = "direct"   # attack pattern key


class Dashboard:
    def __init__(self, dome_radius: float = 200.0, sim_control: SimControl = None):
        self._dome_radius = dome_radius
        self._view        = dome_radius * 4.0   # radar view half-extent
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

        plt.ion()
        self._fig = plt.figure(figsize=(16, 9))
        self._fig.patch.set_facecolor(_BG)
        self._fig.suptitle(
            "ANTI-DRONE DEFENSE SYSTEM  |  STANDBY  ○",
            color=_GREEN, fontsize=13, fontweight="bold", fontfamily="monospace",
        )

        # 3-row layout: [radar/side] [mission+pad select] [controls]
        gs = self._fig.add_gridspec(
            3, 2,
            height_ratios=[6.8, 2.3, 0.9],
            hspace=0.48, wspace=0.28,
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

    # ── Axis setup ─────────────────────────────────────────────────────
    def _setup_radar_ax(self):
        ax  = self._ax_radar
        v   = self._view
        R   = self._dome_radius
        ax.set_facecolor(_RADAR_BG)
        ax.set_xlim(-v, v)
        ax.set_ylim(-v, v)
        ax.set_aspect("equal")
        ax.set_title("RADAR  —  TOP DOWN", color=_GREEN,
                     fontfamily="monospace", fontsize=10)

        # Axis labels encode coordinate axis AND cardinal direction
        ax.set_xlabel("◄ W (−X)  ·  X position (m)  ·  E (+X) ►",
                      color="#557755", fontsize=7, fontfamily="monospace", labelpad=3)
        ax.set_ylabel("▼ S (−Y)  ·  Y position (m)  ·  N (+Y) ▲",
                      color="#557755", fontsize=7, fontfamily="monospace", labelpad=3)

        # Tick marks at dome-scaled intervals
        step  = R if R >= 50 else 5
        ticks = list(range(int(-v), int(v) + 1, int(step)))
        ax.set_xticks(ticks)
        ax.set_yticks(ticks)
        ax.tick_params(axis="both", colors="#334433", labelsize=6, labelcolor="#557755")
        for spine in ax.spines.values():
            spine.set_color("#223322")

        # Crosshair and dot-grid
        ax.axhline(0, color="#1e2e1e", linewidth=0.6, zorder=0)
        ax.axvline(0, color="#1e2e1e", linewidth=0.6, zorder=0)
        ax.grid(True, color="#0e170e", linewidth=0.3, linestyle=":", alpha=0.9, zorder=0)

        # Range rings: 0.25R, 0.5R, R (dome boundary), 2R, 3R
        ring_specs = [
            (R * 0.25, "#1d2d1d", 0.6),
            (R * 0.5,  "#223322", 0.7),
            (R,        _GREEN,    1.8),   # dome boundary — highlighted
            (R * 1.5,  "#223322", 0.7),
            (R * 2.0,  "#1d2d1d", 0.6),
            (R * 3.0,  "#1a281a", 0.5),
        ]
        for r, col, lw in ring_specs:
            if r > v * 0.98:
                continue
            ax.add_patch(plt.Circle((0, 0), r, color=col, fill=False,
                                    linewidth=lw, linestyle="--", zorder=1))
            lbl_col = _GREEN if r == R else "#2e4a2e"
            suffix  = " ◄ DOME" if r == R else ""
            ax.text(r * 0.707, r * 0.707, f"{r:.0f}m{suffix}",
                    color=lbl_col, fontsize=6, fontfamily="monospace", zorder=2)

        # Bidirectional cardinal compass labels
        _c = dict(fontfamily="monospace", fontsize=8, fontweight="bold",
                  ha="center", va="center", zorder=3)
        ax.text( 0,  v * 0.96, "N ▲",  color="#446644", **_c)
        ax.text( 0, -v * 0.96, "▼ S",  color="#446644", **_c)
        ax.text( v * 0.96, 0,  "E ►",  color="#446644",
                 ha="left",  va="center", **{k: v2 for k, v2 in _c.items()
                                              if k not in ("ha", "va")})
        ax.text(-v * 0.96, 0,  "◄ W",  color="#446644",
                 ha="right", va="center", **{k: v2 for k, v2 in _c.items()
                                              if k not in ("ha", "va")})

    def _setup_side_ax(self):
        ax = self._ax_side
        R  = self._dome_radius
        ax.set_facecolor(_RADAR_BG)
        ax.set_xlim(-self._view, self._view)
        ax.set_ylim(-R * 0.05, R * 1.8)
        ax.set_title("ALTITUDE VIEW  (X / Z)", color=_CYAN,
                     fontfamily="monospace", fontsize=10)
        ax.set_xlabel("◄ W (−X)  ·  X position (m)  ·  E (+X) ►",
                      color="#446655", fontsize=7, fontfamily="monospace", labelpad=3)
        ax.set_ylabel("Altitude Z (m)", color="#446655",
                      fontsize=7, fontfamily="monospace")
        ax.tick_params(colors="#334433", labelsize=6, labelcolor="#557755")
        for spine in ax.spines.values():
            spine.set_color("#223322")
        ax.grid(True, color="#0e170e", linewidth=0.3, linestyle=":", alpha=0.7)
        ax.add_patch(plt.Circle((0, 0), R, color="#223322",
                                fill=False, linewidth=0.7, linestyle="--"))
        ax.axhline(0, color="#334433", linewidth=0.8)
        ax.text(0, -R * 0.03, "GROUND", color="#446644",
                fontsize=7, ha="center", fontfamily="monospace")

    # ── Mission / pad select panel ──────────────────────────────────────
    def _setup_mission_panel(self, gs):
        """
        3 sub-rows inside the mission panel row:
          Sub-row 0: Intruder type  [SHAHED-136][CONSUMER][FPV]  | Speed [0.5x…8x]
          Sub-row 1: Attack pattern [DIRECT][NAP-EARTH][SPIRAL]  | Pad   [NEAR][MID][FAR]
        Clicking an intruder-type button triggers launch (sends selected_mission).
        Pattern, speed, pad are pre-selected state — click to highlight, then
        choose intruder to fire.
        """
        mission_row = gs[1, :]
        mgs = mission_row.subgridspec(2, 10, wspace=0.10, hspace=0.35)

        # ── Sub-row 0 left: Intruder type buttons (cols 0-2) — clicking launches
        _typ_base  = (0.03, 0.12, 0.05)
        _typ_hover = (0.07, 0.23, 0.10)
        self._mission_btns = {}
        for i, (key, label, _) in enumerate(_INTRUDER_LABELS):
            ax  = self._fig.add_subplot(mgs[0, i])
            btn = Button(ax, label, color=_typ_base, hovercolor=_typ_hover)
            btn.label.set_color(_GREEN)
            btn.label.set_fontfamily("monospace")
            btn.label.set_fontsize(8)
            btn.on_clicked(lambda _, k=key: self._on_mission(k))
            self._mission_btns[key] = btn

        # ── Sub-row 0 right: Speed buttons (cols 4-8)
        _spd_base  = (0.05, 0.07, 0.18)
        _spd_sel   = (0.16, 0.20, 0.48)
        _spd_hover = (0.10, 0.12, 0.32)
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

        # ── Sub-row 1 left: Attack pattern buttons (cols 0-2)
        _pat_base  = (0.05, 0.08, 0.18)
        _pat_sel   = (0.14, 0.20, 0.40)
        _pat_hover = (0.10, 0.14, 0.30)
        self._pattern_btns = {}
        for i, (key, lbl, _desc) in enumerate(_PATTERN_LABELS):
            ax  = self._fig.add_subplot(mgs[1, i])
            col = _pat_sel if key == "direct" else _pat_base
            btn = Button(ax, lbl, color=col, hovercolor=_pat_hover)
            btn.label.set_color(_CYAN)
            btn.label.set_fontfamily("monospace")
            btn.label.set_fontsize(7)
            btn.on_clicked(lambda _, k=key: self._on_pattern_select(k))
            self._pattern_btns[key] = btn

        # ── Sub-row 1 right: Pad buttons (cols 4-6)
        _pad_base  = (0.08, 0.06, 0.15)
        _pad_sel   = (0.25, 0.15, 0.40)
        _pad_hover = (0.15, 0.10, 0.28)
        self._pad_btns = {}
        for i, (key, lbl) in enumerate(_PADS):
            ax  = self._fig.add_subplot(mgs[1, 4 + i])
            col = _pad_sel if key == "mid" else _pad_base
            btn = Button(ax, lbl, color=col, hovercolor=_pad_hover)
            btn.label.set_color("#bb88ff")
            btn.label.set_fontfamily("monospace")
            btn.label.set_fontsize(7)
            btn.on_clicked(lambda _, k=key: self._on_pad_select(k))
            self._pad_btns[key] = btn

        # Hint text (cols 7-9 of sub-row 1)
        ax_hint = self._fig.add_subplot(mgs[1, 7:])
        ax_hint.set_facecolor(_BG)
        for spine in ax_hint.spines.values():
            spine.set_visible(False)
        ax_hint.tick_params(left=False, bottom=False, labelleft=False, labelbottom=False)
        ax_hint.text(
            0.03, 0.50,
            "Select pattern + pad + speed,\nthen click intruder to LAUNCH",
            transform=ax_hint.transAxes,
            color="#5a6a5a", fontsize=7, fontfamily="monospace", va="center",
        )

    def _setup_controls(self, gs):
        ctrl_row = gs[2, :]
        cgs = ctrl_row.subgridspec(1, 3, wspace=0.25)

        ax_pause  = self._fig.add_subplot(cgs[0, 0])
        ax_reset  = self._fig.add_subplot(cgs[0, 1])
        ax_abort  = self._fig.add_subplot(cgs[0, 2])

        self._btn_pause = Button(ax_pause, "|| PAUSE",   color=(0.05, 0.14, 0.05), hovercolor=(0.10, 0.26, 0.10))
        self._btn_reset = Button(ax_reset, "↺  RESET",   color=(0.10, 0.08, 0.02), hovercolor=(0.22, 0.16, 0.04))
        self._btn_abort = Button(ax_abort, "◼  ABORT",   color=(0.18, 0.04, 0.04), hovercolor=(0.36, 0.07, 0.07))

        for btn in (self._btn_pause, self._btn_reset, self._btn_abort):
            btn.label.set_color("white")
            btn.label.set_fontfamily("monospace")
            btn.label.set_fontsize(9)

        self._btn_pause.on_clicked(self._on_pause)
        self._btn_reset.on_clicked(self._on_reset)
        self._btn_abort.on_clicked(self._on_abort)

    # ── Button callbacks ───────────────────────────────────────────────
    def _on_pause(self, _):
        if not self._ctrl:
            return
        self._ctrl.paused = not self._ctrl.paused
        self._btn_pause.label.set_text(">  RESUME" if self._ctrl.paused else "|| PAUSE")
        self._btn_pause.ax.set_facecolor(
            (0.32, 0.08, 0.08) if self._ctrl.paused else (0.05, 0.14, 0.05))
        self._fig.canvas.draw_idle()

    def _on_reset(self, _):
        if not self._ctrl:
            return
        self._ctrl.restart = True
        self._btn_reset.ax.set_facecolor((0.40, 0.28, 0.04))
        self._fig.canvas.draw_idle()

    def _on_abort(self, _):
        if not self._ctrl:
            return
        self._ctrl.stopped = True
        self._btn_abort.label.set_text("◼  ABORTED")
        self._btn_abort.ax.set_facecolor((0.48, 0.00, 0.00))
        self._fig.canvas.draw_idle()

    def _on_mission(self, key: str):
        if not self._ctrl:
            return
        self._ctrl.selected_mission = key
        for k, btn in self._mission_btns.items():
            btn.ax.set_facecolor((0.10, 0.38, 0.14) if k == key else (0.03, 0.12, 0.05))
        self._fig.canvas.draw_idle()

    def _on_pattern_select(self, key: str):
        if not self._ctrl:
            return
        self._ctrl.selected_pattern = key
        for k, btn in self._pattern_btns.items():
            btn.ax.set_facecolor((0.14, 0.20, 0.40) if k == key else (0.05, 0.08, 0.18))
        self._fig.canvas.draw_idle()

    def _on_speed_select(self, speed: float):
        if not self._ctrl:
            return
        self._ctrl.selected_speed = speed
        for spd, btn in self._speed_btns.items():
            btn.ax.set_facecolor((0.16, 0.20, 0.48) if spd == speed else (0.05, 0.07, 0.18))
        self._fig.canvas.draw_idle()

    def _on_pad_select(self, key: str):
        if not self._ctrl:
            return
        self._ctrl.selected_pad = key
        for k, btn in self._pad_btns.items():
            btn.ax.set_facecolor((0.25, 0.15, 0.40) if k == key else (0.08, 0.06, 0.15))
        self._fig.canvas.draw_idle()

    # ── Artists ─────────────────────────────────────────────────────────
    def _init_artists(self):
        ax = self._ax_radar
        R  = self._dome_radius

        # Dome boundary circle
        self._dome_circle = mpatches.Circle(
            (0, 0), R, color=_GREEN, fill=False, linewidth=2, zorder=4)
        ax.add_patch(self._dome_circle)

        # Phosphor sweep: 6 fan lines with alpha decay
        self._sweep_fans = []
        for i in range(6):
            alpha = max(0.06, 0.70 - i * 0.12)
            g_val = max(0.18, 0.65 - i * 0.09)
            line, = ax.plot([], [], color=(0, g_val, 0.08),
                            linewidth=max(0.7, 1.8 - i * 0.22), alpha=alpha, zorder=3)
            self._sweep_fans.append(line)

        # Radar station
        self._radar_marker, = ax.plot([], [], "gs", markersize=7, zorder=5)
        self._radar_label   = ax.text(0, 0, "RADAR", color=_GREEN, fontsize=6,
                                       fontfamily="monospace", visible=False, zorder=5)

        # Intruder: red diamond trail + marker
        self._intruder_trail_r, = ax.plot([], [], color="#cc1100", alpha=0.55, linewidth=1.5, zorder=5)
        self._intruder_dot_r,   = ax.plot([], [], "D", color=_RED, markersize=10, zorder=6)
        self._intruder_label_r  = ax.text(0, 0, "INTRUDER", color=_RED,
                                           fontsize=7, fontfamily="monospace",
                                           visible=False, zorder=6)

        # Interceptor: cyan triangle trail + marker
        self._intercept_trail_r, = ax.plot([], [], color="#009999", alpha=0.55, linewidth=1.5, zorder=5)
        self._intercept_dot_r,   = ax.plot([], [], "^", color=_CYAN, markersize=11, zorder=6)
        self._intercept_label_r  = ax.text(0, 0, "INTERCEPTOR", color=_CYAN,
                                            fontsize=7, fontfamily="monospace",
                                            visible=False, zorder=6)

        # Prediction line + cross marker
        self._pred_line, = ax.plot([], [], color=_AMBER, linewidth=1.2,
                                    linestyle="--", alpha=0.85, zorder=5)
        self._pred_dot,  = ax.plot([], [], "x", color=_AMBER, markersize=12, mew=2, zorder=6)

        # Status box (top-right corner)
        self._status_text = ax.text(
            self._view * 0.97, self._view * 0.97, "STATUS: STANDBY",
            color=_GREEN, fontsize=10, ha="right", va="top",
            fontweight="bold", fontfamily="monospace", zorder=7,
            bbox=dict(facecolor=_STATUS_BG["CLEAR"], alpha=0.92,
                      edgecolor=_GREEN, pad=5),
        )

        # Paused overlay
        self._paused_text = ax.text(
            0, 0, "── PAUSED ──",
            color=_AMBER, fontsize=17, ha="center", va="center",
            fontweight="bold", fontfamily="monospace", zorder=9,
            bbox=dict(facecolor="black", alpha=0.75, edgecolor=_AMBER),
            visible=False,
        )

        # Debrief overlay — shown after mission ends
        self._debrief_text = ax.text(
            0, 0, "",
            color=_GREEN, fontsize=11, ha="center", va="center",
            fontweight="bold", fontfamily="monospace", linespacing=1.6,
            zorder=10,
            bbox=dict(facecolor=(0.02, 0.08, 0.03), alpha=0.96,
                      edgecolor=_GREEN, pad=14, boxstyle="round,pad=0.6"),
            visible=False,
        )

        # ── Side view ──────────────────────────────────────────────────
        ax = self._ax_side
        theta = np.linspace(0, math.pi, 80)
        self._dome_arc,  = ax.plot(
            R * np.cos(theta), R * np.sin(theta),
            color=_GREEN, linewidth=2, alpha=0.8)
        self._dome_base, = ax.plot(
            [-R, R], [0, 0], color=_GREEN, linewidth=2, alpha=0.8)

        self._intruder_trail_s,  = ax.plot([], [], color="#cc1100", alpha=0.55, linewidth=1.5)
        self._intruder_dot_s,    = ax.plot([], [], "D", color=_RED, markersize=10)
        self._intruder_label_s   = ax.text(0, 0, "", color=_RED,
                                            fontsize=7, fontfamily="monospace", visible=False)

        self._intercept_trail_s, = ax.plot([], [], color="#009999", alpha=0.55, linewidth=1.5)
        self._intercept_dot_s,   = ax.plot([], [], "^", color=_CYAN, markersize=11)
        self._intercept_label_s  = ax.text(0, 0, "", color=_CYAN,
                                            fontsize=7, fontfamily="monospace", visible=False)

        self._info_text = ax.text(
            0.02, 0.98, "",
            transform=ax.transAxes,
            color="white", fontsize=7, fontfamily="monospace",
            va="top", ha="left",
            bbox=dict(facecolor=_RADAR_BG, alpha=0.90, edgecolor="#334433", pad=5),
        )

    # ── State update ────────────────────────────────────────────────────
    def _clear_trails(self):
        self._intruder_trail.clear()
        self._interceptor_trail.clear()
        self._intruder_alt_trail.clear()
        self._interceptor_alt_trail.clear()
        self._event_log.clear()

    def _reset_buttons(self):
        """Re-arm all control buttons to their default colours."""
        self._ctrl.stopped = False
        self._ctrl.restart = False
        self._btn_abort.label.set_text("◼  ABORT")
        self._btn_abort.ax.set_facecolor((0.18, 0.04, 0.04))
        self._btn_reset.ax.set_facecolor((0.10, 0.08, 0.02))
        self._btn_pause.label.set_text("|| PAUSE")
        self._btn_pause.ax.set_facecolor((0.05, 0.14, 0.05))
        self._ctrl.paused = False
        for btn in self._mission_btns.values():
            btn.ax.set_facecolor((0.03, 0.12, 0.05))
        # Keep pattern/pad/speed highlights as-is (user pre-selections persist)

    def update(self, sim_state: dict):
        msg_type = sim_state.get("type")

        # ── Mission start: clear everything and re-arm buttons ─────────
        if msg_type == "mission_start":
            self._clear_trails()
            self._debrief_text.set_visible(False)
            self._reset_buttons()
            try:
                self._fig.canvas.draw_idle()
            except Exception:
                pass
            return

        # ── Show menu / reset after mission: clear trails, hide debrief ─
        if msg_type in ("reset", "show_menu"):
            self._clear_trails()
            self._debrief_text.set_visible(False)
            for btn in self._mission_btns.values():
                btn.ax.set_facecolor((0.03, 0.12, 0.05))
            try:
                self._fig.canvas.draw_idle()
            except Exception:
                pass
            return

        # ── Debrief: show result overlay ───────────────────────────────
        if msg_type == "debrief":
            self._show_debrief(sim_state)
            return

        # ── Throttle normal updates to ~5 Hz ──────────────────────────
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
            prefix = "+ " if any(w in ev.lower() for w in ("detect", "radar", "launch")) \
                     else "! " if "breach" in ev.lower() else "  "
            self._event_log.append(f"[{ts}] {prefix}{ev}")
        self._event_log = self._event_log[-6:]

        dome_fg = _STATUS_FG.get(status, _GREEN)
        dome_bg = _STATUS_BG.get(status, _STATUS_BG["CLEAR"])

        self._dome_circle.set_color(dome_fg)
        self._dome_arc.set_color(dome_fg)
        self._dome_base.set_color(dome_fg)

        # Phosphor sweep
        self._radar_angle = (self._radar_angle + 15) % 360
        rs = sim_state.get("radar_station", [0, -self._dome_radius, 10])
        sweep_len = self._view * 1.02
        for i, fan in enumerate(self._sweep_fans):
            angle = (self._radar_angle - i * 10) % 360
            rad   = math.radians(angle)
            fan.set_data(
                [rs[0], rs[0] + sweep_len * math.cos(rad)],
                [rs[1], rs[1] + sweep_len * math.sin(rad)],
            )
        self._radar_marker.set_data([rs[0]], [rs[1]])
        self._radar_label.set_position((rs[0] + self._dome_radius * 0.05,
                                        rs[1] + self._dome_radius * 0.05))
        self._radar_label.set_visible(True)

        # Intruder
        if intruder_pos:
            self._intruder_trail.append(intruder_pos[:2])
            self._intruder_trail = self._intruder_trail[-60:]
            self._intruder_trail_r.set_data(
                [p[0] for p in self._intruder_trail],
                [p[1] for p in self._intruder_trail])
            self._intruder_dot_r.set_data([intruder_pos[0]], [intruder_pos[1]])
            off = self._dome_radius * 0.04
            self._intruder_label_r.set_position((intruder_pos[0] + off, intruder_pos[1] + off))
            self._intruder_label_r.set_visible(True)
        else:
            self._intruder_trail_r.set_data([], [])
            self._intruder_dot_r.set_data([], [])
            self._intruder_label_r.set_visible(False)

        # Interceptor
        if interceptor_pos:
            self._interceptor_trail.append(interceptor_pos[:2])
            self._interceptor_trail = self._interceptor_trail[-60:]
            self._intercept_trail_r.set_data(
                [p[0] for p in self._interceptor_trail],
                [p[1] for p in self._interceptor_trail])
            self._intercept_dot_r.set_data([interceptor_pos[0]], [interceptor_pos[1]])
            off = self._dome_radius * 0.04
            self._intercept_label_r.set_position((interceptor_pos[0] + off, interceptor_pos[1] + off))
            self._intercept_label_r.set_visible(True)
        else:
            self._intercept_trail_r.set_data([], [])
            self._intercept_dot_r.set_data([], [])
            self._intercept_label_r.set_visible(False)

        # Prediction line
        if interceptor_pos and predicted_ic:
            self._pred_line.set_data(
                [interceptor_pos[0], predicted_ic[0]],
                [interceptor_pos[1], predicted_ic[1]])
            self._pred_dot.set_data([predicted_ic[0]], [predicted_ic[1]])
        else:
            self._pred_line.set_data([], [])
            self._pred_dot.set_data([], [])

        # Status box
        self._status_text.set_text(f"STATUS: {status}")
        self._status_text.set_color(dome_fg)
        bb = self._status_text.get_bbox_patch()
        bb.set_facecolor(dome_bg)
        bb.set_edgecolor(dome_fg)

        self._paused_text.set_visible(bool(self._ctrl and self._ctrl.paused))

        # Side / altitude view
        if intruder_pos:
            self._intruder_alt_trail.append((intruder_pos[0], intruder_pos[2]))
            self._intruder_alt_trail = self._intruder_alt_trail[-60:]
            self._intruder_trail_s.set_data(
                [p[0] for p in self._intruder_alt_trail],
                [p[1] for p in self._intruder_alt_trail])
            self._intruder_dot_s.set_data([intruder_pos[0]], [intruder_pos[2]])
            self._intruder_label_s.set_text(f"INTR {intruder_pos[2]:.0f}m")
            off = self._dome_radius * 0.03
            self._intruder_label_s.set_position((intruder_pos[0] + off, intruder_pos[2] + off))
            self._intruder_label_s.set_visible(True)
        else:
            self._intruder_trail_s.set_data([], [])
            self._intruder_dot_s.set_data([], [])
            self._intruder_label_s.set_visible(False)

        if interceptor_pos:
            self._interceptor_alt_trail.append((interceptor_pos[0], interceptor_pos[2]))
            self._interceptor_alt_trail = self._interceptor_alt_trail[-60:]
            self._intercept_trail_s.set_data(
                [p[0] for p in self._interceptor_alt_trail],
                [p[1] for p in self._interceptor_alt_trail])
            self._intercept_dot_s.set_data([interceptor_pos[0]], [interceptor_pos[2]])
            self._intercept_label_s.set_text(f"INT {interceptor_pos[2]:.0f}m")
            off = self._dome_radius * 0.03
            self._intercept_label_s.set_position((interceptor_pos[0] + off, interceptor_pos[2] + off))
            self._intercept_label_s.set_visible(True)
        else:
            self._intercept_trail_s.set_data([], [])
            self._intercept_dot_s.set_data([], [])
            self._intercept_label_s.set_visible(False)

        # Info text (altitude panel)
        lines      = []
        sim_time   = sim_state.get("mission_time", 0.0)
        sim_speed  = sim_state.get("sim_speed", 1.0)

        if intruder_pos:
            dist  = math.sqrt(sum(v**2 for v in intruder_pos))
            speed = sim_state.get("intruder_speed", 0.0)
            lines.append(f"INTRUDER  rng:{dist:.0f}m alt:{intruder_pos[2]:.0f}m  {speed:.0f}m/s")

        if interceptor_pos and intruder_pos:
            sep  = math.sqrt(sum((interceptor_pos[i] - intruder_pos[i])**2 for i in range(3)))
            tti  = sim_state.get("tti", float("inf"))
            ispd = sim_state.get("interceptor_speed", 0.0)
            tti_s = f"{tti:.1f}s" if tti < 999 else "---"
            lines.append(f"INTERCEPT sep:{sep:.0f}m  TTI:{tti_s}  {ispd:.0f}m/s")

        if radar_return.get("detected"):
            conf = sim_state.get("track_confidence", 0.0)
            lines.append(f"RADAR  conf:{conf*100:.0f}%  snr:{radar_return.get('snr',0):.1f}dB")

        if intruder_pos:
            threat = max(0.0, 1.0 - math.sqrt(sum(v**2 for v in intruder_pos))
                         / (2 * self._dome_radius))
            filled = int(threat * 20)
            bar    = "█" * filled + "░" * (20 - filled)
            lines.append(f"THREAT [{bar}] {threat*100:.0f}%")

        MAX_TIME = 240.0
        t_fill = int(min(1.0, sim_time / MAX_TIME) * 20)
        t_bar  = "█" * t_fill + "░" * (20 - t_fill)
        lines.append(f"TIME  [{t_bar}] {sim_time:.0f}s  {sim_speed:.2g}×")

        if self._event_log:
            lines.append("")
            lines += self._event_log

        self._info_text.set_text("\n".join(lines))

        try:
            self._fig.canvas.draw_idle()
            self._fig.canvas.flush_events()
        except Exception:
            pass

    def _show_debrief(self, state: dict):
        result   = state.get("result", "---")
        sim_time = state.get("sim_time", 0.0)
        closest  = state.get("closest_approach", float("inf"))

        _result_col = {
            "INTERCEPTED": _GREEN,
            "FAILURE":     _RED,
            "TIMEOUT":     _AMBER,
            "ABORTED":     "#888888",
        }
        _result_icon = {
            "INTERCEPTED": "★  INTERCEPTED  ★",
            "FAILURE":     "✗  BREACH — FAILURE  ✗",
            "TIMEOUT":     "⏱  TIME EXPIRED  ⏱",
            "ABORTED":     "■  MISSION ABORTED  ■",
        }
        col  = _result_col.get(result, "white")
        icon = _result_icon.get(result, f"■  {result}  ■")

        lines = [icon, ""]
        lines.append(f"Duration:      {sim_time:.0f} s")
        if closest < 9999:
            lines.append(f"Closest appr:  {closest:.1f} m")
        lines += [
            "",
            "─" * 30,
            "Click a scenario to continue",
            "■ STANDARD   ► FAST LOW   ◎ SPIRAL",
        ]

        self._debrief_text.set_text("\n".join(lines))
        self._debrief_text.set_color(col)
        bb = self._debrief_text.get_bbox_patch()
        bb.set_edgecolor(col)
        self._debrief_text.set_visible(True)

        # Update title to reflect result
        try:
            self._fig.suptitle(
                f"ANTI-DRONE DEFENSE SYSTEM  |  {result}",
                color=col, fontsize=13, fontweight="bold", fontfamily="monospace",
            )
        except Exception:
            pass

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
