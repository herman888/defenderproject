"""
Real-time PyQtGraph dashboard — DroneShield DroneSentry-C2 / military C2 aesthetic.

Drop-in replacement for the legacy matplotlib dashboard. Same public surface:
    Dashboard(dome_radius, sim_control).update(state_dict)
    Dashboard(...).close()
    SimControl()  ── plain attribute container

Why PyQtGraph:
    * matplotlib's full-figure redraw pipeline caps around 30–40 fps for this layout.
    * PyQtGraph uses QPainter raster rendering with dirty-region updates — easily
      100+ fps on the same content.

Trail rendering:
    Each PPI trail keeps a deque of (x, y, t_birth). On every refresh we age all
    points and recompute brushes with linear alpha decay so the tail fades to
    transparent over ``TRAIL_PERSISTENCE_S`` seconds — the classic phosphor-decay
    look of a real PPI scope.

Threading model:
    The owning process must run a Qt event loop on its main thread. ``update()``
    only mutates Qt items / data buffers and is safe to call from the same
    thread that owns the loop (the typical pattern is a QTimer drain → update).
"""

from __future__ import annotations

import math
import time
from collections import deque

import numpy as np
import pyqtgraph as pg
from pyqtgraph.Qt import QtCore, QtGui, QtWidgets


# ── Color palette (DroneSentry C2) ──────────────────────────────────────────
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
    ("shahed136",     "■ SHAHED-136"),
    ("consumer_quad", "# CONSUMER"),
    ("fpv_attack",    "✕ FPV ATTACK"),
]
_PATTERN_LABELS = [
    ("direct",    "→ DIRECT"),
    ("nap_earth", "↘ NAP-EARTH"),
    ("spiral",    "◎ SPIRAL"),
]
_SPEEDS = [(0.5, "0.5×"), (1.0, "1×"), (2.0, "2×"), (4.0, "4×"), (8.0, "8×")]
_PADS   = [("near", "NEAR 50m"), ("mid", "MID 180m"), ("far", "FAR 380m")]

TRAIL_PERSISTENCE_S = 6.0    # phosphor decay time
TRAIL_HEAD_SIZE     = 11     # marker size for current-position dot


# ─────────────────────────────────────────────────────────────────────────────
class SimControl:
    def __init__(self):
        self.paused              = False
        self.stopped             = False
        self.restart             = False
        self.speed               = 1
        self.pending_intruder    = "shahed136"
        self.selected_mission    = None
        self.selected_speed      = 1.0
        self.selected_pad        = "mid"
        self.selected_pattern    = "direct"
        self.camera_zoom_pending = None


# ─────────────────────────────────────────────────────────────────────────────
def _btn_style(fg: str, border: str, base: str, hover: str, sel: str = None) -> str:
    sel = sel or hover
    return f"""
        QPushButton {{
            background-color: {base};
            color: {fg};
            border: 1.4px solid {border};
            font-family: 'Consolas', 'Courier New', monospace;
            font-size: 10px;
            padding: 4px 6px;
        }}
        QPushButton:hover {{ background-color: {hover}; }}
        QPushButton:checked {{ background-color: {sel}; border-color: {fg}; }}
    """


# ─────────────────────────────────────────────────────────────────────────────
class _FadingTrail:
    """Phosphor-decay PPI trail. Holds (x, y, t_birth) tuples and renders as a
    ScatterPlotItem with per-point alpha that decays linearly to 0 over
    TRAIL_PERSISTENCE_S seconds."""

    def __init__(self, plot_item: pg.PlotItem, color_hex: str,
                 size: int = 4, head_size: int = TRAIL_HEAD_SIZE,
                 head_symbol: str = "d", z_trail: int = 5, z_head: int = 6):
        self._color   = QtGui.QColor(color_hex)
        self._size    = size
        self._buf: deque[tuple[float, float, float]] = deque(maxlen=600)

        self._scatter = pg.ScatterPlotItem(
            size=size, pen=None, brush=None, pxMode=True)
        self._scatter.setZValue(z_trail)
        plot_item.addItem(self._scatter)

        self._head = pg.ScatterPlotItem(
            size=head_size, symbol=head_symbol,
            pen=pg.mkPen(color_hex, width=1.5),
            brush=pg.mkBrush(QtGui.QColor(color_hex)))
        self._head.setZValue(z_head)
        plot_item.addItem(self._head)

    def append(self, x: float, y: float, t: float) -> None:
        self._buf.append((float(x), float(y), float(t)))

    def clear(self) -> None:
        self._buf.clear()
        self._scatter.setData([])
        self._head.setData([])

    def hide(self) -> None:
        self._scatter.setData([])
        self._head.setData([])

    def render(self, now: float) -> None:
        if not self._buf:
            self._scatter.setData([])
            self._head.setData([])
            return

        # drop expired
        while self._buf and (now - self._buf[0][2]) > TRAIL_PERSISTENCE_S:
            self._buf.popleft()
        if not self._buf:
            self._scatter.setData([])
            self._head.setData([])
            return

        n   = len(self._buf)
        xs  = np.empty(n, dtype=np.float32)
        ys  = np.empty(n, dtype=np.float32)
        brs = np.empty(n, dtype=object)
        base_r, base_g, base_b = self._color.red(), self._color.green(), self._color.blue()
        for i, (x, y, t) in enumerate(self._buf):
            age   = now - t
            alpha = max(0, min(255, int(255 * (1.0 - age / TRAIL_PERSISTENCE_S))))
            xs[i] = x; ys[i] = y
            brs[i] = pg.mkBrush(base_r, base_g, base_b, alpha)
        self._scatter.setData(x=xs, y=ys, brush=brs.tolist(), pen=None, size=self._size)

        # head dot at most-recent point
        hx, hy, _ = self._buf[-1]
        self._head.setData(x=[hx], y=[hy])


