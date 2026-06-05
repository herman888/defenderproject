"""
Real-time matplotlib dashboard — production C-UAS aesthetic.
DroneShield DroneSentry-C2 / military C2 interface style.

IPC logic, queue handling, button callbacks, and data flow are unchanged.
Only visual appearance and layout changed.
"""

import math
import sys
import time
import numpy as np
import matplotlib


def _matplotlib_backend():
    if sys.platform == "darwin":
        try:
            import tkinter  # noqa: F401
        except ImportError:
            return "MacOSX"
    return "TkAgg"


matplotlib.use(_matplotlib_backend())
matplotlib.rcParams.update({
    "toolbar":         "None",
    "font.family":     "monospace",
    "font.size":       9,
    "text.color":      "#c8d8c8",
    "axes.labelcolor": "#c8d8c8",
    "xtick.color":     "#4a6a4a",
    "ytick.color":     "#4a6a4a",
})

import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.widgets import Button

# ── Color palette ──────────────────────────────────────────────────────────────
C = {
    "bg":      "#04080c",
    "panel":   "#080f14",
    "border":  "#1a2e1a",
    "primary": "#00e676",
    "dim":     "#1e3a1e",
    "amber":   "#ffab00",
    "red":     "#ff1744",
    "blue":    "#2979ff",
    "cyan":    "#00e5ff",
    "text":    "#b2d8b2",
    "textdim": "#4a6a4a",
    "white":   "#e8f0e8",
}

_STATUS_COLOR = {
    "CLEAR":       C["primary"],
    "TRACKING":    C["amber"],
    "BREACH":      C["red"],
    "INTERCEPTED": C["cyan"],
}

_INTRUDER_LABELS = [
    ("shahed136",    "■ SHAHED-136",  "Loitering munition — 51 m/s, composite, low RCS"),
    ("consumer_quad","# CONSUMER",    "DJI Mavic type — 16 m/s, ISR / light payload"),
    ("fpv_attack",   "✕ FPV ATTACK",  "Racing frame — 32 m/s, agile, near-zero RCS"),
]
_PATTERN_LABELS = [
    ("direct",    "→ DIRECT",    "NE bearing, cruise altitude"),
    ("nap_earth", "↘ NAP-EARTH", "Low-altitude sprint, hardest to detect"),
    ("spiral",    "◎ SPIRAL",    "High-alt evasive descent"),
]
_SPEEDS = [(0.5, "0.5×"), (1.0, "1×"), (2.0, "2×"), (4.0, "4×"), (8.0, "8×")]
_PADS   = [("near", "NEAR 50m"), ("mid", "MID 180m"), ("far", "FAR 380m")]


# ─────────────────────────────────────────────────────────────────────────────
class SimControl:
    def __init__(self):
        self.paused           = False
        self.stopped          = False
        self.restart          = False
        self.speed            = 1
        self.pending_intruder = "shahed136"
        self.selected_mission = None
        self.selected_speed   = 1.0
        self.selected_pad     = "mid"
        self.selected_pattern = "direct"
        self.camera_zoom_pending = None


# ─────────────────────────────────────────────────────────────────────────────
def _dark_ax(ax, border=True):
    """Apply dark theme: panel bg, no ticks, optional border via spines."""
    ax.set_facecolor(C["panel"])
    ax.tick_params(left=False, bottom=False, labelleft=False, labelbottom=False)
    if border:
        for sp in ax.spines.values():
            sp.set_visible(True)
            sp.set_color(C["border"])
            sp.set_linewidth(0.8)
    else:
        for sp in ax.spines.values():
            sp.set_visible(False)


