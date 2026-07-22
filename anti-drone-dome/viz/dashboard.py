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
    "bg":      "#111417",
    "panel":   "#181c20",
    "border":  "#30373d",
    "primary": "#4fa66a",
    "dim":     "#252b30",
    "amber":   "#e5b94b",
    "red":     "#e24a4a",
    "blue":    "#4a90e2",
    "cyan":    "#aebbc3",
    "text":    "#d4d9dd",
    "textdim": "#7f8a91",
    "white":   "#f1f3f4",
}

_STATUS_COLOR = {
    "CLEAR":       C["primary"],
    "MONITORING":  C["cyan"],
    "TRACKING":    C["amber"],
    "BREACH":      C["red"],
    "INTERCEPTED": C["primary"],
}

_INTRUDER_LABELS = [
    ("shahed136",     "SHAHED-136"),
    ("consumer_quad", "CONSUMER UAS"),
    ("fpv_attack",    "FPV ATTACK"),
]
_PATTERN_LABELS = [
    ("direct",    "DIRECT"),
    ("nap_earth", "NAP-EARTH"),
    ("spiral",    "SPIRAL"),
    ("crossing",  "CROSSING"),
    ("pop_up",    "POP-UP"),
    ("offset",    "OFFSET"),
]
_SPEEDS = [(0.5, "0.5×"), (1.0, "1×"), (2.0, "2×"), (4.0, "4×"), (8.0, "8×")]
_PADS   = [("near", "NEAR 50m"), ("mid", "MID 180m"), ("far", "FAR 380m")]

TRAIL_PERSISTENCE_S = 6.0    # phosphor decay time
TRAIL_HEAD_SIZE     = 11     # marker size for current-position dot


def _register_dashboard_fonts() -> None:
    """Bundle reliable fonts for native and headless dashboard rendering."""
    try:
        from matplotlib import font_manager

        for family in ("DejaVu Sans", "DejaVu Sans Mono"):
            QtGui.QFontDatabase.addApplicationFont(font_manager.findfont(family))
    except Exception:
        pass


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
        self.runtime_speed       = 1.0
        self.radar_failure       = False
        self.camera_failure      = False
        self.actuator_failure    = False
        self.camera_zoom_pending = None
        self.camera_view_pending = None


# ─────────────────────────────────────────────────────────────────────────────
def _btn_style(fg: str, border: str, base: str, hover: str, sel: str = None) -> str:
    sel = sel or hover
    return f"""
        QPushButton {{
            background-color: {base};
            color: {fg};
            border: 1px solid {border};
            border-radius: 3px;
            font-family: 'DejaVu Sans';
            font-size: 11px;
            font-weight: 600;
            padding: 6px 8px;
        }}
        QPushButton:hover {{ background-color: {hover}; }}
        QPushButton:checked {{ background-color: {sel}; border-color: {fg}; }}
    """


def _altitude_time_window(sim_time: float) -> tuple[float, float, list[tuple[float, str]]]:
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


# ─────────────────────────────────────────────────────────────────────────────
class _FadingTrail:
    """Phosphor-decay PPI trail. Holds (x, y, t_birth) tuples and renders as a
    ScatterPlotItem with per-point alpha that decays linearly to 0 over
    TRAIL_PERSISTENCE_S seconds."""

    def __init__(self, plot_item: pg.PlotItem, color_hex: str,
                 size: int = 4, head_size: int = TRAIL_HEAD_SIZE,
                 head_symbol: str = "s", z_trail: int = 5, z_head: int = 6,
                 persistence_s: float = TRAIL_PERSISTENCE_S):
        self._color   = QtGui.QColor(color_hex)
        self._size    = size
        self._persistence_s = persistence_s
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

    def points(self) -> list[tuple[float, float]]:
        return [(x, y) for x, y, _ in self._buf]

    def hide(self) -> None:
        self._scatter.setData([])
        self._head.setData([])

    def render(self, now: float) -> None:
        if not self._buf:
            self._scatter.setData([])
            self._head.setData([])
            return

        # drop expired
        while self._buf and (now - self._buf[0][2]) > self._persistence_s:
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
            alpha = max(0, min(255, int(255 * (1.0 - age / self._persistence_s))))
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


class _ThreatMeter(QtWidgets.QWidget):
    """Platform-independent three-zone meter with a precise current-value marker."""

    def __init__(self):
        super().__init__()
        self._value = 0
        self.setFixedHeight(16)

    def setValue(self, value: int) -> None:
        self._value = max(0, min(100, int(value)))
        self.update()

    def paintEvent(self, event):  # type: ignore[override]
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing, False)
        rect = self.rect().adjusted(0, 5, -1, -4)
        monitor_width = int(rect.width() * 0.5)
        caution_width = int(rect.width() * 0.25)
        painter.fillRect(
            QtCore.QRect(rect.left(), rect.top(), monitor_width, rect.height()),
            QtGui.QColor(C["primary"]),
        )
        painter.fillRect(
            QtCore.QRect(
                rect.left() + monitor_width,
                rect.top(),
                caution_width,
                rect.height(),
            ),
            QtGui.QColor(C["amber"]),
        )
        painter.fillRect(
            QtCore.QRect(
                rect.left() + monitor_width + caution_width,
                rect.top(),
                rect.width() - monitor_width - caution_width,
                rect.height(),
            ),
            QtGui.QColor(C["red"]),
        )
        marker_x = rect.left() + int(rect.width() * self._value / 100.0)
        painter.setPen(QtGui.QPen(QtGui.QColor(C["white"]), 2))
        painter.drawLine(marker_x, rect.top() - 3, marker_x, rect.bottom() + 3)
        painter.end()