# ─────────────────────────────────────────────────────────────────────────────
class _FpsGraphicsLayoutWidget(pg.GraphicsLayoutWidget):
    """GraphicsLayoutWidget that timestamps actual `paintEvent` calls.

    True render-rate measurement: every painted frame appends ``perf_counter()``
    to ``self._paint_times``. If Qt drops paints under load this naturally
    reflects it, unlike a QTimer-tick counter which only reports how often the
    timer is firing.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._paint_times: deque[float] = deque(maxlen=240)

    def paintEvent(self, ev):                                  # type: ignore[override]
        super().paintEvent(ev)
        self._paint_times.append(time.perf_counter())


# ───────────────────────────────────────────────────────────────────────────
class Dashboard(QtWidgets.QMainWindow):
    """PyQtGraph C-UAS C2 dashboard. Public API matches legacy matplotlib version."""

    def __init__(self, dome_radius: float = 200.0, sim_control: SimControl = None):
        super().__init__()
        self._dome_radius     = float(dome_radius)
        self._view            = self._dome_radius * 4.0
        self._ctrl            = sim_control or SimControl()
        self._event_log: list[tuple[str, str, float]] = []
        self._radar_angle     = 0.0
        self._t_start_wall    = time.time()
        self._last_blink      = time.time()
        self._blink_state     = False
        self._mission_active  = False

        # ── Window chrome ─────────────────────────────────────────────────
        self.setWindowTitle("ANTI-DRONE DEFENSE SYSTEM  —  C-UAS COMMAND")
        self.resize(1360, 850)
        self.setStyleSheet(f"""
            QMainWindow, QWidget {{ background-color: {C['bg']}; }}
            QLabel {{ color: {C['text']}; font-family: 'Consolas', 'Courier New', monospace; }}
        """)

        pg.setConfigOptions(antialias=True, useOpenGL=False, background=C["panel"],
                            foreground=C["text"])

        central = QtWidgets.QWidget(self)
        self.setCentralWidget(central)
        root = QtWidgets.QVBoxLayout(central)
        root.setContentsMargins(6, 4, 6, 6)
        root.setSpacing(4)

        self._build_header(root)
        self._build_main_viz(root)
        self._build_event_log(root)
        self._build_mission_panel(root)
        self._build_controls_row(root)

        # Sweep / blink animation tied to a 60 Hz QTimer (independent of state push).
        self._anim_timer = QtCore.QTimer(self)
        self._anim_timer.timeout.connect(self._on_anim_tick)
        self._anim_timer.start(16)
        self._last_anim = time.time()

        # FPS update timer (every 250 ms — cheap label update)
        self._fps_timer = QtCore.QTimer(self)
        self._fps_timer.timeout.connect(self._refresh_fps_label)
        self._fps_timer.start(250)

        self.show()

    # ── Header ────────────────────────────────────────────────────────────
    def _build_header(self, root: QtWidgets.QVBoxLayout) -> None:
        bar = QtWidgets.QFrame()
        bar.setFixedHeight(44)
        bar.setStyleSheet(
            f"QFrame {{ background-color: {C['panel']}; "
            f"border-top: 2px solid {C['primary']}; "
            f"border-bottom: 1px solid {C['border']}; }}")
        h = QtWidgets.QHBoxLayout(bar)
        h.setContentsMargins(10, 4, 10, 4)

        title = QtWidgets.QLabel("◈  ANTI-DRONE DEFENSE SYSTEM")
        title.setStyleSheet(f"color: {C['white']}; font-size: 13px; font-weight: bold;")
        sub = QtWidgets.QLabel("C-UAS COMMAND & CONTROL  v1.0")
        sub.setStyleSheet(f"color: {C['textdim']}; font-size: 8px;")
        title_box = QtWidgets.QVBoxLayout()
        title_box.setContentsMargins(0, 0, 0, 0)
        title_box.addWidget(title); title_box.addWidget(sub)
        title_w = QtWidgets.QWidget(); title_w.setLayout(title_box)
        h.addWidget(title_w, stretch=1)

        self._hdr_status = QtWidgets.QLabel("●  STANDBY")
        self._hdr_status.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self._hdr_status.setStyleSheet(
            f"color: {C['primary']}; font-size: 12px; font-weight: bold;")
        h.addWidget(self._hdr_status, stretch=2)

        right_box = QtWidgets.QVBoxLayout()
        right_box.setContentsMargins(0, 0, 0, 0)
        self._hdr_time = QtWidgets.QLabel("T+  00:00")
        self._hdr_time.setAlignment(QtCore.Qt.AlignmentFlag.AlignRight)
        self._hdr_time.setStyleSheet(f"color: {C['text']}; font-size: 12px;")
        self._hdr_speed = QtWidgets.QLabel("SIM  1.0×   FPS --")
        self._hdr_speed.setAlignment(QtCore.Qt.AlignmentFlag.AlignRight)
        self._hdr_speed.setStyleSheet(f"color: {C['textdim']}; font-size: 8px;")
        right_box.addWidget(self._hdr_time); right_box.addWidget(self._hdr_speed)
        right_w = QtWidgets.QWidget(); right_w.setLayout(right_box)
        h.addWidget(right_w, stretch=1)

        root.addWidget(bar)

    # ── Main viz row ──────────────────────────────────────────────────────
    def _build_main_viz(self, root: QtWidgets.QVBoxLayout) -> None:
        """Layout: [ radar PPI ] | [ altitude (top) / telemetry (bottom) ]."""
        # Left: radar PPI in its own FPS-instrumented GraphicsLayoutWidget
        self._gw_radar = _FpsGraphicsLayoutWidget()
        self._gw_radar.setBackground(C["bg"])
        self._gw_radar.ci.setSpacing(0)
        self._gw_radar.ci.setContentsMargins(2, 2, 2, 2)
        self._ax_radar = self._gw_radar.addPlot(row=0, col=0)
        self._setup_radar_ax(self._ax_radar)

        # Right top: altitude in its own GraphicsLayoutWidget
        self._gw_side = pg.GraphicsLayoutWidget()
        self._gw_side.setBackground(C["bg"])
        self._gw_side.ci.setSpacing(0)
        self._gw_side.ci.setContentsMargins(2, 2, 2, 2)
        self._ax_side = self._gw_side.addPlot(row=0, col=0)
        self._setup_side_ax(self._ax_side)

        # Right bottom: telemetry panel (Qt widget — crisp text)
        self._telem_panel = self._build_telem_panel()
        self._telem_panel.setMinimumHeight(140)

        # Stack altitude + telemetry vertically on the right
        right_col = QtWidgets.QWidget()
        right_v = QtWidgets.QVBoxLayout(right_col)
        right_v.setContentsMargins(0, 0, 0, 0); right_v.setSpacing(4)
        right_v.addWidget(self._gw_side, stretch=5)
        right_v.addWidget(self._telem_panel, stretch=4)

        # Horizontal split: radar | right column
        split = QtWidgets.QSplitter(QtCore.Qt.Orientation.Horizontal)
        split.addWidget(self._gw_radar)
        split.addWidget(right_col)
        split.setStretchFactor(0, 11)
        split.setStretchFactor(1, 9)
        split.setHandleWidth(2)
        split.setStyleSheet(
            f"QSplitter::handle {{ background-color: {C['border']}; }}")

        root.addWidget(split, stretch=20)
        self._init_artists()

    def _setup_radar_ax(self, ax: pg.PlotItem) -> None:
        v = self._view
        R = self._dome_radius
        ax.setAspectLocked(True, ratio=1.0)
        ax.setXRange(-v, v, padding=0)
        ax.setYRange(-v, v, padding=0)
        ax.hideAxis("bottom"); ax.hideAxis("left")
        ax.setMouseEnabled(x=False, y=False)
        ax.setMenuEnabled(False)
        ax.setTitle('<span style="color:#00e676; font-family:Consolas;">'
                    'RADAR  —  TOP DOWN</span>', size="9pt")
        # Crosshairs (horizontal + vertical through origin)
        for ang in (0, 90):
            ax.addItem(pg.InfiniteLine(pos=0, angle=ang,
                       pen=pg.mkPen(QtGui.QColor(C["dim"]), width=0.6)))
        # Half-quadrant guides
        for frac in (0.5, -0.5):
            for ang in (0, 90):
                ln = pg.InfiniteLine(pos=v*frac, angle=ang,
                                     pen=pg.mkPen(QtGui.QColor(C["dim"]),
                                                   width=0.4, style=QtCore.Qt.PenStyle.DotLine))
                ax.addItem(ln)

        # Range rings
        ring_specs = [
            (R*0.25, C["dim"],     0.5, None,             False),
            (R*0.50, C["dim"],     0.6, f"{R*0.5:.0f}m",  False),
            (R,      C["primary"], 2.5, f"{R:.0f}m  DOME", True),
            (R*2.0,  C["dim"],     0.5, f"{R*2:.0f}m",    False),
            (R*3.0,  C["dim"],     0.4, None,             False),
        ]
        theta = np.linspace(0, 2*math.pi, 256)
        for r, col, lw, label, dome in ring_specs:
            if r > v * 0.98:
                continue
            xs = r * np.cos(theta); ys = r * np.sin(theta)
            pen = pg.mkPen(QtGui.QColor(col), width=lw)
            if not dome:
                pen.setStyle(QtCore.Qt.PenStyle.DashLine)
            ax.plot(xs, ys, pen=pen)
            if label:
                t = pg.TextItem(text=label, color=C["textdim"], anchor=(0, 0.5))
                t.setPos(r + v*0.012, 0)
                font = QtGui.QFont("Consolas", 7)
                t.setFont(font)
                ax.addItem(t)

        # Cardinal labels
        for x, y, txt in [(0, v*0.93, "N▲"), (0, -v*0.93, "▼S"),
                          (v*0.93, 0, "E►"), (-v*0.93, 0, "◄W")]:
            t = pg.TextItem(text=txt, color=C["textdim"], anchor=(0.5, 0.5))
            t.setFont(QtGui.QFont("Consolas", 8, QtGui.QFont.Weight.Bold))
            t.setPos(x, y); ax.addItem(t)

    def _setup_side_ax(self, ax: pg.PlotItem) -> None:
        R = self._dome_radius
        ax.setXRange(-self._view, self._view, padding=0)
        ax.setYRange(-R*0.05, R*1.8, padding=0)
        ax.setMouseEnabled(x=False, y=False)
        ax.setMenuEnabled(False)
        ax.setTitle('<span style="color:#00e5ff; font-family:Consolas;">'
                    'ALTITUDE  —  X / Z</span>', size="9pt")
        ax.hideAxis("bottom")
        ax.showAxis("right")
        ay = ax.getAxis("right")
        ay.setTextPen(pg.mkPen(QtGui.QColor(C["textdim"])))
        ay.setPen(pg.mkPen(QtGui.QColor(C["border"])))
        ay.setTicks([[(0, "0m"), (R*0.5, f"{R*0.5:.0f}m"),
                      (R, f"{R:.0f}m"), (R*1.5, f"{R*1.5:.0f}m")]])
        ax.hideAxis("left")
        # Ground line
        ax.addItem(pg.InfiniteLine(pos=0, angle=0,
                                   pen=pg.mkPen(QtGui.QColor(C["dim"]), width=0.8)))
        # Dome arc + base
        theta = np.linspace(0, math.pi, 80)
        self._dome_arc = ax.plot(R*np.cos(theta), R*np.sin(theta),
                                 pen=pg.mkPen(QtGui.QColor(C["amber"]), width=1.8))
        self._dome_base = ax.plot([-R, R], [0, 0],
                                  pen=pg.mkPen(QtGui.QColor(C["amber"]), width=1.8))

    # ── Telemetry panel (Qt widget — crisp text) ──────────────────────────
    def _build_telem_panel(self) -> QtWidgets.QWidget:
        frame = QtWidgets.QFrame()
        frame.setStyleSheet(
            f"QFrame {{ background-color: {C['panel']}; "
            f"border: 1px solid {C['border']}; }}"
            f"QLabel {{ font-family: 'Consolas', 'Courier New', monospace; "
            f"font-size: 9px; }}")
        v = QtWidgets.QVBoxLayout(frame)
        v.setContentsMargins(8, 6, 8, 6); v.setSpacing(3)

        self._telem_intruder = QtWidgets.QLabel(
            "─ INTRUDER ──────────────────────────────\n"
            "  RNG  ---        ALT  ---        SPD  ---\n"
            "  BRG  ---        TYPE  ─────────────────")
        self._telem_intruder.setStyleSheet(f"color: {C['red']};")
        v.addWidget(self._telem_intruder)

        self._telem_intercept = QtWidgets.QLabel(
            "─ INTERCEPTOR ───────────────────────────\n"
            "  SEP  ---        TTI  ---     SPD  ---\n"
            "  STATUS  STANDBY")
        self._telem_intercept.setStyleSheet(f"color: {C['blue']};")
        v.addWidget(self._telem_intercept)

        self._telem_radar = QtWidgets.QLabel(
            "─ RADAR ─────────────────────────────────\n"
            "  CONF  ---%       SNR  ---dB\n"
            "  TRACK  SEARCHING    LOCK  PENDING")
        self._telem_radar.setStyleSheet(f"color: {C['primary']};")
        v.addWidget(self._telem_radar)

        # Threat row
        threat_row = QtWidgets.QHBoxLayout()
        thlbl = QtWidgets.QLabel("THREAT")
        thlbl.setStyleSheet(f"color: {C['textdim']}; font-size: 8px;")
        self._threat_bar = QtWidgets.QProgressBar()
        self._threat_bar.setRange(0, 100); self._threat_bar.setValue(0)
        self._threat_bar.setTextVisible(False)
        self._threat_bar.setFixedHeight(10)
        self._threat_bar.setStyleSheet(
            f"QProgressBar {{ background-color: {C['dim']}; border: 0px; }}"
            f"QProgressBar::chunk {{ background-color: {C['primary']}; }}")
        self._threat_pct = QtWidgets.QLabel("0%")
        self._threat_pct.setStyleSheet(f"color: {C['textdim']}; font-size: 9px;")
        self._threat_pct.setFixedWidth(36)
        self._threat_pct.setAlignment(QtCore.Qt.AlignmentFlag.AlignRight)
        threat_row.addWidget(thlbl); threat_row.addWidget(self._threat_bar, 1)
        threat_row.addWidget(self._threat_pct)
        v.addLayout(threat_row)
        return frame

    # ── Event log strip ───────────────────────────────────────────────────
    def _build_event_log(self, root: QtWidgets.QVBoxLayout) -> None:
        bar = QtWidgets.QFrame()
        bar.setFixedHeight(36)
        bar.setStyleSheet(
            f"QFrame {{ background-color: {C['panel']}; "
            f"border-top: 1px solid {C['border']}; "
            f"border-bottom: 1px solid {C['border']}; }}")
        h = QtWidgets.QHBoxLayout(bar)
        h.setContentsMargins(10, 2, 10, 2)
        head = QtWidgets.QLabel("EVENT LOG")
        head.setStyleSheet(f"color: {C['textdim']}; font-size: 7px; font-weight: bold;")
        head.setFixedWidth(70)
        self._log_text = QtWidgets.QLabel("─  No events")
        self._log_text.setStyleSheet(
            f"color: {C['textdim']}; font-size: 9px; "
            f"font-family: 'Consolas', 'Courier New', monospace;")
        h.addWidget(head); h.addWidget(self._log_text, 1)
        root.addWidget(bar)

    # ── Mission select panel ──────────────────────────────────────────────
    def _build_mission_panel(self, root: QtWidgets.QVBoxLayout) -> None:
        frame = QtWidgets.QFrame()
        frame.setStyleSheet(f"QFrame {{ background-color: {C['bg']}; }}")
        grid = QtWidgets.QGridLayout(frame)
        grid.setContentsMargins(2, 4, 2, 2); grid.setSpacing(4)

        # Row 0: 3 intruders + 5 speeds
        self._mission_btns: dict[str, QtWidgets.QPushButton] = {}
        for i, (key, label) in enumerate(_INTRUDER_LABELS):
            b = QtWidgets.QPushButton(label)
            b.setCheckable(True); b.setChecked(key == "shahed136")
            b.setStyleSheet(_btn_style(
                C["primary"], "#2a6a2a", "#0e1a0e", "#163a1a", "#1a4020"))
            b.clicked.connect(lambda _, k=key: self._on_mission(k))
            self._mission_btns[key] = b
            grid.addWidget(b, 0, i)

        self._speed_btns: dict[float, QtWidgets.QPushButton] = {}
        for i, (spd, lbl) in enumerate(_SPEEDS):
            b = QtWidgets.QPushButton(lbl)
            b.setCheckable(True); b.setChecked(spd == 1.0)
            b.setStyleSheet(_btn_style(
                C["cyan"], "#1a4a8a", "#0a0f22", "#0d162e", "#0f1a48"))
            b.clicked.connect(lambda _, s=spd: self._on_speed_select(s))
            self._speed_btns[spd] = b
            grid.addWidget(b, 0, 4 + i)

        # Row 1: 3 patterns + 3 pads + hint
        self._pattern_btns: dict[str, QtWidgets.QPushButton] = {}
        for i, (key, lbl) in enumerate(_PATTERN_LABELS):
            b = QtWidgets.QPushButton(lbl)
            b.setCheckable(True); b.setChecked(key == "direct")
            b.setStyleSheet(_btn_style(
                C["amber"], "#4a4010", "#110e05", "#1a1408", "#201a06"))
            b.clicked.connect(lambda _, k=key: self._on_pattern_select(k))
            self._pattern_btns[key] = b
            grid.addWidget(b, 1, i)

        self._pad_btns: dict[str, QtWidgets.QPushButton] = {}
        for i, (key, lbl) in enumerate(_PADS):
            b = QtWidgets.QPushButton(lbl)
            b.setCheckable(True); b.setChecked(key == "mid")
            b.setStyleSheet(_btn_style(
                "#cc99ff", "#4a1a7a", "#0e0a1a", "#160c24", "#1a0e2e"))
            b.clicked.connect(lambda _, k=key: self._on_pad_select(k))
            self._pad_btns[key] = b
            grid.addWidget(b, 1, 4 + i)

        hint = QtWidgets.QLabel(
            "Select intruder · pattern · pad · speed\n"
            "then  ▶ START  to launch the 3-D sim")
        hint.setStyleSheet(
            f"color: {C['textdim']}; font-size: 8px; "
            f"font-family: 'Consolas', 'Courier New', monospace;")
        hint.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        grid.addWidget(hint, 1, 8, 1, 3)

        # Even column stretch
        for c in range(11):
            grid.setColumnStretch(c, 1)
        root.addWidget(frame, stretch=3)

    # ── Controls row ──────────────────────────────────────────────────────
    def _build_controls_row(self, root: QtWidgets.QVBoxLayout) -> None:
        bar = QtWidgets.QFrame()
        bar.setFixedHeight(46)
        bar.setStyleSheet(f"QFrame {{ background-color: {C['bg']}; }}")
        h = QtWidgets.QHBoxLayout(bar)
        h.setContentsMargins(2, 4, 2, 2); h.setSpacing(6)

        self._btn_pause = QtWidgets.QPushButton("|| PAUSE")
        self._btn_reset = QtWidgets.QPushButton("↺  RESET")
        self._btn_start = QtWidgets.QPushButton("▶  START")
        self._btn_abort = QtWidgets.QPushButton("◼  ABORT")
        sep_lbl  = QtWidgets.QLabel("3-D CAM")
        sep_lbl.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        sep_lbl.setStyleSheet(f"color: {C['textdim']}; font-size: 8px;")
        self._btn_zoom_in  = QtWidgets.QPushButton("+")
        self._btn_zoom_out = QtWidgets.QPushButton("−")

        self._btn_pause.setStyleSheet(_btn_style(C["primary"], C["primary"], "#0a1808", "#112010"))
        self._btn_reset.setStyleSheet(_btn_style(C["amber"],   C["amber"],   "#141008", "#201808"))
        self._btn_start.setStyleSheet(_btn_style(C["white"],   C["primary"], "#0d2010", "#163015"))
        self._btn_abort.setStyleSheet(_btn_style(C["red"],     C["red"],     "#1e0508", "#2e0810"))
        self._btn_zoom_in.setStyleSheet(_btn_style(C["cyan"],  C["cyan"],    "#061212", "#0c2020"))
        self._btn_zoom_out.setStyleSheet(_btn_style(C["cyan"], C["cyan"],    "#061212", "#0c2020"))

        for w, s in ((self._btn_pause, 3), (self._btn_reset, 3),
                     (self._btn_start, 3), (self._btn_abort, 3),
                     (sep_lbl, 1), (self._btn_zoom_in, 1), (self._btn_zoom_out, 1)):
            h.addWidget(w, stretch=s)

        self._btn_pause.clicked.connect(self._on_pause)
        self._btn_reset.clicked.connect(self._on_reset)
        self._btn_start.clicked.connect(self._on_start)
        self._btn_abort.clicked.connect(self._on_abort)
        self._btn_zoom_in.clicked.connect(lambda _: self._on_zoom("in"))
        self._btn_zoom_out.clicked.connect(lambda _: self._on_zoom("out"))

        root.addWidget(bar)

    # ── Initial radar/altitude artists ────────────────────────────────────
    def _init_artists(self) -> None:
        ax = self._ax_radar
        R  = self._dome_radius

        # Dome ring
        theta = np.linspace(0, 2*math.pi, 256)
        self._dome_circle = ax.plot(
            R*np.cos(theta), R*np.sin(theta),
            pen=pg.mkPen(QtGui.QColor(C["primary"]), width=2.5))

        # Phosphor sweep — persistent wedge + single rotating beam
        self._sweep_wedge = QtWidgets.QGraphicsPolygonItem()
        self._sweep_wedge.setBrush(QtGui.QBrush(QtGui.QColor(0, 180, 60, 45)))
        self._sweep_wedge.setPen(QtGui.QPen(QtCore.Qt.PenStyle.NoPen))
        self._sweep_wedge.setZValue(3)
        ax.addItem(self._sweep_wedge)
        self._sweep_beam = ax.plot([], [], pen=pg.mkPen(QtGui.QColor(0, 230, 118, 255), width=2.0))
        self._sweep_beam.setZValue(4)
        self._sweep_beam.setVisible(False)
        self._sweep_wedge.setVisible(False)

        # Radar marker
        self._radar_marker = pg.ScatterPlotItem(
            size=8, symbol="s",
            pen=pg.mkPen(QtGui.QColor(C["primary"]), width=1.5),
            brush=pg.mkBrush(QtGui.QColor(C["primary"])))
        ax.addItem(self._radar_marker)

        # Fading PPI trails
        self._intruder_ppi   = _FadingTrail(ax, "#ff1744", size=4,
                                            head_size=11, head_symbol="d")
        self._intercept_ppi  = _FadingTrail(ax, "#2979ff", size=4,
                                            head_size=12, head_symbol="t1")

        # Prediction line + cross
        self._pred_line = ax.plot([], [], pen=pg.mkPen(
            QtGui.QColor(C["amber"]), width=1.5,
            style=QtCore.Qt.PenStyle.DashLine))
        self._pred_dot = pg.ScatterPlotItem(
            size=12, symbol="x",
            pen=pg.mkPen(QtGui.QColor(C["amber"]), width=2),
            brush=None)
        ax.addItem(self._pred_dot)

        # Status badge
        self._status_badge = pg.TextItem(
            text="●  STATUS: STANDBY",
            color=C["primary"], anchor=(0, 0),
            border=pg.mkPen(QtGui.QColor(C["border"])),
            fill=pg.mkBrush(QtGui.QColor("#010f05")))
        self._status_badge.setFont(QtGui.QFont("Consolas", 9, QtGui.QFont.Weight.Bold))
        self._status_badge.setPos(-self._view*0.96, self._view*0.93)
        ax.addItem(self._status_badge)

        # PAUSED overlay
        self._paused_text = pg.TextItem(
            text="── PAUSED ──", color=C["amber"], anchor=(0.5, 0.5),
            border=pg.mkPen(QtGui.QColor(C["amber"])),
            fill=pg.mkBrush(QtGui.QColor(C["bg"])))
        self._paused_text.setFont(QtGui.QFont("Consolas", 18, QtGui.QFont.Weight.Bold))
        self._paused_text.setPos(0, 0)
        self._paused_text.setVisible(False)
        ax.addItem(self._paused_text)

        # Debrief overlay
        self._debrief_text = pg.TextItem(
            text="", color=C["primary"], anchor=(0.5, 0.5),
            border=pg.mkPen(QtGui.QColor(C["primary"])),
            fill=pg.mkBrush(QtGui.QColor("#020a04")))
        self._debrief_text.setFont(QtGui.QFont("Consolas", 11, QtGui.QFont.Weight.Bold))
        self._debrief_text.setPos(0, 0)
        self._debrief_text.setVisible(False)
        ax.addItem(self._debrief_text)

        # Altitude trails
        self._intruder_alt   = _FadingTrail(self._ax_side, "#ff1744", size=4,
                                            head_size=11, head_symbol="d")
        self._intercept_alt  = _FadingTrail(self._ax_side, "#2979ff", size=4,
                                            head_size=12, head_symbol="t1")

    # ── Animation tick (sweep + blink) ────────────────────────────────────
    def _on_anim_tick(self) -> None:
        now = time.time()
        dt  = min(now - self._last_anim, 0.2)
        self._last_anim = now
        if now - self._last_blink >= 1.0:
            self._blink_state = not self._blink_state
            self._last_blink = now

        rs = getattr(self, "_radar_station", [0, 0, 0])
        self._radar_marker.setData(x=[rs[0]], y=[rs[1]])
        if not self._mission_active:
            self._sweep_beam.setVisible(False)
            self._sweep_wedge.setVisible(False)
        else:
            self._radar_angle = (self._radar_angle + 72.0 * dt) % 360
            sweep_len = self._view * 1.02
            cur_rad = math.radians(self._radar_angle)
            self._sweep_beam.setData(
                [rs[0], rs[0] + sweep_len * math.cos(cur_rad)],
                [rs[1], rs[1] + sweep_len * math.sin(cur_rad)])
            trailing = self._radar_angle - 25.0
            pts = [QtCore.QPointF(rs[0], rs[1])]
            for k in range(21):
                a = math.radians(trailing + k * 25.0 / 20)
                pts.append(QtCore.QPointF(
                    rs[0] + sweep_len * math.cos(a),
                    rs[1] + sweep_len * math.sin(a)))
            self._sweep_wedge.setPolygon(QtGui.QPolygonF(pts))
            self._sweep_beam.setVisible(True)
            self._sweep_wedge.setVisible(True)

        # Trails fade continuously even when no new state arrives
        self._intruder_ppi.render(now)
        self._intercept_ppi.render(now)
        self._intruder_alt.render(now)
        self._intercept_alt.render(now)

    def _refresh_fps_label(self) -> None:
        # True render rate: measured from actual paintEvent timestamps on the
        # radar GraphicsLayoutWidget, NOT the QTimer firing rate. If Qt drops
        # paints under load this label reflects it; a timer-tick counter would not.
        pts = self._gw_radar._paint_times
        n = len(pts)
        if n < 2:
            return
        span = pts[-1] - pts[0]
        if span <= 0:
            return
        fps = (n - 1) / span
        # Update FPS portion of the speed label without losing the speed value.
        cur = self._hdr_speed.text()
        if "  FPS" in cur:
            cur = cur.split("  FPS")[0]
        self._hdr_speed.setText(f"{cur}  FPS {fps:4.1f}")

    # ── Button callbacks ──────────────────────────────────────────────────
    def _on_pause(self):
        self._ctrl.paused = not self._ctrl.paused
        self._btn_pause.setText(">  RESUME" if self._ctrl.paused else "|| PAUSE")

    def _on_reset(self):
        self._ctrl.restart = True

    def _on_abort(self):
        self._ctrl.stopped = True
        self._btn_abort.setText("◼  ABORTED")

    def _on_zoom(self, direction: str):
        self._ctrl.camera_zoom_pending = direction

    def _on_mission(self, key: str):
        self._ctrl.pending_intruder = key
        for k, b in self._mission_btns.items():
            b.setChecked(k == key)

    def _on_start(self):
        self._ctrl.selected_mission = self._ctrl.pending_intruder

    def _on_pattern_select(self, key: str):
        self._ctrl.selected_pattern = key
        for k, b in self._pattern_btns.items():
            b.setChecked(k == key)

    def _on_speed_select(self, speed: float):
        self._ctrl.selected_speed = speed
        for s, b in self._speed_btns.items():
            b.setChecked(s == speed)

    def _on_pad_select(self, key: str):
        self._ctrl.selected_pad = key
        for k, b in self._pad_btns.items():
            b.setChecked(k == key)

    # ── State helpers ─────────────────────────────────────────────────────
    def _clear_trails(self):
        self._intruder_ppi.clear()
        self._intercept_ppi.clear()
        self._intruder_alt.clear()
        self._intercept_alt.clear()
        self._event_log.clear()

    def _reset_buttons(self):
        self._ctrl.stopped = False
        self._ctrl.restart = False
        self._ctrl.paused  = False
        self._btn_abort.setText("◼  ABORT")
        self._btn_pause.setText("|| PAUSE")

    # ── Main update entry point ───────────────────────────────────────────
    def update(self, sim_state: dict) -> None:                  # noqa: C901
        msg_type = sim_state.get("type")

        if msg_type == "mission_start":
            self._clear_trails()
            self._debrief_text.setVisible(False)
            self._reset_buttons()
            self._mission_active = True
            return
        if msg_type in ("reset", "show_menu"):
            self._clear_trails()
            self._debrief_text.setVisible(False)
            self._mission_active = False
            return
        if msg_type == "debrief":
            self._show_debrief(sim_state)
            return

        now = time.time()
        status          = sim_state.get("dome_status", "CLEAR")
        intruder_pos    = sim_state.get("intruder_pos")
        interceptor_pos = sim_state.get("interceptor_pos")
        radar_return    = sim_state.get("radar_return", {}) or {}
        predicted_ic    = sim_state.get("predicted_intercept")
        events          = sim_state.get("events", []) or []
        sim_time        = sim_state.get("mission_time", 0.0)
        sim_speed       = sim_state.get("sim_speed", 1.0)
        self._radar_station = sim_state.get("radar_station", [0, 0, 0])

        for ev in events:
            self._event_log.append((ev, status, sim_time))
        self._event_log = self._event_log[-6:]

        dome_fg = _STATUS_COLOR.get(status, C["primary"])

        # ── Header ────────────────────────────────────────────────────────
        dot = "●" if self._blink_state else "○"
        self._hdr_status.setText(f"{dot}  {status}")
        self._hdr_status.setStyleSheet(
            f"color: {dome_fg}; font-size: 12px; font-weight: bold;")
        mins = int(sim_time) // 60; secs = int(sim_time) % 60
        self._hdr_time.setText(f"T+  {mins:02d}:{secs:02d}")
        # Keep FPS suffix; only replace the "SIM" portion.
        cur = self._hdr_speed.text()
        suffix = ""
        if "  FPS" in cur:
            suffix = "  FPS" + cur.split("  FPS", 1)[1]
        self._hdr_speed.setText(f"SIM  {sim_speed:.2g}×{suffix}")

        # ── Event log ─────────────────────────────────────────────────────
        if self._event_log:
            ev_col = {"CLEAR": C["primary"], "TRACKING": C["amber"],
                      "BREACH": C["red"],    "INTERCEPTED": C["cyan"]}
            parts = []
            for ev, _st, t in self._event_log[-4:]:
                m2 = int(t) // 60; s2 = int(t) % 60
                parts.append(f"[T+{m2:02d}:{s2:02d}]  {ev}")
            self._log_text.setText("   ·   ".join(parts))
            self._log_text.setStyleSheet(
                f"color: {ev_col.get(status, C['textdim'])}; font-size: 9px; "
                f"font-family: 'Consolas', 'Courier New', monospace;")

        # ── Dome ring color & altitude arc ────────────────────────────────
        self._dome_circle.setPen(pg.mkPen(QtGui.QColor(dome_fg), width=2.5))
        arc_col = dome_fg if status != "CLEAR" else C["amber"]
        self._dome_arc.setPen(pg.mkPen(QtGui.QColor(arc_col), width=1.8))
        self._dome_base.setPen(pg.mkPen(QtGui.QColor(arc_col), width=1.8))

        # ── Status badge ──────────────────────────────────────────────────
        self._status_badge.setText(f"●  STATUS: {status}")
        self._status_badge.setColor(QtGui.QColor(dome_fg))

        # ── Intruder trail ────────────────────────────────────────────────
        if intruder_pos:
            self._intruder_ppi.append(intruder_pos[0], intruder_pos[1], now)
            self._intruder_alt.append(intruder_pos[0], intruder_pos[2], now)
        else:
            self._intruder_ppi.hide(); self._intruder_alt.hide()

        # ── Interceptor trail ─────────────────────────────────────────────
        if interceptor_pos:
            self._intercept_ppi.append(interceptor_pos[0], interceptor_pos[1], now)
            self._intercept_alt.append(interceptor_pos[0], interceptor_pos[2], now)
        else:
            self._intercept_ppi.hide(); self._intercept_alt.hide()

        # ── Prediction ────────────────────────────────────────────────────
        if interceptor_pos and predicted_ic:
            self._pred_line.setData(
                [interceptor_pos[0], predicted_ic[0]],
                [interceptor_pos[1], predicted_ic[1]])
            self._pred_dot.setData(x=[predicted_ic[0]], y=[predicted_ic[1]])
        else:
            self._pred_line.setData([], [])
            self._pred_dot.setData([], [])

        self._paused_text.setVisible(bool(self._ctrl and self._ctrl.paused))

        # ── Telemetry ─────────────────────────────────────────────────────
        i_key = sim_state.get("intruder_key", "shahed136")
        lmap = {"shahed136": "SHAHED-136", "consumer_quad": "CONSUMER QUAD",
                "fpv_attack": "FPV ATTACK"}
        tname = lmap.get(i_key, i_key.upper())

        if intruder_pos:
            rng  = radar_return.get("range") if radar_return.get("detected") else None
            rstr = f"{rng:.0f}m" if rng else "no lock"
            brg  = math.degrees(math.atan2(intruder_pos[0], intruder_pos[1])) % 360
            ispd = sim_state.get("intruder_speed", 0.0)
            self._telem_intruder.setText(
                f"─ INTRUDER ──────────────────────────────\n"
                f"  RNG  {rstr:>8}    ALT  {intruder_pos[2]:>5.0f}m    SPD  {ispd:.0f}m/s\n"
                f"  BRG  {brg:>7.1f}°    TYPE  {tname}")
        else:
            self._telem_intruder.setText(
                "─ INTRUDER ──────────────────────────────\n"
                "  RNG  ---           ALT  ---       SPD  ---\n"
                "  BRG  ---           TYPE  ─────────────────")

        if interceptor_pos and intruder_pos:
            sep   = math.sqrt(sum((interceptor_pos[k] - intruder_pos[k])**2 for k in range(3)))
            tti   = sim_state.get("tti", float("inf"))
            xspd  = sim_state.get("interceptor_speed", 0.0)
            tti_s = f"{tti:.1f}s" if tti < 999 else "---"
            st    = "PURSUING" if tti < 999 else "LAUNCHED"
            self._telem_intercept.setText(
                f"─ INTERCEPTOR ───────────────────────────\n"
                f"  SEP  {sep:>7.0f}m    TTI  {tti_s:>7}    SPD  {xspd:.0f}m/s\n"
                f"  STATUS  {st}")
        else:
            self._telem_intercept.setText(
                "─ INTERCEPTOR ───────────────────────────\n"
                "  SEP  ---           TTI  ---      SPD  ---\n"
                "  STATUS  STANDBY")

        if radar_return.get("detected"):
            conf = sim_state.get("track_confidence", 0.0)
            snr  = radar_return.get("snr", 0.0)
            self._telem_radar.setText(
                f"─ RADAR ─────────────────────────────────\n"
                f"  CONF  {conf*100:.0f}%         SNR  {snr:.1f}dB\n"
                f"  TRACK  LOCKED        KALMAN  6-STATE")
        else:
            self._telem_radar.setText(
                "─ RADAR ─────────────────────────────────\n"
                "  CONF  ---%          SNR  ---dB\n"
                "  TRACK  SEARCHING     LOCK  PENDING")

        # Threat bar
        if intruder_pos:
            threat = max(0.0, 1.0 - math.sqrt(sum(v**2 for v in intruder_pos))
                         / (2 * self._dome_radius))
        else:
            threat = 0.0
        bar_col = C["primary"] if threat < 0.5 else (C["amber"] if threat < 0.75 else C["red"])
        self._threat_bar.setValue(int(threat * 100))
        self._threat_bar.setStyleSheet(
            f"QProgressBar {{ background-color: {C['dim']}; border: 0px; }}"
            f"QProgressBar::chunk {{ background-color: {bar_col}; }}")
        self._threat_pct.setText(f"{threat*100:.0f}%")
        self._threat_pct.setStyleSheet(f"color: {bar_col}; font-size: 9px;")

    def _show_debrief(self, state: dict) -> None:
        result   = state.get("result", "---")
        sim_time = state.get("sim_time", 0.0)
        closest  = state.get("closest_approach", float("inf"))

        result_col  = {"INTERCEPTED": C["primary"], "FAILURE": C["red"],
                       "TIMEOUT": C["amber"], "ABORTED": C["textdim"]}
        result_icon = {"INTERCEPTED": "★  INTERCEPTED  ★",
                       "FAILURE":     "✗  BREACH — FAILURE  ✗",
                       "TIMEOUT":     "⏱  TIME EXPIRED  ⏱",
                       "ABORTED":     "■  MISSION ABORTED  ■"}
        col  = result_col.get(result, C["white"])
        icon = result_icon.get(result, f"■  {result}  ■")

        lines = [icon, ""]
        lines.append(f"Duration:      {sim_time:.0f} s")
        if closest < 9999:
            lines.append(f"Closest appr:  {closest:.1f} m")
        lines += ["", "─" * 30, "Click a scenario to continue"]

        self._debrief_text.setText("\n".join(lines))
        self._debrief_text.setColor(QtGui.QColor(col))
        self._debrief_text.setVisible(True)

        self._hdr_status.setText(f"■  {result}")
        self._hdr_status.setStyleSheet(
            f"color: {col}; font-size: 12px; font-weight: bold;")

    def close(self) -> None:                                    # type: ignore[override]
        try:
            self._anim_timer.stop()
            self._fps_timer.stop()
        except Exception:
            pass
        try:
            super().close()
        except Exception:
            pass