# ─────────────────────────────────────────────────────────────────────────────
class Dashboard:
    def __init__(self, dome_radius: float = 200.0, sim_control: SimControl = None):
        self._dome_radius = dome_radius
        self._view        = dome_radius * 4.0
        self._ctrl        = sim_control
        self._event_log   = []
        self._intruder_trail        = []
        self._interceptor_trail     = []
        self._intruder_alt_trail    = []
        self._interceptor_alt_trail = []
        self._radar_angle = 0.0
        self._last_draw   = 0.0
        self._blink_state = False
        self._last_blink  = 0.0

        plt.ion()
        self._fig = plt.figure(figsize=(14, 8.8), dpi=96)
        self._fig.patch.set_facecolor(C["bg"])

        try:
            mgr = self._fig.canvas.manager
            mgr.set_window_title("ANTI-DRONE DEFENSE SYSTEM  —  C-UAS COMMAND")
            mgr.window.wm_geometry("980x660+940+0")
        except Exception:
            pass

        # Remove any leftover toolmanager tools
        try:
            tm = self._fig.canvas.manager.toolmanager
            for t in ("zoom", "pan", "subplots", "save", "help"):
                try:
                    tm.remove_tool(t)
                except Exception:
                    pass
        except Exception:
            pass

        # ── 4-row layout: header | viz | event-log | controls ─────────────────
        gs = self._fig.add_gridspec(
            4, 1,
            height_ratios=[0.30, 5.6, 0.42, 3.2],
            hspace=0.0,
            left=0.01, right=0.99, top=0.99, bottom=0.01,
        )

        # Row 0 — header bar
        self._ax_header = self._fig.add_subplot(gs[0])
        self._build_header()

        # Row 1 — radar (left 55%) | altitude + telemetry (right 45%)
        viz_gs = gs[1].subgridspec(1, 2, wspace=0.04, width_ratios=[11, 9])
        self._ax_radar = self._fig.add_subplot(viz_gs[0])
        right_gs = viz_gs[1].subgridspec(2, 1, hspace=0.05, height_ratios=[5, 4])
        self._ax_side  = self._fig.add_subplot(right_gs[0])
        self._ax_telem = self._fig.add_subplot(right_gs[1])

        # Row 2 — event log strip
        self._ax_log = self._fig.add_subplot(gs[2])
        self._build_event_log_ax()

        # Row 3 — mission select (top) + controls (bottom)
        ctrl_gs = gs[3].subgridspec(2, 1, height_ratios=[1.3, 0.9], hspace=0.22)

        self._setup_radar_ax()
        self._setup_side_ax()
        self._setup_telem_ax()
        self._setup_mission_panel(ctrl_gs[0])
        self._setup_controls(ctrl_gs[1])
        self._init_artists()
        plt.pause(0.01)

    # ── Header bar ────────────────────────────────────────────────────────────
    def _build_header(self):
        ax = self._ax_header
        _dark_ax(ax, border=False)
        ax.set_facecolor(C["panel"])
        # Top accent line and bottom separator
        ax.plot([0, 1], [1, 1], color=C["primary"], linewidth=2.5,
                transform=ax.transAxes, clip_on=False)
        ax.plot([0, 1], [0, 0], color=C["border"], linewidth=0.8,
                transform=ax.transAxes, clip_on=False)

        ax.text(0.008, 0.72, "◈  ANTI-DRONE DEFENSE SYSTEM",
                color=C["white"], fontsize=11, fontweight="bold",
                va="top", transform=ax.transAxes)
        ax.text(0.008, 0.12, "C-UAS COMMAND & CONTROL  v1.0",
                color=C["textdim"], fontsize=7,
                va="bottom", transform=ax.transAxes)

        self._hdr_status = ax.text(
            0.50, 0.52, "●  STANDBY",
            color=C["primary"], fontsize=10, fontweight="bold",
            va="center", ha="center", transform=ax.transAxes)

        self._hdr_time = ax.text(
            0.985, 0.72, "T+  00:00",
            color=C["text"], fontsize=10, va="top", ha="right",
            transform=ax.transAxes)
        self._hdr_speed = ax.text(
            0.985, 0.12, "SIM  1.0×",
            color=C["textdim"], fontsize=7, va="bottom", ha="right",
            transform=ax.transAxes)

    # ── Event log strip ───────────────────────────────────────────────────────
    def _build_event_log_ax(self):
        ax = self._ax_log
        _dark_ax(ax, border=False)
        ax.plot([0, 1], [1, 1], color=C["border"], linewidth=0.7,
                transform=ax.transAxes, clip_on=False)
        ax.plot([0, 1], [0, 0], color=C["border"], linewidth=0.7,
                transform=ax.transAxes, clip_on=False)
        ax.text(0.004, 0.88, "EVENT LOG",
                color=C["textdim"], fontsize=6, fontweight="bold",
                va="top", transform=ax.transAxes)
        self._log_text = ax.text(
            0.012, 0.38, "─  No events",
            color=C["textdim"], fontsize=8,
            va="center", transform=ax.transAxes)

    # ── Radar panel ───────────────────────────────────────────────────────────
    def _setup_radar_ax(self):
        ax = self._ax_radar
        v  = self._view
        R  = self._dome_radius

        ax.set_facecolor(C["panel"])
        ax.set_xlim(-v, v)
        ax.set_ylim(-v, v)
        ax.set_aspect("equal")
        ax.tick_params(labelbottom=False, labelleft=False, bottom=False, left=False)
        for sp in ax.spines.values():
            sp.set_visible(True)
            sp.set_color(C["border"])
            sp.set_linewidth(0.8)

        ax.set_title("RADAR  —  TOP DOWN", color=C["primary"],
                     fontsize=9, pad=4, loc="left", fontweight="bold")

        # 4 crosshair lines only
        ax.axhline(0, color=C["dim"], linewidth=0.6, zorder=0)
        ax.axvline(0, color=C["dim"], linewidth=0.6, zorder=0)
        for frac in (0.5, -0.5):
            ax.axhline(v * frac, color=C["dim"], linewidth=0.3, linestyle=":", zorder=0)
            ax.axvline(v * frac, color=C["dim"], linewidth=0.3, linestyle=":", zorder=0)

        # Cardinal labels inside panel
        _kw = dict(fontsize=8, fontweight="bold", ha="center", va="center", zorder=3)
        ax.text( 0,  v * 0.94, "N▲", color=C["textdim"], **_kw)
        ax.text( 0, -v * 0.94, "▼S", color=C["textdim"], **_kw)
        ax.text( v * 0.94, 0,  "E►", color=C["textdim"], **_kw)
        ax.text(-v * 0.94, 0,  "◄W", color=C["textdim"], **_kw)

        # Range rings — labels at 3 o'clock
        ring_specs = [
            (R * 0.25, C["dim"],     0.5, None),
            (R * 0.5,  C["dim"],     0.6, f"{R*0.5:.0f}m"),
            (R,        C["primary"], 2.5, f"{R:.0f}m  DOME"),
            (R * 2.0,  C["dim"],     0.5, f"{R*2:.0f}m"),
            (R * 3.0,  C["dim"],     0.4, None),
        ]
        for r, col, lw, label in ring_specs:
            if r > v * 0.98:
                continue
            ls = "-" if r == R else "--"
            ax.add_patch(plt.Circle((0, 0), r, color=col, fill=False,
                                    linewidth=lw, linestyle=ls, zorder=1))
            if r == R:
                ax.add_patch(plt.Circle((0, 0), r, color=C["primary"],
                                        alpha=0.03, linewidth=0, zorder=0))
            if label:
                ax.text(r + v * 0.012, 0, label,
                        color=C["textdim"], fontsize=7, va="center", zorder=2)

    # ── Altitude panel ────────────────────────────────────────────────────────
    def _setup_side_ax(self):
        ax = self._ax_side
        R  = self._dome_radius

        ax.set_facecolor(C["panel"])
        ax.set_xlim(-self._view, self._view)
        ax.set_ylim(-R * 0.05, R * 1.8)
        for sp in ax.spines.values():
            sp.set_visible(True)
            sp.set_color(C["border"])
            sp.set_linewidth(0.8)

        ax.set_title("ALTITUDE  —  X / Z", color=C["cyan"],
                     fontsize=9, pad=4, loc="left", fontweight="bold")

        ax.tick_params(left=False, bottom=False, labelbottom=False)
        ax.yaxis.tick_right()
        ax.yaxis.set_tick_params(labelright=True, labelleft=False,
                                  labelsize=6, labelcolor=C["textdim"])
        ax.set_yticks([0, R * 0.5, R, R * 1.5])
        ax.set_yticklabels([f"{int(z)}m" for z in [0, R * 0.5, R, R * 1.5]])

        ax.axhline(0, color=C["dim"], linewidth=0.8, zorder=0)
        ax.grid(True, color=C["dim"], linewidth=0.3, linestyle=":", alpha=0.4, zorder=0)
        ax.text(-self._view * 0.94, -R * 0.03, "GND",
                color=C["textdim"], fontsize=6, va="center")

    # ── Telemetry panel ───────────────────────────────────────────────────────
    def _setup_telem_ax(self):
        ax = self._ax_telem
        ax.set_facecolor(C["panel"])
        ax.set_xlim(0, 1)
        ax.set_ylim(0, 1)
        for sp in ax.spines.values():
            sp.set_visible(True)
            sp.set_color(C["border"])
            sp.set_linewidth(0.8)
        ax.tick_params(left=False, bottom=False, labelleft=False, labelbottom=False)

        _bb_i = dict(boxstyle="round,pad=0.3", facecolor="#06100e",
                     edgecolor=C["border"], alpha=0.95)
        _bb_c = dict(boxstyle="round,pad=0.3", facecolor="#04080f",
                     edgecolor=C["border"], alpha=0.95)
        _bb_r = dict(boxstyle="round,pad=0.3", facecolor="#040f08",
                     edgecolor=C["border"], alpha=0.95)

        self._telem_intruder = ax.text(
            0.025, 0.97,
            "─ INTRUDER ──────────────────────────────\n"
            "  RNG  ---        ALT  ---        SPD  ---\n"
            "  BRG  ---        TYPE  ─────────────────",
            color=C["red"], fontsize=7.5, va="top",
            transform=ax.transAxes, bbox=_bb_i)

        self._telem_intercept = ax.text(
            0.025, 0.62,
            "─ INTERCEPTOR ───────────────────────────\n"
            "  SEP  ---        TTI  ---     SPD  ---\n"
            "  STATUS  STANDBY",
            color=C["blue"], fontsize=7.5, va="top",
            transform=ax.transAxes, bbox=_bb_c)

        self._telem_radar = ax.text(
            0.025, 0.29,
            "─ RADAR ─────────────────────────────────\n"
            "  CONF  ---%       SNR  ---dB\n"
            "  TRACK  SEARCHING    LOCK  PENDING",
            color=C["primary"], fontsize=7.5, va="top",
            transform=ax.transAxes, bbox=_bb_r)

        # Threat bar
        ax.text(0.025, 0.065, "THREAT",
                color=C["textdim"], fontsize=6.5, va="center",
                transform=ax.transAxes)
        self._threat_pct = ax.text(
            0.975, 0.065, "0%",
            color=C["textdim"], fontsize=7, va="center", ha="right",
            transform=ax.transAxes)
        # Background track
        ax.add_patch(mpatches.Rectangle(
            (0.175, 0.022), 0.79, 0.068,
            facecolor=C["dim"], edgecolor="none", transform=ax.transAxes))
        # Fill (updated each frame)
        self._threat_bar = mpatches.Rectangle(
            (0.175, 0.022), 0.001, 0.068,
            facecolor=C["primary"], edgecolor="none", transform=ax.transAxes)
        ax.add_patch(self._threat_bar)

    # ── Mission select panel ──────────────────────────────────────────────────
    def _setup_mission_panel(self, mission_spec):
        mgs = mission_spec.subgridspec(2, 11, wspace=0.10, hspace=0.32)

        _I_BASE  = "#0e1a0e";  _I_SEL = "#1a4020";  _I_HOV = "#163a1a"
        _S_BASE  = "#0a0f22";  _S_SEL = "#0f1a48";  _S_HOV = "#0d162e"
        _P_BASE  = "#110e05";  _P_SEL = "#201a06";  _P_HOV = "#1a1408"
        _D_BASE  = "#0e0a1a";  _D_SEL = "#1a0e2e";  _D_HOV = "#160c24"

        self._mission_btns = {}
        for i, (key, label, _) in enumerate(_INTRUDER_LABELS):
            ax  = self._fig.add_subplot(mgs[0, i])
            col = _I_SEL if key == "shahed136" else _I_BASE
            btn = Button(ax, label, color=col, hovercolor=_I_HOV)
            btn.label.set_color(C["primary"]); btn.label.set_fontfamily("monospace")
            btn.label.set_fontsize(8)
            for sp in ax.spines.values(): sp.set_color("#2a6a2a"); sp.set_linewidth(1.4)
            btn.on_clicked(lambda _, k=key: self._on_mission(k))
            self._mission_btns[key] = btn

        self._speed_btns = {}
        for i, (spd, lbl) in enumerate(_SPEEDS):
            ax  = self._fig.add_subplot(mgs[0, 4 + i])
            col = _S_SEL if spd == 1.0 else _S_BASE
            btn = Button(ax, lbl, color=col, hovercolor=_S_HOV)
            btn.label.set_color(C["cyan"]); btn.label.set_fontfamily("monospace")
            btn.label.set_fontsize(8)
            for sp in ax.spines.values(): sp.set_color("#1a4a8a"); sp.set_linewidth(1.4)
            btn.on_clicked(lambda _, s=spd: self._on_speed_select(s))
            self._speed_btns[spd] = btn

        self._pattern_btns = {}
        for i, (key, lbl, _) in enumerate(_PATTERN_LABELS):
            ax  = self._fig.add_subplot(mgs[1, i])
            col = _P_SEL if key == "direct" else _P_BASE
            btn = Button(ax, lbl, color=col, hovercolor=_P_HOV)
            btn.label.set_color(C["amber"]); btn.label.set_fontfamily("monospace")
            btn.label.set_fontsize(7)
            for sp in ax.spines.values(): sp.set_color("#4a4010"); sp.set_linewidth(1.4)
            btn.on_clicked(lambda _, k=key: self._on_pattern_select(k))
            self._pattern_btns[key] = btn

        self._pad_btns = {}
        for i, (key, lbl) in enumerate(_PADS):
            ax  = self._fig.add_subplot(mgs[1, 4 + i])
            col = _D_SEL if key == "mid" else _D_BASE
            btn = Button(ax, lbl, color=col, hovercolor=_D_HOV)
            btn.label.set_color("#cc99ff"); btn.label.set_fontfamily("monospace")
            btn.label.set_fontsize(7)
            for sp in ax.spines.values(): sp.set_color("#4a1a7a"); sp.set_linewidth(1.4)
            btn.on_clicked(lambda _, k=key: self._on_pad_select(k))
            self._pad_btns[key] = btn

        # Hint text col 8-10
        ax_hint = self._fig.add_subplot(mgs[1, 8:])
        _dark_ax(ax_hint, border=False)
        ax_hint.text(0.05, 0.5,
                     "Select intruder · pattern · pad · speed\n"
                     "then  ▶ START  to launch the 3-D sim",
                     transform=ax_hint.transAxes,
                     color=C["textdim"], fontsize=7, va="center")

    # ── Controls row ──────────────────────────────────────────────────────────
    def _setup_controls(self, controls_spec):
        cgs = controls_spec.subgridspec(1, 7, wspace=0.12)

        ax_pause = self._fig.add_subplot(cgs[0, 0])
        ax_reset = self._fig.add_subplot(cgs[0, 1])
        ax_start = self._fig.add_subplot(cgs[0, 2])
        ax_abort = self._fig.add_subplot(cgs[0, 3])
        ax_sep   = self._fig.add_subplot(cgs[0, 4])
        ax_plus  = self._fig.add_subplot(cgs[0, 5])
        ax_minus = self._fig.add_subplot(cgs[0, 6])

        # Separator label
        _dark_ax(ax_sep, border=False)
        ax_sep.text(0.5, 0.65, "3-D CAM", color=C["textdim"],
                    fontsize=6, ha="center", va="center",
                    transform=ax_sep.transAxes)

        self._btn_pause = Button(ax_pause, "|| PAUSE",  color="#0a1808", hovercolor="#112010")
        self._btn_reset = Button(ax_reset, "↺  RESET",  color="#141008", hovercolor="#201808")
        self._btn_start = Button(ax_start, "▶  START",  color="#0d2010", hovercolor="#163015")
        self._btn_abort = Button(ax_abort, "◼  ABORT",  color="#1e0508", hovercolor="#2e0810")
        self._btn_zoom_in  = Button(ax_plus,  "+",      color="#061212", hovercolor="#0c2020")
        self._btn_zoom_out = Button(ax_minus, "−",      color="#061212", hovercolor="#0c2020")

        _styles = {
            self._btn_pause:    (C["primary"], 9,  C["primary"]),
            self._btn_reset:    (C["amber"],   9,  C["amber"]),
            self._btn_start:    (C["white"],   9,  C["primary"]),
            self._btn_abort:    (C["red"],     9,  C["red"]),
            self._btn_zoom_in:  (C["cyan"],    12, C["cyan"]),
            self._btn_zoom_out: (C["cyan"],    12, C["cyan"]),
        }
        for btn, (col, sz, border) in _styles.items():
            btn.label.set_color(col)
            btn.label.set_fontfamily("monospace")
            btn.label.set_fontsize(sz)
            for sp in btn.ax.spines.values():
                sp.set_color(border); sp.set_linewidth(1.5)

        self._btn_start.label.set_fontweight("bold")

        self._btn_pause.on_clicked(self._on_pause)
        self._btn_reset.on_clicked(self._on_reset)
        self._btn_start.on_clicked(self._on_start)
        self._btn_abort.on_clicked(self._on_abort)
        self._btn_zoom_in.on_clicked(self._on_zoom_in)
        self._btn_zoom_out.on_clicked(self._on_zoom_out)

    # ── Button callbacks (data logic unchanged) ────────────────────────────────
    def _on_pause(self, _):
        if not self._ctrl:
            return
        self._ctrl.paused = not self._ctrl.paused
        self._btn_pause.label.set_text(">  RESUME" if self._ctrl.paused else "|| PAUSE")
        self._btn_pause.ax.set_facecolor("#2a0610" if self._ctrl.paused else "#0a1808")
        self._fig.canvas.draw_idle()

    def _on_reset(self, _):
        if not self._ctrl:
            return
        self._ctrl.restart = True
        self._btn_reset.ax.set_facecolor("#241a06")
        self._fig.canvas.draw_idle()

    def _on_abort(self, _):
        if not self._ctrl:
            return
        self._ctrl.stopped = True
        self._btn_abort.label.set_text("◼  ABORTED")
        self._btn_abort.ax.set_facecolor("#3a0810")
        self._fig.canvas.draw_idle()

    def _on_zoom_in(self, _):
        if self._ctrl:
            self._ctrl.camera_zoom_pending = "in"
        self._fig.canvas.draw_idle()

    def _on_zoom_out(self, _):
        if self._ctrl:
            self._ctrl.camera_zoom_pending = "out"
        self._fig.canvas.draw_idle()

    def _on_mission(self, key: str):
        if not self._ctrl:
            return
        self._ctrl.pending_intruder = key
        for k, btn in self._mission_btns.items():
            c = "#1a4020" if k == key else "#0e1a0e"
            btn.color = c; btn.ax.set_facecolor(c)
        self._fig.canvas.draw_idle()

    def _on_start(self, _):
        if not self._ctrl:
            return
        self._ctrl.selected_mission = self._ctrl.pending_intruder
        self._btn_start.ax.set_facecolor("#163520")
        self._fig.canvas.draw_idle()

    def _on_pattern_select(self, key: str):
        if not self._ctrl:
            return
        self._ctrl.selected_pattern = key
        for k, btn in self._pattern_btns.items():
            c = "#201a06" if k == key else "#110e05"
            btn.color = c; btn.ax.set_facecolor(c)
        self._fig.canvas.draw_idle()

    def _on_speed_select(self, speed: float):
        if not self._ctrl:
            return
        self._ctrl.selected_speed = speed
        for spd, btn in self._speed_btns.items():
            c = "#0f1a48" if spd == speed else "#0a0f22"
            btn.color = c; btn.ax.set_facecolor(c)
        self._fig.canvas.draw_idle()

    def _on_pad_select(self, key: str):
        if not self._ctrl:
            return
        self._ctrl.selected_pad = key
        for k, btn in self._pad_btns.items():
            c = "#1a0e2e" if k == key else "#0e0a1a"
            btn.color = c; btn.ax.set_facecolor(c)
        self._fig.canvas.draw_idle()

    # ── Initial artists ───────────────────────────────────────────────────────
    def _init_artists(self):
        ax = self._ax_radar
        R  = self._dome_radius

        self._dome_circle = mpatches.Circle(
            (0, 0), R, color=C["primary"], fill=False, linewidth=2.5, zorder=4)
        ax.add_patch(self._dome_circle)

        # Phosphor sweep — 12 fan lines with exponential alpha
        self._sweep_fans = []
        for i in range(12):
            alpha = max(0.04, 0.82 - i * 0.07)
            g_val = max(0.12, 0.90 - i * 0.07)
            lw    = max(0.5, 2.0 - i * 0.12)
            line, = ax.plot([], [], color=(0.04, g_val, 0.10),
                            linewidth=lw, alpha=alpha, zorder=3)
            self._sweep_fans.append(line)

        self._radar_marker, = ax.plot([], [], "s", color=C["primary"],
                                       markersize=6, zorder=5)
        self._radar_label   = ax.text(0, 0, "RADAR", color=C["primary"],
                                       fontsize=6, visible=False, zorder=5)

        # Intruder
        self._intruder_trail_r, = ax.plot([], [], color="#cc1100",
                                           alpha=0.5, linewidth=1.5, zorder=5)
        self._intruder_dot_r,   = ax.plot([], [], "D", color=C["red"],
                                           markersize=10, zorder=6)
        self._intruder_label_r  = ax.text(0, 0, "INTRUDER", color=C["red"],
                                           fontsize=7, visible=False, zorder=6)

        # Interceptor
        self._intercept_trail_r, = ax.plot([], [], color="#1a50cc",
                                            alpha=0.5, linewidth=1.5, zorder=5)
        self._intercept_dot_r,   = ax.plot([], [], "^", color=C["blue"],
                                            markersize=11, zorder=6)
        self._intercept_label_r  = ax.text(0, 0, "INTERCEPTOR", color=C["blue"],
                                            fontsize=7, visible=False, zorder=6)

        # Prediction line + cross
        self._pred_line, = ax.plot([], [], color=C["amber"], linewidth=1.5,
                                    linestyle="--", alpha=0.85, zorder=5)
        self._pred_dot,  = ax.plot([], [], "x", color=C["amber"],
                                    markersize=12, mew=2, zorder=6)

        # Status badge — top-left of radar panel
        self._status_badge = ax.text(
            -self._view * 0.96, self._view * 0.93, "●  STATUS: STANDBY",
            color=C["primary"], fontsize=8, fontweight="bold",
            ha="left", va="top", zorder=7,
            bbox=dict(facecolor="#010f05", alpha=0.95,
                      edgecolor=C["border"], pad=4,
                      boxstyle="round,pad=0.4"))

        self._paused_text = ax.text(
            0, 0, "── PAUSED ──",
            color=C["amber"], fontsize=17, ha="center", va="center",
            fontweight="bold", zorder=9,
            bbox=dict(facecolor=C["bg"], alpha=0.85, edgecolor=C["amber"]),
            visible=False)

        self._debrief_text = ax.text(
            0, 0, "",
            color=C["primary"], fontsize=11, ha="center", va="center",
            fontweight="bold", linespacing=1.6, zorder=10,
            bbox=dict(facecolor="#020a04", alpha=0.96,
                      edgecolor=C["primary"], pad=14,
                      boxstyle="round,pad=0.6"),
            visible=False)

        # ── Altitude view artists ─────────────────────────────────────────────
        ax2   = self._ax_side
        theta = np.linspace(0, math.pi, 80)
        self._dome_arc,  = ax2.plot(R * np.cos(theta), R * np.sin(theta),
                                     color=C["amber"], linewidth=1.8, alpha=0.8)
        self._dome_base, = ax2.plot([-R, R], [0, 0],
                                     color=C["amber"], linewidth=1.8, alpha=0.8)

        self._intruder_trail_s,  = ax2.plot([], [], color="#cc1100", alpha=0.5, linewidth=1.5)
        self._intruder_dot_s,    = ax2.plot([], [], "D", color=C["red"], markersize=10)
        self._intruder_label_s   = ax2.text(0, 0, "", color=C["red"],
                                             fontsize=7, visible=False)
        self._intercept_trail_s, = ax2.plot([], [], color="#1a50cc", alpha=0.5, linewidth=1.5)
        self._intercept_dot_s,   = ax2.plot([], [], "^", color=C["blue"], markersize=11)
        self._intercept_label_s  = ax2.text(0, 0, "", color=C["blue"],
                                             fontsize=7, visible=False)

    # ── State helpers ─────────────────────────────────────────────────────────
    def _clear_trails(self):
        self._intruder_trail.clear()
        self._interceptor_trail.clear()
        self._intruder_alt_trail.clear()
        self._interceptor_alt_trail.clear()
        self._event_log.clear()

    def _reset_buttons(self):
        self._ctrl.stopped = False
        self._ctrl.restart = False
        self._btn_abort.label.set_text("◼  ABORT")
        self._btn_abort.ax.set_facecolor("#1e0508")
        self._btn_reset.ax.set_facecolor("#141008")
        self._btn_start.ax.set_facecolor("#0d2010")
        self._btn_pause.label.set_text("|| PAUSE")
        self._btn_pause.ax.set_facecolor("#0a1808")
        self._ctrl.paused = False
        for btn in self._mission_btns.values():
            btn.ax.set_facecolor("#0e1a0e")

    # ── Main update ───────────────────────────────────────────────────────────
    def update(self, sim_state: dict):
        msg_type = sim_state.get("type")

        if msg_type == "mission_start":
            self._clear_trails()
            self._debrief_text.set_visible(False)
            self._reset_buttons()
            try:
                self._fig.canvas.draw_idle()
            except Exception:
                pass
            return

        if msg_type in ("reset", "show_menu"):
            self._clear_trails()
            self._debrief_text.set_visible(False)
            for btn in self._mission_btns.values():
                btn.ax.set_facecolor("#0e1a0e")
            try:
                self._fig.canvas.draw_idle()
            except Exception:
                pass
            return

        if msg_type == "debrief":
            self._show_debrief(sim_state)
            return

        now = time.time()
        if now - self._last_draw < 0.20:
            return
        self._last_draw = now

        if now - self._last_blink >= 1.0:
            self._blink_state = not self._blink_state
            self._last_blink  = now

        status          = sim_state.get("dome_status", "CLEAR")
        intruder_pos    = sim_state.get("intruder_pos")
        interceptor_pos = sim_state.get("interceptor_pos")
        radar_return    = sim_state.get("radar_return", {})
        predicted_ic    = sim_state.get("predicted_intercept")
        events          = sim_state.get("events", [])
        sim_time        = sim_state.get("mission_time", 0.0)
        sim_speed       = sim_state.get("sim_speed", 1.0)

        for ev in events:
            self._event_log.append((ev, status, sim_time))
        self._event_log = self._event_log[-6:]

        dome_fg = _STATUS_COLOR.get(status, C["primary"])

        # ── Header ────────────────────────────────────────────────────────────
        dot = "●" if self._blink_state else "○"
        self._hdr_status.set_text(f"{dot}  {status}")
        self._hdr_status.set_color(dome_fg)
        mins = int(sim_time) // 60; secs = int(sim_time) % 60
        self._hdr_time.set_text(f"T+  {mins:02d}:{secs:02d}")
        self._hdr_speed.set_text(f"SIM  {sim_speed:.2g}×")

        # ── Event log ─────────────────────────────────────────────────────────
        if self._event_log:
            _ev_col = {"CLEAR": C["primary"], "TRACKING": C["amber"],
                       "BREACH": C["red"],    "INTERCEPTED": C["cyan"]}
            parts = []
            for ev, st, t in self._event_log[-4:]:
                m2 = int(t) // 60; s2 = int(t) % 60
                parts.append(f"[T+{m2:02d}:{s2:02d}]  {ev}")
            self._log_text.set_text("   ·   ".join(parts))
            self._log_text.set_color(_ev_col.get(status, C["textdim"]))

        # ── Dome ring color ────────────────────────────────────────────────────
        self._dome_circle.set_color(dome_fg)
        arc_col = dome_fg if status != "CLEAR" else C["amber"]
        self._dome_arc.set_color(arc_col)
        self._dome_base.set_color(arc_col)

        # ── Status badge ──────────────────────────────────────────────────────
        self._status_badge.set_text(f"●  STATUS: {status}")
        self._status_badge.set_color(dome_fg)
        self._status_badge.get_bbox_patch().set_edgecolor(dome_fg)

        # ── Phosphor sweep ────────────────────────────────────────────────────
        self._radar_angle = (self._radar_angle + 15) % 360
        rs = sim_state.get("radar_station", [0, 0, 0])
        sweep_len = self._view * 1.02
        for i, fan in enumerate(self._sweep_fans):
            angle = (self._radar_angle - i * 8) % 360
            rad   = math.radians(angle)
            fan.set_data(
                [rs[0], rs[0] + sweep_len * math.cos(rad)],
                [rs[1], rs[1] + sweep_len * math.sin(rad)])
        self._radar_marker.set_data([rs[0]], [rs[1]])
        self._radar_label.set_position(
            (rs[0] + self._dome_radius * 0.05, rs[1] + self._dome_radius * 0.05))
        self._radar_label.set_visible(True)

        # ── Intruder ──────────────────────────────────────────────────────────
        if intruder_pos:
            self._intruder_trail.append(intruder_pos[:2])
            self._intruder_trail = self._intruder_trail[-60:]
            self._intruder_trail_r.set_data(
                [p[0] for p in self._intruder_trail],
                [p[1] for p in self._intruder_trail])
            self._intruder_dot_r.set_data([intruder_pos[0]], [intruder_pos[1]])
            off = self._dome_radius * 0.04
            self._intruder_label_r.set_position(
                (intruder_pos[0] + off, intruder_pos[1] + off))
            self._intruder_label_r.set_visible(True)
        else:
            self._intruder_trail_r.set_data([], [])
            self._intruder_dot_r.set_data([], [])
            self._intruder_label_r.set_visible(False)

        # ── Interceptor ───────────────────────────────────────────────────────
        if interceptor_pos:
            self._interceptor_trail.append(interceptor_pos[:2])
            self._interceptor_trail = self._interceptor_trail[-60:]
            self._intercept_trail_r.set_data(
                [p[0] for p in self._interceptor_trail],
                [p[1] for p in self._interceptor_trail])
            self._intercept_dot_r.set_data([interceptor_pos[0]], [interceptor_pos[1]])
            off = self._dome_radius * 0.04
            self._intercept_label_r.set_position(
                (interceptor_pos[0] + off, interceptor_pos[1] + off))
            self._intercept_label_r.set_visible(True)
        else:
            self._intercept_trail_r.set_data([], [])
            self._intercept_dot_r.set_data([], [])
            self._intercept_label_r.set_visible(False)

        # ── Prediction ────────────────────────────────────────────────────────
        if interceptor_pos and predicted_ic:
            self._pred_line.set_data(
                [interceptor_pos[0], predicted_ic[0]],
                [interceptor_pos[1], predicted_ic[1]])
            self._pred_dot.set_data([predicted_ic[0]], [predicted_ic[1]])
        else:
            self._pred_line.set_data([], [])
            self._pred_dot.set_data([], [])

        self._paused_text.set_visible(bool(self._ctrl and self._ctrl.paused))

        # ── Altitude / side view ──────────────────────────────────────────────
        if intruder_pos:
            self._intruder_alt_trail.append((intruder_pos[0], intruder_pos[2]))
            self._intruder_alt_trail = self._intruder_alt_trail[-60:]
            self._intruder_trail_s.set_data(
                [p[0] for p in self._intruder_alt_trail],
                [p[1] for p in self._intruder_alt_trail])
            self._intruder_dot_s.set_data([intruder_pos[0]], [intruder_pos[2]])
            self._intruder_label_s.set_text(f"INTR {intruder_pos[2]:.0f}m")
            off = self._dome_radius * 0.03
            self._intruder_label_s.set_position(
                (intruder_pos[0] + off, intruder_pos[2] + off))
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
            self._intercept_label_s.set_position(
                (interceptor_pos[0] + off, interceptor_pos[2] + off))
            self._intercept_label_s.set_visible(True)
        else:
            self._intercept_trail_s.set_data([], [])
            self._intercept_dot_s.set_data([], [])
            self._intercept_label_s.set_visible(False)

        # ── Telemetry cards ───────────────────────────────────────────────────
        i_key = sim_state.get("intruder_key", "shahed136")
        _lmap = {"shahed136": "SHAHED-136", "consumer_quad": "CONSUMER QUAD",
                 "fpv_attack": "FPV ATTACK"}
        tname = _lmap.get(i_key, i_key.upper())

        if intruder_pos:
            rng  = radar_return.get("range") if radar_return.get("detected") else None
            rstr = f"{rng:.0f}m" if rng else "no lock"
            brg  = math.degrees(math.atan2(intruder_pos[0], intruder_pos[1])) % 360
            ispd = sim_state.get("intruder_speed", 0.0)
            self._telem_intruder.set_text(
                f"─ INTRUDER ──────────────────────────────\n"
                f"  RNG  {rstr:>8}    ALT  {intruder_pos[2]:>5.0f}m    SPD  {ispd:.0f}m/s\n"
                f"  BRG  {brg:>7.1f}°    TYPE  {tname}")
        else:
            self._telem_intruder.set_text(
                "─ INTRUDER ──────────────────────────────\n"
                "  RNG  ---           ALT  ---       SPD  ---\n"
                "  BRG  ---           TYPE  ─────────────────")

        if interceptor_pos and intruder_pos:
            sep   = math.sqrt(sum((interceptor_pos[k] - intruder_pos[k])**2 for k in range(3)))
            tti   = sim_state.get("tti", float("inf"))
            xspd  = sim_state.get("interceptor_speed", 0.0)
            tti_s = f"{tti:.1f}s" if tti < 999 else "---"
            st    = "PURSUING" if tti < 999 else "LAUNCHED"
            self._telem_intercept.set_text(
                f"─ INTERCEPTOR ───────────────────────────\n"
                f"  SEP  {sep:>7.0f}m    TTI  {tti_s:>7}    SPD  {xspd:.0f}m/s\n"
                f"  STATUS  {st}")
        else:
            self._telem_intercept.set_text(
                "─ INTERCEPTOR ───────────────────────────\n"
                "  SEP  ---           TTI  ---      SPD  ---\n"
                "  STATUS  STANDBY")

        if radar_return.get("detected"):
            conf = sim_state.get("track_confidence", 0.0)
            snr  = radar_return.get("snr", 0.0)
            self._telem_radar.set_text(
                f"─ RADAR ─────────────────────────────────\n"
                f"  CONF  {conf*100:.0f}%         SNR  {snr:.1f}dB\n"
                f"  TRACK  LOCKED        KALMAN  6-STATE")
        else:
            self._telem_radar.set_text(
                "─ RADAR ─────────────────────────────────\n"
                "  CONF  ---%          SNR  ---dB\n"
                "  TRACK  SEARCHING     LOCK  PENDING")

        # Threat bar
        if intruder_pos:
            threat = max(0.0, 1.0 - math.sqrt(sum(v**2 for v in intruder_pos))
                         / (2 * self._dome_radius))
        else:
            threat = 0.0
        bar_w   = max(0.001, threat * 0.79)
        bar_col = C["primary"] if threat < 0.5 else (C["amber"] if threat < 0.75 else C["red"])
        self._threat_bar.set_width(bar_w)
        self._threat_bar.set_facecolor(bar_col)
        self._threat_pct.set_text(f"{threat*100:.0f}%")
        self._threat_pct.set_color(bar_col)

        try:
            self._fig.canvas.draw_idle()
            self._fig.canvas.flush_events()
        except Exception:
            pass

    def _show_debrief(self, state: dict):
        result   = state.get("result", "---")
        sim_time = state.get("sim_time", 0.0)
        closest  = state.get("closest_approach", float("inf"))

        _result_col  = {"INTERCEPTED": C["primary"], "FAILURE": C["red"],
                        "TIMEOUT": C["amber"], "ABORTED": C["textdim"]}
        _result_icon = {"INTERCEPTED": "★  INTERCEPTED  ★",
                        "FAILURE":     "✗  BREACH — FAILURE  ✗",
                        "TIMEOUT":     "⏱  TIME EXPIRED  ⏱",
                        "ABORTED":     "■  MISSION ABORTED  ■"}
        col  = _result_col.get(result, "white")
        icon = _result_icon.get(result, f"■  {result}  ■")

        lines = [icon, ""]
        lines.append(f"Duration:      {sim_time:.0f} s")
        if closest < 9999:
            lines.append(f"Closest appr:  {closest:.1f} m")
        lines += ["", "─" * 30, "Click a scenario to continue"]

        self._debrief_text.set_text("\n".join(lines))
        self._debrief_text.set_color(col)
        self._debrief_text.get_bbox_patch().set_edgecolor(col)
        self._debrief_text.set_visible(True)

        try:
            self._hdr_status.set_text(f"■  {result}")
            self._hdr_status.set_color(col)
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