# ───────────────────────────────────────────────────────────────────────────
class Dashboard(QtWidgets.QMainWindow):
    """PyQtGraph C-UAS C2 dashboard. Public API matches legacy matplotlib version."""

    def __init__(self, dome_radius: float = 200.0, sim_control: SimControl = None):
        super().__init__()
        _register_dashboard_fonts()
        self._dome_radius     = float(dome_radius)
        self._view            = self._dome_radius * 4.0
        self._ctrl            = sim_control or SimControl()
        self._event_log: list[tuple[str, str, float]] = []
        self._last_status: str | None = None
        self._radar_angle     = 0.0
        self._t_start_wall    = time.time()
        self._last_blink      = time.time()
        self._blink_state     = False
        self._mission_active  = False
        self._last_trail_render = 0.0
        self._last_sim_speed = 1.0
        self._last_real_time_factor = 0.0
        self._video_update_times: deque[float] = deque(maxlen=120)

        # ── Window chrome ─────────────────────────────────────────────────
        self.setWindowTitle("AEGIS  —  INTEGRATED AIRSPACE PROTECTION")
        self.resize(1680, 950)
        self.setStyleSheet(f"""
            QMainWindow, QWidget {{ background-color: {C['bg']}; }}
            QLabel {{ color: {C['text']}; font-family: 'DejaVu Sans'; }}
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
        self._build_timeline(root)
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

        title = QtWidgets.QLabel("AEGIS  /  INTEGRATED AIRSPACE PROTECTION")
        title.setStyleSheet(f"color: {C['white']}; font-size: 15px; font-weight: 700;")
        sub = QtWidgets.QLabel("CRITICAL INFRASTRUCTURE DEFENSE  ·  COMMON OPERATING PICTURE")
        sub.setStyleSheet(f"color: {C['textdim']}; font-size: 9px; letter-spacing: 1px;")
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
        """Layout: [operational map] | [live 3-D / altitude] | [system status]."""
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

        self._video_frame = QtWidgets.QFrame()
        self._video_frame.setStyleSheet(
            f"QFrame {{ background-color: #05090d; border: 1px solid {C['border']}; }}"
        )
        video_layout = QtWidgets.QVBoxLayout(self._video_frame)
        video_layout.setContentsMargins(0, 0, 0, 0)
        video_layout.setSpacing(0)
        video_header = QtWidgets.QFrame()
        video_header.setFixedHeight(32)
        video_header.setStyleSheet(f"background-color: {C['panel']};")
        video_header_layout = QtWidgets.QHBoxLayout(video_header)
        video_header_layout.setContentsMargins(8, 2, 6, 2)
        video_header_layout.setSpacing(4)
        self._video_title = QtWidgets.QLabel(
            "TACTICAL 3-D  /  OVERVIEW  /  PYBULLET 3-D PREVIEW"
        )
        self._video_title.setStyleSheet(
            f"color: {C['cyan']}; background-color: {C['panel']}; "
            "font-size: 10px; font-weight: 700; letter-spacing: 1px;"
        )
        video_header_layout.addWidget(self._video_title, 1)
        self._view_btns = {}
        for key, label in (
            ("overview", "OVERVIEW"),
            ("shahed", "SHAHED TRACK"),
            ("interceptor", "INTERCEPTOR CHASE"),
            ("topdown", "TOP DOWN"),
        ):
            button = QtWidgets.QPushButton(label)
            button.setCheckable(True)
            button.setChecked(key == "overview")
            button.setFixedHeight(23)
            button.setStyleSheet(
                _btn_style(C["cyan"], C["border"], "#09131b", "#112635", "#46515a")
                + "QPushButton { font-size: 8px; padding: 2px 7px; }"
            )
            button.clicked.connect(lambda _, mode=key: self._on_camera_view(mode))
            self._view_btns[key] = button
            video_header_layout.addWidget(button)
        self._video = QtWidgets.QLabel("WAITING FOR MISSION TELEMETRY")
        self._video.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self._video.setMinimumSize(560, 315)
        self._video.setStyleSheet(
            f"color: {C['textdim']}; background-color: #05090d; "
            "font-size: 11px; letter-spacing: 1px;"
        )
        self._video.setScaledContents(False)
        video_layout.addWidget(video_header)
        video_layout.addWidget(self._video, 1)

        # Right: telemetry panel (Qt widget — crisp text)
        self._telem_panel = self._build_telem_panel()
        self._telem_panel.setMinimumWidth(305)

        center_col = QtWidgets.QWidget()
        center_v = QtWidgets.QVBoxLayout(center_col)
        center_v.setContentsMargins(0, 0, 0, 0); center_v.setSpacing(4)
        center_v.addWidget(self._video_frame, stretch=7)
        center_v.addWidget(self._gw_side, stretch=3)

        # Horizontal split: operational map | 3-D site | prioritized status
        split = QtWidgets.QSplitter(QtCore.Qt.Orientation.Horizontal)
        split.addWidget(self._gw_radar)
        split.addWidget(center_col)
        split.addWidget(self._telem_panel)
        split.setStretchFactor(0, 6)
        split.setStretchFactor(1, 12)
        split.setStretchFactor(2, 5)
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
        ax.setTitle('<span style="color:#aebbc3; font-family:DejaVu Sans;">'
                    'COMMON OPERATING PICTURE  ·  LOCAL ENU</span>', size="9pt")
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
            (R*0.50, C["dim"],     0.6, None,              False),
            (R,      C["textdim"], 1.4, f"{R:.0f}m  DOME", True),
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
                label_angle = math.radians(35.0)
                t.setPos(
                    r * math.cos(label_angle) + v * 0.008,
                    r * math.sin(label_angle),
                )
                font = QtGui.QFont("DejaVu Sans Mono", 7)
                t.setFont(font)
                ax.addItem(t)

        # Cardinal labels
        for x, y, txt in [(0, v*0.93, "N"), (0, -v*0.93, "S"),
                          (v*0.93, 0, "E"), (-v*0.93, 0, "W")]:
            t = pg.TextItem(text=txt, color=C["textdim"], anchor=(0.5, 0.5))
            t.setFont(QtGui.QFont("DejaVu Sans Mono", 8, QtGui.QFont.Weight.Bold))
            t.setPos(x, y); ax.addItem(t)

    def _setup_side_ax(self, ax: pg.PlotItem) -> None:
        R = self._dome_radius
        ax.setXRange(0, 120, padding=0)
        ax.setYRange(-R*0.05, R*1.8, padding=0)
        ax.setMouseEnabled(x=False, y=False)
        ax.setMenuEnabled(False)
        ax.setTitle('<span style="color:#aebbc3; font-family:DejaVu Sans;">'
                    'ALTITUDE HISTORY  /  MISSION TIME</span>', size="9pt")
        ax.showAxis("bottom")
        ax.getAxis("bottom").setTicks([_altitude_time_window(0.0)[2]])
        ax.getAxis("bottom").setTextPen(pg.mkPen(QtGui.QColor(C["textdim"])))
        ax.getAxis("bottom").setPen(pg.mkPen(QtGui.QColor(C["border"])))
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
        self._dome_arc = ax.plot(
            [0, 120], [R, R],
            pen=pg.mkPen(
                QtGui.QColor(C["textdim"]),
                width=1.0,
                style=QtCore.Qt.PenStyle.DashLine,
            ),
        )
        self._dome_base = ax.plot(
            [0, 120], [0, 0],
            pen=pg.mkPen(QtGui.QColor(C["border"]), width=1.0),
        )

    # ── Telemetry panel (Qt widget — crisp text) ──────────────────────────
    def _build_telem_panel(self) -> QtWidgets.QWidget:
        frame = QtWidgets.QFrame()
        frame.setObjectName("telemetryPanel")
        frame.setStyleSheet(
            f"QFrame#telemetryPanel {{ background-color: {C['panel']}; "
            f"border: 1px solid {C['border']}; }}"
            f"QLabel {{ font-family: 'DejaVu Sans'; font-size: 10px; }}")
        v = QtWidgets.QVBoxLayout(frame)
        v.setContentsMargins(8, 6, 8, 6); v.setSpacing(3)

        role = QtWidgets.QLabel("MISSION  /  PROTECT CRITICAL SITE")
        role.setStyleSheet(
            f"color: {C['white']}; font-size: 11px; font-weight: 700; "
            f"padding: 7px; background-color: {C['dim']};"
        )
        v.addWidget(role)

        decision = QtWidgets.QFrame()
        decision.setObjectName("decisionCard")
        decision.setStyleSheet(
            f"QFrame#decisionCard {{ background-color: #20252a; border: 0px; "
            f"border-left: 3px solid {C['amber']}; }}"
        )
        decision_layout = QtWidgets.QVBoxLayout(decision)
        decision_layout.setContentsMargins(9, 7, 9, 7)
        decision_layout.setSpacing(3)
        decision_title = QtWidgets.QLabel("ENGAGEMENT PRIORITY")
        decision_title.setStyleSheet(
            f"color: {C['textdim']}; font-size: 8px; font-weight: 600; "
            "letter-spacing: 1px;"
        )
        self._decision_values = QtWidgets.QLabel("RANGE  --- m     TTI  --- s")
        self._decision_values.setStyleSheet(
            f"color: {C['white']}; font-family: 'DejaVu Sans Mono'; "
            "font-size: 17px; font-weight: 700;"
        )
        self._threat_bar = _ThreatMeter()
        self._threat_bar.setValue(0)
        zones = QtWidgets.QHBoxLayout()
        for text, color, alignment in (
            ("MONITOR", C["primary"], QtCore.Qt.AlignmentFlag.AlignLeft),
            ("CAUTION", C["amber"], QtCore.Qt.AlignmentFlag.AlignCenter),
            ("CRITICAL", C["red"], QtCore.Qt.AlignmentFlag.AlignRight),
        ):
            label = QtWidgets.QLabel(text)
            label.setAlignment(alignment)
            label.setStyleSheet(
                f"color: {color}; font-size: 7px; font-weight: 600;"
            )
            zones.addWidget(label, 1)
        self._threat_pct = QtWidgets.QLabel("THREAT INDEX  0%")
        self._threat_pct.setStyleSheet(
            f"color: {C['text']}; font-size: 8px; font-weight: 600;"
        )
        decision_layout.addWidget(decision_title)
        decision_layout.addWidget(self._decision_values)
        decision_layout.addWidget(self._threat_bar)
        decision_layout.addLayout(zones)
        decision_layout.addWidget(self._threat_pct)
        v.addWidget(decision)

        self._telem_fusion = QtWidgets.QLabel(
            "FUSED TRACK\n"
            "  ID  TRK-001       SOURCE  SEARCHING\n"
            "  CONF  ---         GUIDANCE  STANDBY")
        self._telem_fusion.setStyleSheet(
            f"color: {C['text']}; padding-top: 6px; "
            "font-family: 'DejaVu Sans Mono'; font-size: 9px;"
        )
        v.addWidget(self._telem_fusion)

        self._telem_intruder = QtWidgets.QLabel(
            "─ INTRUDER ──────────────────────────────\n"
            "  RNG  ---        ALT  ---        SPD  ---\n"
            "  BRG  ---        TYPE  ─────────────────")
        self._telem_intruder.setStyleSheet(
            f"color: {C['red']}; font-family: 'DejaVu Sans Mono'; font-size: 9px;"
        )
        v.addWidget(self._telem_intruder)

        self._telem_intercept = QtWidgets.QLabel(
            "─ INTERCEPTOR ───────────────────────────\n"
            "  SEP  ---        TTI  ---     SPD  ---\n"
            "  STATUS  STANDBY")
        self._telem_intercept.setStyleSheet(
            f"color: {C['blue']}; font-family: 'DejaVu Sans Mono'; font-size: 9px;"
        )
        v.addWidget(self._telem_intercept)

        self._telem_radar = QtWidgets.QLabel(
            "─ RADAR ─────────────────────────────────\n"
            "  CONF  ---%       SNR  ---dB\n"
            "  TRACK  SEARCHING    LOCK  PENDING")
        self._telem_radar.setStyleSheet(
            f"color: {C['primary']}; font-family: 'DejaVu Sans Mono'; font-size: 9px;"
        )
        v.addWidget(self._telem_radar)

        self._telem_environment = QtWidgets.QLabel(
            "SITE & ENVIRONMENT\n"
            "  SITE  SOUTHERN ONTARIO TRAINING SITE\n"
            "  WEATHER  ---      VIS  ---")
        self._telem_environment.setStyleSheet(
            f"color: {C['textdim']}; padding-top: 6px; "
            "font-family: 'DejaVu Sans Mono'; font-size: 8px;"
        )
        v.addWidget(self._telem_environment)

        self._telem_recording = QtWidgets.QLabel(
            "MISSION DATA\n"
            "  REC  ARMED       ACMI  READY\n"
            "  BUS  LOCAL IPC   MODEL  APN")
        self._telem_recording.setStyleSheet(
            f"color: {C['amber']}; padding-top: 6px; "
            "font-family: 'DejaVu Sans Mono'; font-size: 8px;"
        )
        v.addWidget(self._telem_recording)
        v.addStretch(1)

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
            f"font-family: 'DejaVu Sans Mono';")
        h.addWidget(head); h.addWidget(self._log_text, 1)
        root.addWidget(bar)

    def _build_timeline(self, root: QtWidgets.QVBoxLayout) -> None:
        bar = QtWidgets.QFrame()
        bar.setFixedHeight(30)
        bar.setStyleSheet(
            f"QFrame {{ background-color: {C['panel']}; border: 1px solid {C['border']}; }}"
        )
        h = QtWidgets.QHBoxLayout(bar)
        h.setContentsMargins(8, 3, 8, 3)
        h.setSpacing(8)
        self._record_badge = QtWidgets.QLabel("● REC  ACMI + TELEMETRY")
        self._record_badge.setFixedWidth(150)
        self._record_badge.setStyleSheet(
            f"color: {C['red']}; font-size: 8px; font-weight: 700;"
        )
        self._timeline = QtWidgets.QProgressBar()
        self._timeline.setRange(0, 1200)
        self._timeline.setValue(0)
        self._timeline.setFormat("LIVE  T+00:00  /  02:00")
        self._timeline.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self._timeline.setStyleSheet(
            f"QProgressBar {{ background: #08131b; color: {C['text']}; "
            f"border: 0; font-size: 8px; }}"
            f"QProgressBar::chunk {{ background: {C['dim']}; }}"
        )
        self._timeline_state = QtWidgets.QLabel("LIVE")
        self._timeline_state.setFixedWidth(70)
        self._timeline_state.setAlignment(QtCore.Qt.AlignmentFlag.AlignRight)
        self._timeline_state.setStyleSheet(
            f"color: {C['primary']}; font-size: 8px; font-weight: 700;"
        )
        h.addWidget(self._record_badge)
        h.addWidget(self._timeline, 1)
        h.addWidget(self._timeline_state)
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
                C["text"], C["border"], C["bg"], C["dim"], "#46515a"))
            b.clicked.connect(lambda _, k=key: self._on_mission(k))
            self._mission_btns[key] = b
            grid.addWidget(b, 0, i)

        self._speed_btns: dict[float, QtWidgets.QPushButton] = {}
        for i, (spd, lbl) in enumerate(_SPEEDS):
            b = QtWidgets.QPushButton(lbl)
            b.setCheckable(True); b.setChecked(spd == 1.0)
            b.setStyleSheet(_btn_style(
                C["text"], C["border"], C["bg"], C["dim"], "#46515a"))
            b.clicked.connect(lambda _, s=spd: self._on_speed_select(s))
            self._speed_btns[spd] = b
            grid.addWidget(b, 0, 4 + i)

        # Row 1: 3 patterns + 3 pads + hint
        self._pattern_btns: dict[str, QtWidgets.QPushButton] = {}
        for i, (key, lbl) in enumerate(_PATTERN_LABELS):
            b = QtWidgets.QPushButton(lbl)
            b.setCheckable(True); b.setChecked(key == "direct")
            b.setStyleSheet(_btn_style(
                C["text"], C["border"], C["bg"], C["dim"], "#46515a"))
            b.clicked.connect(lambda _, k=key: self._on_pattern_select(k))
            self._pattern_btns[key] = b
            grid.addWidget(b, 1, i)

        self._pad_btns: dict[str, QtWidgets.QPushButton] = {}
        for i, (key, lbl) in enumerate(_PADS):
            b = QtWidgets.QPushButton(lbl)
            b.setCheckable(True); b.setChecked(key == "mid")
            b.setStyleSheet(_btn_style(
                C["text"], C["border"], C["bg"], C["dim"], "#46515a"))
            b.clicked.connect(lambda _, k=key: self._on_pad_select(k))
            self._pad_btns[key] = b
            grid.addWidget(b, 1, 7 + i)

        hint = QtWidgets.QLabel(
            "Select intruder · pattern · pad · speed\n"
            "then  ▶ START  to launch the 3-D sim")
        hint.setStyleSheet(
            f"color: {C['textdim']}; font-size: 8px; "
            f"font-family: 'DejaVu Sans Mono';")
        hint.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        grid.addWidget(hint, 1, 10, 1, 3)

        # Even column stretch
        for c in range(13):
            grid.setColumnStretch(c, 1)
        self._mission_panel = frame
        root.addWidget(frame, stretch=3)

    # ── Controls row ──────────────────────────────────────────────────────
    def _build_controls_row(self, root: QtWidgets.QVBoxLayout) -> None:
        bar = QtWidgets.QFrame()
        bar.setFixedHeight(46)
        bar.setStyleSheet(f"QFrame {{ background-color: {C['bg']}; }}")
        h = QtWidgets.QHBoxLayout(bar)
        h.setContentsMargins(2, 4, 2, 2); h.setSpacing(6)

        self._btn_pause = QtWidgets.QPushButton("PAUSE")
        self._btn_reset = QtWidgets.QPushButton("RESET")
        self._btn_start = QtWidgets.QPushButton("START")
        self._btn_abort = QtWidgets.QPushButton("ABORT")
        self._btn_radar_fail = QtWidgets.QPushButton("RADAR FAIL")
        self._btn_camera_fail = QtWidgets.QPushButton("EO FAIL")
        self._btn_actuator_fail = QtWidgets.QPushButton("ACT FAIL")
        sep_lbl  = QtWidgets.QLabel("3-D CAM")
        sep_lbl.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        sep_lbl.setStyleSheet(f"color: {C['textdim']}; font-size: 8px;")
        self._btn_zoom_in  = QtWidgets.QPushButton("+")
        self._btn_zoom_out = QtWidgets.QPushButton("−")

        self._btn_pause.setStyleSheet(_btn_style(C["primary"], C["primary"], "#0a1808", "#112010"))
        self._btn_reset.setStyleSheet(_btn_style(C["amber"],   C["amber"],   "#141008", "#201808"))
        self._btn_start.setStyleSheet(_btn_style(C["white"],   C["primary"], "#0d2010", "#163015"))
        self._btn_abort.setStyleSheet(_btn_style(C["red"],     C["red"],     "#1e0508", "#2e0810"))
        for button in (
            self._btn_radar_fail,
            self._btn_camera_fail,
            self._btn_actuator_fail,
        ):
            button.setCheckable(True)
            button.setStyleSheet(
                _btn_style(C["amber"], C["amber"], "#141008", "#201808", "#5a2108")
            )
        self._btn_zoom_in.setStyleSheet(
            _btn_style(C["text"], C["border"], C["bg"], C["dim"])
        )
        self._btn_zoom_out.setStyleSheet(
            _btn_style(C["text"], C["border"], C["bg"], C["dim"])
        )

        for w, s in ((self._btn_pause, 3), (self._btn_reset, 3),
                     (self._btn_start, 3), (self._btn_abort, 3),
                     (self._btn_radar_fail, 2), (self._btn_camera_fail, 2),
                     (self._btn_actuator_fail, 2),
                     (sep_lbl, 1), (self._btn_zoom_in, 1), (self._btn_zoom_out, 1)):
            h.addWidget(w, stretch=s)

        self._btn_pause.clicked.connect(self._on_pause)
        self._btn_reset.clicked.connect(self._on_reset)
        self._btn_start.clicked.connect(self._on_start)
        self._btn_abort.clicked.connect(self._on_abort)
        self._btn_radar_fail.toggled.connect(
            lambda checked: setattr(self._ctrl, "radar_failure", checked)
        )
        self._btn_camera_fail.toggled.connect(
            lambda checked: setattr(self._ctrl, "camera_failure", checked)
        )
        self._btn_actuator_fail.toggled.connect(
            lambda checked: setattr(self._ctrl, "actuator_failure", checked)
        )
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
        self._intruder_ppi   = _FadingTrail(
            ax, C["red"], size=4, head_size=11, head_symbol="s"
        )
        self._intercept_ppi  = _FadingTrail(
            ax, C["blue"], size=4, head_size=11, head_symbol="s"
        )

        # Prediction line + cross
        self._pred_line = ax.plot([], [], pen=pg.mkPen(
            QtGui.QColor(C["white"]), width=1.2,
            style=QtCore.Qt.PenStyle.DashLine))
        self._pred_dot = pg.ScatterPlotItem(
            size=12, symbol="x",
            pen=pg.mkPen(QtGui.QColor(C["white"]), width=2),
            brush=None)
        ax.addItem(self._pred_dot)

        self._intruder_vector = ax.plot(
            [], [], pen=pg.mkPen(QtGui.QColor(C["red"]), width=1.2)
        )
        self._interceptor_vector = ax.plot(
            [], [], pen=pg.mkPen(QtGui.QColor(C["blue"]), width=1.2)
        )
        self._intruder_leader = ax.plot(
            [], [], pen=pg.mkPen(QtGui.QColor(C["red"]), width=0.8)
        )
        self._interceptor_leader = ax.plot(
            [], [], pen=pg.mkPen(QtGui.QColor(C["blue"]), width=0.8)
        )
        self._intruder_label = pg.TextItem(
            text="TRK-001", color=C["red"], anchor=(0, 1),
            border=pg.mkPen(QtGui.QColor(C["red"])),
            fill=pg.mkBrush(QtGui.QColor(7, 16, 24, 220)),
        )
        self._interceptor_label = pg.TextItem(
            text="INT-01", color=C["blue"], anchor=(0, 1),
            border=pg.mkPen(QtGui.QColor(C["blue"])),
            fill=pg.mkBrush(QtGui.QColor(7, 16, 24, 220)),
        )
        self._intruder_label.setFont(QtGui.QFont("DejaVu Sans Mono", 7))
        self._interceptor_label.setFont(QtGui.QFont("DejaVu Sans Mono", 7))
        ax.addItem(self._intruder_label)
        ax.addItem(self._interceptor_label)
        self._intruder_label.setVisible(False)
        self._interceptor_label.setVisible(False)

        # Status badge
        self._status_badge = pg.TextItem(
            text="●  STATUS: STANDBY",
            color=C["primary"], anchor=(0, 0),
            border=pg.mkPen(QtGui.QColor(C["border"])),
            fill=pg.mkBrush(QtGui.QColor(C["panel"])))
        self._status_badge.setFont(QtGui.QFont("DejaVu Sans Mono", 9, QtGui.QFont.Weight.Bold))
        self._status_badge.setPos(-self._view*0.96, self._view*0.93)
        ax.addItem(self._status_badge)

        # PAUSED overlay
        self._paused_text = pg.TextItem(
            text="── PAUSED ──", color=C["amber"], anchor=(0.5, 0.5),
            border=pg.mkPen(QtGui.QColor(C["amber"])),
            fill=pg.mkBrush(QtGui.QColor(C["bg"])))
        self._paused_text.setFont(QtGui.QFont("DejaVu Sans", 18, QtGui.QFont.Weight.Bold))
        self._paused_text.setPos(0, 0)
        self._paused_text.setVisible(False)
        ax.addItem(self._paused_text)

        # Debrief overlay
        self._debrief_text = pg.TextItem(
            text="", color=C["primary"], anchor=(0.5, 0.5),
            border=pg.mkPen(QtGui.QColor(C["primary"])),
            fill=pg.mkBrush(QtGui.QColor("#020a04")))
        self._debrief_text.setFont(QtGui.QFont("DejaVu Sans Mono", 11, QtGui.QFont.Weight.Bold))
        self._debrief_text.setPos(0, 0)
        self._debrief_text.setVisible(False)
        ax.addItem(self._debrief_text)

        # Altitude trails
        self._intruder_alt = _FadingTrail(
            self._ax_side,
            C["red"],
            size=4,
            head_size=10,
            head_symbol="s",
            persistence_s=120.0,
        )
        self._intercept_alt = _FadingTrail(
            self._ax_side,
            C["blue"],
            size=4,
            head_size=10,
            head_symbol="s",
            persistence_s=120.0,
        )

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
        if now - self._last_trail_render >= 1.0 / 15.0:
            self._intruder_ppi.render(now)
            self._intercept_ppi.render(now)
            self._intruder_alt.render(now)
            self._intercept_alt.render(now)
            self._last_trail_render = now

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
        video_hz = 0.0
        video_times = self._video_update_times
        if (
            len(video_times) >= 2
            and time.perf_counter() - video_times[-1] <= 2.0
        ):
            video_span = video_times[-1] - video_times[0]
            if video_span > 0:
                video_hz = (len(video_times) - 1) / video_span
        self._hdr_speed.setText(
            f"SIM {self._last_sim_speed:.2g}×  RTF {self._last_real_time_factor:.2f}  "
            f"UI {fps:3.0f}Hz  VIDEO {video_hz:3.0f}Hz"
        )

    # ── Button callbacks ──────────────────────────────────────────────────
    def _on_pause(self):
        self._ctrl.paused = not self._ctrl.paused
        self._btn_pause.setText("RESUME" if self._ctrl.paused else "PAUSE")

    def _on_reset(self):
        self._ctrl.restart = True

    def _on_abort(self):
        self._ctrl.stopped = True
        self._btn_abort.setText("ABORTED")

    def _on_zoom(self, direction: str):
        self._ctrl.camera_zoom_pending = direction

    def _on_camera_view(self, mode: str):
        self._ctrl.camera_view_pending = mode
        for key, button in self._view_btns.items():
            button.setChecked(key == mode)
        titles = {
            "overview": "TACTICAL 3-D  /  OVERVIEW  /  PYBULLET 3-D PREVIEW",
            "shahed": "THREAT CHASE  /  SHAHED-136  /  PYBULLET 3-D PREVIEW",
            "interceptor": "INTERCEPTOR CHASE  /  PYBULLET 3-D PREVIEW",
            "topdown": "TACTICAL 3-D  /  NADIR  /  PYBULLET 3-D PREVIEW",
        }
        self._video_title.setText(titles.get(mode, titles["overview"]))

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
        self._ctrl.runtime_speed = speed
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
        self._last_status = None
        self._intruder_vector.setData([], [])
        self._interceptor_vector.setData([], [])
        self._intruder_leader.setData([], [])
        self._interceptor_leader.setData([], [])
        self._intruder_label.setVisible(False)
        self._interceptor_label.setVisible(False)

    def _reset_buttons(self):
        self._ctrl.stopped = False
        self._ctrl.restart = False
        self._ctrl.paused  = False
        self._btn_abort.setText("ABORT")
        self._btn_pause.setText("PAUSE")

    def _render_tactical_frame(self, frame: np.ndarray, sim_state: dict) -> None:
        frame = np.ascontiguousarray(frame)
        height, width = frame.shape[:2]
        image = QtGui.QImage(
            frame.data,
            width,
            height,
            frame.strides[0],
            QtGui.QImage.Format.Format_RGB888,
        ).copy()
        overlay = sim_state.get("tactical_overlay", {}) or {}
        points = overlay.get("screen_points", {}) or {}
        painter = QtGui.QPainter(image)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        painter.setFont(QtGui.QFont("DejaVu Sans Mono", 8, QtGui.QFont.Weight.Bold))

        mode = overlay.get("view_mode", "overview")
        if mode in ("shahed", "interceptor"):
            center = QtCore.QPointF(width / 2, height / 2)
            painter.setPen(QtGui.QPen(QtGui.QColor(C["textdim"]), 1))
            painter.drawLine(
                QtCore.QPointF(center.x() - 18, center.y()),
                QtCore.QPointF(center.x() - 5, center.y()),
            )
            painter.drawLine(
                QtCore.QPointF(center.x() + 5, center.y()),
                QtCore.QPointF(center.x() + 18, center.y()),
            )
            painter.drawLine(
                QtCore.QPointF(center.x(), center.y() - 18),
                QtCore.QPointF(center.x(), center.y() - 5),
            )
            painter.drawLine(
                QtCore.QPointF(center.x(), center.y() + 5),
                QtCore.QPointF(center.x(), center.y() + 18),
            )

        intruder_pos = sim_state.get("intruder_pos")
        interceptor_pos = sim_state.get("interceptor_pos")
        labels = {
            "intruder": (
                C["red"],
                "TRK-001  SHAHED-136",
                f"ALT {intruder_pos[2]:.0f}m  SPD {sim_state.get('intruder_speed', 0):.0f}m/s"
                if intruder_pos else "",
            ),
            "interceptor": (
                C["blue"],
                "INT-01  C-UAS INTERCEPTOR",
                f"ALT {interceptor_pos[2]:.0f}m  SPD {sim_state.get('interceptor_speed', 0):.0f}m/s"
                if interceptor_pos else "",
            ),
            "predicted_intercept": (C["white"], "PREDICTED INTERCEPT", ""),
        }
        occupied_labels: list[QtCore.QRectF] = []
        placed_labels = []
        for key in ("intruder", "interceptor", "predicted_intercept"):
            if (mode == "shahed" and key == "intruder") or (
                mode == "interceptor" and key == "interceptor"
            ):
                continue
            point = points.get(key)
            if not point or key not in labels:
                continue
            color, title, detail = labels[key]
            x, y = point
            text_x = min(x + 26.0, width - 180.0)
            text_y = max(16.0, y - 28.0)
            label_height = 28.0 if detail else 16.0
            label_rect = QtCore.QRectF(
                text_x - 3, text_y - 11, 176, label_height
            )
            while any(label_rect.intersects(existing) for existing in occupied_labels):
                label_rect.translate(0.0, label_height + 4.0)
                text_y += label_height + 4.0
                if label_rect.bottom() > height - 4.0:
                    label_rect.moveTop(4.0)
                    text_y = 15.0
                    break
            occupied_labels.append(label_rect)
            placed_labels.append((key, x, y, color, title, detail, label_rect))

        for key, x, y, color, title, detail, label_rect in placed_labels:
            painter.setPen(QtGui.QPen(QtGui.QColor(color), 1.5))
            painter.setBrush(QtCore.Qt.BrushStyle.NoBrush)
            if key == "predicted_intercept":
                size = 9.0
                painter.drawLine(
                    QtCore.QPointF(x - size, y - size),
                    QtCore.QPointF(x + size, y + size),
                )
                painter.drawLine(
                    QtCore.QPointF(x - size, y + size),
                    QtCore.QPointF(x + size, y - size),
                )
            else:
                size = 14.0
                corner = 5.0
                for sx, sy in ((-1.0, -1.0), (1.0, -1.0), (-1.0, 1.0), (1.0, 1.0)):
                    corner_x = x + sx * size
                    corner_y = y + sy * size
                    painter.drawLine(
                        QtCore.QPointF(corner_x, corner_y),
                        QtCore.QPointF(corner_x - sx * corner, corner_y),
                    )
                    painter.drawLine(
                        QtCore.QPointF(corner_x, corner_y),
                        QtCore.QPointF(corner_x, corner_y - sy * corner),
                    )
            painter.setBrush(QtGui.QBrush(QtGui.QColor(color)))
            painter.drawEllipse(QtCore.QPointF(x, y), 2.5, 2.5)
            leader_end = QtCore.QPointF(label_rect.left(), label_rect.center().y())
            painter.drawLine(QtCore.QPointF(x + 3.0, y - 3.0), leader_end)
            painter.fillRect(label_rect, QtGui.QColor(17, 20, 23, 235))
            painter.setBrush(QtCore.Qt.BrushStyle.NoBrush)
            painter.drawRect(label_rect)
            text_x = label_rect.left() + 3.0
            text_y = label_rect.top() + 11.0
            painter.drawText(QtCore.QPointF(text_x, text_y), title)
            if detail:
                painter.setFont(QtGui.QFont("DejaVu Sans Mono", 7))
                painter.drawText(QtCore.QPointF(text_x, text_y + 12), detail)
                painter.setFont(
                    QtGui.QFont("DejaVu Sans Mono", 8, QtGui.QFont.Weight.Bold)
                )

        intruder_screen = points.get("intruder")
        intercept_screen = points.get("predicted_intercept")
        if intruder_screen and intercept_screen:
            painter.setPen(
                QtGui.QPen(
                    QtGui.QColor(C["white"]),
                    1,
                    QtCore.Qt.PenStyle.DashLine,
                )
            )
            painter.drawLine(
                QtCore.QPointF(*intruder_screen),
                QtCore.QPointF(*intercept_screen),
            )
        painter.end()
        pixmap = QtGui.QPixmap.fromImage(image)
        self._video.setPixmap(
            pixmap.scaled(
                self._video.size(),
                QtCore.Qt.AspectRatioMode.KeepAspectRatio,
                QtCore.Qt.TransformationMode.SmoothTransformation,
            )
        )

    # ── Main update entry point ───────────────────────────────────────────
    def update(self, sim_state: dict) -> None:                  # noqa: C901
        msg_type = sim_state.get("type")

        if msg_type == "mission_start":
            self._clear_trails()
            self._event_log.append(("Mission recording started", "CLEAR", 0.0))
            self._debrief_text.setVisible(False)
            self._reset_buttons()
            self._video.clear()
            self._video.setText("INITIALIZING PHYSICS, MAP, AND SENSOR FUSION")
            self._mission_active = True
            self._mission_panel.setVisible(False)
            self._timeline_state.setText("LIVE")
            self._record_badge.setText("● REC  ACMI + TELEMETRY")
            return
        if msg_type in ("reset", "show_menu"):
            self._clear_trails()
            self._debrief_text.setVisible(False)
            self._mission_active = False
            self._mission_panel.setVisible(True)
            return
        if msg_type == "debrief":
            self._show_debrief(sim_state)
            return

        now = time.time()
        status          = sim_state.get("dome_status", "CLEAR")
        intruder_pos    = sim_state.get("intruder_pos")
        interceptor_pos = sim_state.get("interceptor_pos")
        radar_return    = sim_state.get("radar_return", {}) or {}
        camera_return   = sim_state.get("camera_return", {}) or {}
        fused_track     = sim_state.get("fused_track", {}) or {}
        predicted_ic    = sim_state.get("predicted_intercept")
        events          = sim_state.get("events", []) or []
        sim_time        = sim_state.get("mission_time", 0.0)
        sim_speed       = sim_state.get("sim_speed", 1.0)
        self._radar_station = sim_state.get("radar_station", [0, 0, 0])

        camera_frame = sim_state.get("camera_frame")
        if camera_frame is not None:
            self._video_update_times.append(time.perf_counter())
            self._render_tactical_frame(camera_frame, sim_state)

        if self._last_status != status:
            transition_event = {
                "MONITORING": "Track under monitoring",
                "TRACKING": "Engagement zone entered",
                "BREACH": "Protected zone breached",
                "INTERCEPTED": "Intercept confirmed",
            }.get(status)
            if transition_event and not any(
                transition_event.lower() in str(event).lower() for event in events
            ):
                events = [transition_event, *events]
            self._last_status = status
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
        self._timeline.setValue(min(1200, int(sim_time * 10)))
        self._timeline.setFormat(f"LIVE  T+{mins:02d}:{secs:02d}  /  02:00")
        time_start, time_end, time_ticks = _altitude_time_window(sim_time)
        self._ax_side.setXRange(time_start, time_end, padding=0)
        self._ax_side.getAxis("bottom").setTicks([time_ticks])
        self._last_sim_speed = float(sim_speed)
        self._last_real_time_factor = float(
            sim_state.get("real_time_factor", 0.0)
        )

        # ── Event log ─────────────────────────────────────────────────────
        if self._event_log:
            ev_col = {"CLEAR": C["primary"], "MONITORING": C["cyan"],
                      "TRACKING": C["amber"],
                      "BREACH": C["red"],    "INTERCEPTED": C["primary"]}
            parts = []
            for ev, _st, t in self._event_log[-4:]:
                m2 = int(t) // 60; s2 = int(t) % 60
                parts.append(f"[T+{m2:02d}:{s2:02d}]  {ev}")
            self._log_text.setText("   ·   ".join(parts))
            self._log_text.setStyleSheet(
                f"color: {ev_col.get(status, C['textdim'])}; font-size: 9px; "
                f"font-family: 'DejaVu Sans Mono';")

        # ── Dome ring color & altitude arc ────────────────────────────────
        self._dome_circle.setPen(pg.mkPen(QtGui.QColor(C["textdim"]), width=1.2))
        self._dome_arc.setPen(
            pg.mkPen(
                QtGui.QColor(C["textdim"]),
                width=1.0,
                style=QtCore.Qt.PenStyle.DashLine,
            )
        )
        self._dome_base.setPen(pg.mkPen(QtGui.QColor(C["border"]), width=1.0))

        # ── Status badge ──────────────────────────────────────────────────
        self._status_badge.setText(f"●  STATUS: {status}")
        self._status_badge.setColor(QtGui.QColor(dome_fg))

        # ── Intruder trail ────────────────────────────────────────────────
        if intruder_pos:
            self._intruder_ppi.append(intruder_pos[0], intruder_pos[1], now)
            self._intruder_alt.append(sim_time, intruder_pos[2], now)
            intruder_velocity = sim_state.get("intruder_velocity", (0.0, 0.0, 0.0))
            self._intruder_vector.setData(
                [intruder_pos[0], intruder_pos[0] + intruder_velocity[0] * 2.0],
                [intruder_pos[1], intruder_pos[1] + intruder_velocity[1] * 2.0],
            )
            self._intruder_label.setText(
                f"TRK-001 | {sim_state.get('intruder_speed', 0):.0f}m/s | "
                f"{intruder_pos[2]:.0f}m"
            )
            self._intruder_label.setPos(intruder_pos[0] + 12, intruder_pos[1] + 12)
            self._intruder_leader.setData(
                [intruder_pos[0], intruder_pos[0] + 10],
                [intruder_pos[1], intruder_pos[1] + 10],
            )
            self._intruder_label.setVisible(True)
        else:
            self._intruder_ppi.hide(); self._intruder_alt.hide()
            self._intruder_vector.setData([], [])
            self._intruder_leader.setData([], [])
            self._intruder_label.setVisible(False)

        # ── Interceptor trail ─────────────────────────────────────────────
        if interceptor_pos:
            self._intercept_ppi.append(interceptor_pos[0], interceptor_pos[1], now)
            self._intercept_alt.append(sim_time, interceptor_pos[2], now)
            interceptor_velocity = sim_state.get(
                "interceptor_velocity", (0.0, 0.0, 0.0)
            )
            self._interceptor_vector.setData(
                [interceptor_pos[0], interceptor_pos[0] + interceptor_velocity[0] * 1.5],
                [interceptor_pos[1], interceptor_pos[1] + interceptor_velocity[1] * 1.5],
            )
            self._interceptor_label.setText(
                f"INT-01 | {sim_state.get('interceptor_speed', 0):.0f}m/s | "
                f"{interceptor_pos[2]:.0f}m"
            )
            self._interceptor_label.setPos(
                interceptor_pos[0] + 12, interceptor_pos[1] + 12
            )
            self._interceptor_leader.setData(
                [interceptor_pos[0], interceptor_pos[0] + 10],
                [interceptor_pos[1], interceptor_pos[1] + 10],
            )
            self._interceptor_label.setVisible(True)
        else:
            self._intercept_ppi.hide(); self._intercept_alt.hide()
            self._interceptor_vector.setData([], [])
            self._interceptor_leader.setData([], [])
            self._interceptor_label.setVisible(False)

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
            link_margin = radar_return.get(
                "link_margin_db",
                radar_return.get("snr", 0.0),
            )
            self._telem_radar.setText(
                f"─ RADAR ─────────────────────────────────\n"
                f"  CONF  {conf*100:.0f}%      MARGIN  {link_margin:.1f}dB\n"
                f"  TRACK  LOCKED        KALMAN  6-STATE")
        else:
            self._telem_radar.setText(
                "─ RADAR ─────────────────────────────────\n"
                "  CONF  ---%          SNR  ---dB\n"
                "  TRACK  SEARCHING     LOCK  PENDING")

        fusion_source = fused_track.get("source", "SEARCHING")
        fusion_confidence = fused_track.get("confidence", 0.0)
        guidance_mode = sim_state.get("guidance_mode", "STANDBY")
        camera_health = "TRACK" if camera_return.get("detected") else "READY"
        self._telem_fusion.setText(
            "FUSED TRACK\n"
            f"  ID  TRK-001       SOURCE  {fusion_source}\n"
            f"  CONF  {fusion_confidence*100:>3.0f}%        GUIDANCE  {guidance_mode}\n"
            f"  RADAR  {'LOCK' if radar_return.get('detected') else 'SEARCH':<6}     "
            f"EO  {camera_health}"
        )
        environment_name = sim_state.get("environment_name", "---").replace("_", " ").upper()
        site_name = sim_state.get("site_name", "---").upper()
        visibility = sim_state.get("visibility_m", 0.0)
        wind = sim_state.get("wind_mps", (0.0, 0.0, 0.0))
        wind_speed = math.sqrt(sum(float(value) ** 2 for value in wind))
        self._telem_environment.setText(
            "SITE & ENVIRONMENT\n"
            f"  SITE  {site_name}\n"
            f"  WEATHER  {environment_name}\n"
            f"  WIND  {wind_speed:.1f}m/s      VIS  {visibility/1000:.1f}km"
        )
        self._telem_recording.setText(
            "MISSION DATA\n"
            "  REC  ACTIVE      ACMI  STREAMING\n"
            f"  BUS  LOCAL IPC   MODEL  {guidance_mode}\n"
            f"  RENDER  {sim_state.get('render_backend', 'PYBULLET CPU PREVIEW')}\n"
            f"  COMPUTE  {sim_state.get('compute_backend', 'CLASSICAL APN / CPU')}\n"
            f"  MODE  {sim_state.get('hardware_mode', 'SIL')}  "
            f"PROFILE  {sim_state.get('hardware_profile', 'REFERENCE')}"
        )

        # Threat bar
        if intruder_pos:
            range_threat = max(
                0.0,
                1.0 - math.sqrt(sum(v**2 for v in intruder_pos))
                / (4 * self._dome_radius),
            )
            current_tti = sim_state.get("tti", float("inf"))
            time_threat = (
                max(0.0, 1.0 - current_tti / 20.0)
                if current_tti < 999 else 0.0
            )
            threat = max(range_threat, time_threat)
        else:
            threat = 0.0
        bar_col = C["primary"] if threat < 0.5 else (C["amber"] if threat < 0.75 else C["red"])
        self._threat_bar.setValue(int(threat * 100))
        self._threat_pct.setText(f"THREAT INDEX  {threat*100:.0f}%")
        self._threat_pct.setStyleSheet(
            f"color: {bar_col}; font-size: 8px; font-weight: 700;"
        )
        range_value = (
            radar_return.get("range")
            if radar_return.get("detected") else None
        )
        tti_value = sim_state.get("tti", float("inf"))
        range_text = f"{range_value:.0f}" if range_value is not None else "---"
        tti_text = f"{tti_value:.1f}" if tti_value < 999 else "---"
        self._decision_values.setText(
            f"RANGE {range_text:>4} m    TTI {tti_text:>4} s"
        )

    def altitude_history(self) -> dict[str, list[tuple[float, float]]]:
        return {
            "intruder": self._intruder_alt.points(),
            "interceptor": self._intercept_alt.points(),
        }

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
        self._mission_panel.setVisible(True)
        self._timeline_state.setText("REPLAY READY")
        self._timeline_state.setStyleSheet(
            f"color: {C['amber']}; font-size: 8px; font-weight: 700;"
        )
        self._record_badge.setText("■ REC COMPLETE  /  ACMI SAVED")

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
