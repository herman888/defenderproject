"""
VisPy 3D renderer — anti-drone dome simulation.
Real 3D drone meshes, per-object telemetry panels, interactive camera pivot.
"""

import math
import os
import threading
import numpy as np
from vispy import app, scene
from vispy.scene import visuals
MatrixTransform = scene.transforms.MatrixTransform
from vispy.geometry import create_box

try:
    from scipy.spatial.transform import Rotation as _SciRot
    _SCIPY_OK = True
except ImportError:
    _SciRot   = None
    _SCIPY_OK = False

_ASSETS      = os.path.join(os.path.dirname(os.path.dirname(__file__)), "assets")
_RADAR_OMEGA = 12.0 / 60.0 * 2 * math.pi   # rad/s


# ═══════════════════════════════════════════════════════ geometry helpers ══════

def _rot_z(verts: np.ndarray, deg: float) -> np.ndarray:
    a = math.radians(deg)
    c, s = math.cos(a), math.sin(a)
    R = np.array([[c, -s, 0.0], [s, c, 0.0], [0.0, 0.0, 1.0]], dtype=np.float32)
    return (R @ verts.T).T


def _make_disc(r: float, n: int = 24, z: float = 0.0):
    angles = np.linspace(0, 2 * math.pi, n, endpoint=False)
    rim    = np.column_stack([r * np.cos(angles), r * np.sin(angles), np.full(n, z)])
    verts  = np.vstack([[[0, 0, z]], rim]).astype(np.float32)
    faces  = np.array([[0, i + 1, (i + 1) % n + 1] for i in range(n)], dtype=np.uint32)
    return verts, faces


def _combine(parts):
    """parts = list of (verts, faces, rgba_tuple).  Returns (verts, faces, vert_colors)."""
    v_list, f_list, c_list = [], [], []
    off = 0
    for verts, faces, rgba in parts:
        v_list.append(verts)
        f_list.append(faces + off)
        c_list.append(np.tile(np.array(rgba, dtype=np.float32), (len(verts), 1)))
        off += len(verts)
    return np.vstack(v_list), np.vstack(f_list), np.vstack(c_list)


def _build_quad_geom(scale: float, body_rgba, rotor_rgba):
    """
    Build quad-rotor mesh from drone.urdf geometry.
    Body in XY plane, rotors at +Z.  body +X = nose (for consumer/FPV).
    """
    parts = []

    # Central body box  0.6×0.6×0.15
    bv, bf, _ = create_box(0.6, 0.6, 0.15)
    parts.append((bv["position"].astype(np.float32), bf.astype(np.uint32), body_rgba))

    # 4 diagonal arms
    arm_cfg = [(0.25, -0.25, -45), (0.25, 0.25, 45), (-0.25, 0.25, 135), (-0.25, -0.25, -135)]
    for cx, cy, deg in arm_cfg:
        av, af, _ = create_box(0.5, 0.04, 0.04)
        avp = _rot_z(av["position"].astype(np.float32), deg)
        avp += np.array([cx, cy, 0.0], dtype=np.float32)
        parts.append((avp, af.astype(np.uint32), body_rgba))

    # 4 rotor discs  r=0.22
    for rx, ry in [(0.354, -0.354), (0.354, 0.354), (-0.354, 0.354), (-0.354, -0.354)]:
        dv, df = _make_disc(0.22, 24, z=0.06)
        dv[:, 0] += rx
        dv[:, 1] += ry
        parts.append((dv, df, rotor_rgba))

    verts, faces, colors = _combine(parts)
    return verts * scale, faces, colors


def _build_shahed_geom(scale: float, wing_rgba, fuse_rgba):
    """
    Try to load the Shahed-136 GLB mesh (decimated).
    Falls back to procedural delta-wing if trimesh unavailable or mesh missing.
    """
    glb = os.path.join(_ASSETS, "80_followers_iranian_shahed-136_drone.glb")
    try:
        import trimesh
        raw  = trimesh.load(glb, force="mesh")
        simp = raw.simplify_quadric_decimation(face_count=2000)
        v    = np.asarray(simp.vertices, dtype=np.float32)
        f    = np.asarray(simp.faces,    dtype=np.uint32)
        # glTF is Y-up with -Z forward; convert so nose→+X, wingspan→±Y, up→+Z
        # det=+1 proper rotation: GLB-Z→+X, GLB-X→-Y, GLB-Y→+Z
        R_base = np.array([[ 0, 0,-1],
                            [-1, 0, 0],
                            [ 0, 1, 0]], dtype=np.float32)
        v = (R_base @ v.T).T
        v -= v.mean(axis=0)           # centre AFTER rotation
        # Scale so total wingspan (Y extent) ≈ scale metres
        half_span = np.abs(v[:, 1]).max()
        v_scaled  = v * (scale * 0.5 / half_span) if half_span > 0 else v * scale
        colors    = np.tile(np.array(wing_rgba, dtype=np.float32), (len(v_scaled), 1))
        return v_scaled, f, colors
    except Exception:
        pass

    # ── fallback: procedural delta wing ──────────────────────────────────────
    parts = []
    t = 0.04  # half-thickness
    for sign in (+1.0, -1.0):
        # wing: apex at +X, swept back to ±Y
        wv = np.array([
            [ 1.0,  0.0,  t], [-0.7, sign*1.3,  t], [ 0.1, sign*0.1,  t],
            [ 1.0,  0.0, -t], [-0.7, sign*1.3, -t], [ 0.1, sign*0.1, -t],
        ], dtype=np.float32)
        wf = np.array([[0,1,2],[3,5,4],[0,3,4],[0,4,1],[1,4,5],[1,5,2],[2,5,3],[2,3,0]], dtype=np.uint32)
        parts.append((wv, wf, wing_rgba))

    # fuselage: long thin box along X axis
    fv, ff, _ = create_box(2.0, 0.22, 0.18)
    fvp = fv["position"].astype(np.float32)
    fvp[:, 0] += 0.1          # slight forward offset
    parts.append((fvp, ff.astype(np.uint32), fuse_rgba))

    verts, faces, colors = _combine(parts)
    return verts * scale, faces, colors


def _build_radar_tower_geom(target_height: float = 12.0):
    """
    Load radar tower GLB and return (verts, faces, per-vertex-colors).
    Falls back to a simple pole+dish if trimesh is unavailable or file missing.
    """
    glb_path = os.path.join(_ASSETS, "rts_radar_tower (1).glb")
    try:
        import trimesh
        raw = trimesh.load(glb_path, force="mesh")
        v = np.asarray(raw.vertices, dtype=np.float32)
        f = np.asarray(raw.faces,    dtype=np.uint32)
        # glTF is Y-up; convert to Z-up: (X, Y, Z) → (X, -Z, Y)
        v = np.column_stack([v[:, 0], -v[:, 2], v[:, 1]])
        # Centre XY, lift so base sits at z=0
        v[:, :2] -= v[:, :2].mean(axis=0)
        v[:, 2]  -= v[:, 2].min()
        h = v[:, 2].max()
        if h > 0:
            v *= target_height / h
        color = np.tile(np.array([0.38, 0.40, 0.42, 1.0], dtype=np.float32), (len(v), 1))
        return v, f, color
    except Exception:
        pass
    # Fallback: pole + dish
    parts = []
    bv, bf, _ = create_box(0.6, 0.6, 10.0)
    bvp = bv["position"].astype(np.float32); bvp[:, 2] += 5.0
    parts.append((bvp, bf.astype(np.uint32), (0.38, 0.40, 0.42, 1.0)))
    dv, df, _ = create_box(4.0, 4.0, 0.3)
    dvp = dv["position"].astype(np.float32); dvp[:, 2] += 10.2
    parts.append((dvp, df.astype(np.uint32), (0.44, 0.46, 0.48, 1.0)))
    return _combine(parts)


def _perp_vecs(d):
    """Two unit vectors orthogonal to d."""
    d = np.array(d, dtype=np.float64)
    d /= np.linalg.norm(d)
    up = np.array([0., 0., 1.]) if abs(d[2]) < 0.9 else np.array([1., 0., 0.])
    p1 = np.cross(d, up); p1 /= np.linalg.norm(p1)
    p2 = np.cross(d, p1)
    return p1.astype(np.float32), p2.astype(np.float32)


def _make_cone(apex, direction, half_deg, length, rgba_ring, n=22):
    """
    Triangle-fan cone mesh: apex (transparent) → ring of n points.
    Returns (vertices [n+1,3], faces [n,3], vertex_colors [n+1,4]).
    """
    apex = np.array(apex, dtype=np.float32)
    d    = np.array(direction, dtype=np.float64); d /= np.linalg.norm(d)
    p1, p2 = _perp_vecs(d)
    base   = apex + d.astype(np.float32) * float(length)
    br     = float(length) * math.tan(math.radians(half_deg))
    angles = np.linspace(0, 2 * math.pi, n, endpoint=False)
    ring   = (base[None]
              + br * np.cos(angles)[:, None] * p1[None]
              + br * np.sin(angles)[:, None] * p2[None])
    verts  = np.vstack([apex[None], ring]).astype(np.float32)
    faces  = np.array([[0, i + 1, (i + 1) % n + 1] for i in range(n)], dtype=np.uint32)
    r, g, b, a = rgba_ring
    colors    = np.zeros((n + 1, 4), dtype=np.float32)
    colors[1:] = [r, g, b, a]   # apex row stays [0,0,0,0] → transparent tip
    return verts, faces, colors


# ═══════════════════════════════════════════════════════════ math helpers ══════

def _quat_to_mat4(q) -> np.ndarray:
    """PyBullet (x,y,z,w) quaternion → 4×4 rotation matrix (float32)."""
    x, y, z, w = q
    return np.array([
        [1-2*(y*y+z*z),  2*(x*y-z*w),   2*(x*z+y*w),  0],
        [  2*(x*y+z*w),1-2*(x*x+z*z),   2*(y*z-x*w),  0],
        [  2*(x*z-y*w),  2*(y*z+x*w), 1-2*(x*x+y*y),  0],
        [0,              0,             0,              1],
    ], dtype=np.float32)


def _pose_mat(pos, quat, scale: float = 1.0) -> np.ndarray:
    """
    Build a 4×4 transform for VisPy's row-vector convention:
      v_out = v_in @ M   (v_in is a row vector [x,y,z,1])
    Translation goes in ROW 3, rotation is R.T in the top-left 3×3.
    """
    R = _quat_to_mat4(quat)[:3, :3]
    M = np.eye(4, dtype=np.float32)
    M[:3, :3] = R.T * scale      # R.T because VisPy multiplies on the right
    M[3, 0]   = pos[0]           # translation in last ROW, not last column
    M[3, 1]   = pos[1]
    M[3, 2]   = pos[2]
    return M


# ═══════════════════════════════════════════════════════════ HUD helper ════════

def _hud_quad(x, y, w, h, color, parent):
    verts = np.array([[x, y, 0], [x+w, y, 0], [x+w, y+h, 0], [x, y+h, 0]], dtype=np.float32)
    faces = np.array([[0, 1, 2], [0, 2, 3]], dtype=np.uint32)
    m = visuals.Mesh(vertices=verts, faces=faces, color=color, shading=None)
    m.parent = parent
    return m


# ════════════════════════════════════════════════════ shared pip helpers ══════

def _quat_axes(q, fwd_axis):
    """Rotate fwd_axis and world-up [0,0,1] by PyBullet quaternion (xyzw)."""
    if _SCIPY_OK:
        rot = _SciRot.from_quat(q)
        return rot.apply(fwd_axis), rot.apply([0.0, 0.0, 1.0])
    qx, qy, qz, qw = q
    def _qr(v):
        v = np.array(v, dtype=float)
        t = 2.0 * np.cross([qx, qy, qz], v)
        return v + qw * t + np.cross([qx, qy, qz], t)
    return _qr(fwd_axis), _qr([0.0, 0.0, 1.0])


def _set_cam(view, cam_pos, look_at):
    """Point a TurntableCamera at look_at from cam_pos."""
    diff = cam_pos - look_at
    dist = float(np.linalg.norm(diff))
    if dist < 0.5:
        return
    unit = diff / dist
    el   = math.degrees(math.asin(float(np.clip(unit[2], -1.0, 1.0))))
    az   = math.degrees(math.atan2(float(unit[0]), float(-unit[1])))
    cam  = view.camera
    cam.center    = tuple(look_at.tolist())
    cam.azimuth   = az
    cam.elevation = el
    cam.distance  = dist


# ═══════════════════════════════════════════════════════════ Renderer ═════════

_INTRUDER_SCALES = {
    "shahed136":     30.0,   # ~30m wingspan — clearly visible at 200m dome scale
    "consumer_quad": 20.0,
    "fpv_attack":    16.0,
}
_INTERCEPTOR_SCALE = 20.0


class SimRenderer:

    def __init__(self, shared_state: dict, state_lock: threading.Lock, dome_radius: float = 200.0):
        self._shared_state  = shared_state
        self._lock          = state_lock
        self._dome_radius   = dome_radius
        self._last_status   = "CLEAR"
        self._last_i_key    = None
        self._intruder_trail_pts  = []
        self._intercept_trail_pts = []
        self._cam_idx           = 0
        self._flash_count       = 0
        self._flash_timer       = None
        self._radar_sweep_angle = 0.0
        self._frame             = 0

        # PiP FPV state (initialised before _build_canvas so F-key handler is safe)
        # pip  = intruder tail-cam  (always on, no toggle)
        # pip2 = interceptor nose-cam (F key toggles)
        self._pip_visible   = True
        self._pip_canvas    = None
        self._pip_view      = None
        self._pip_label     = None
        self._pip_i_tf      = MatrixTransform()
        self._pip_i_mesh    = None
        self._pip_i_key     = None
        self._pip_int_tf    = MatrixTransform()
        self._pip_int_mesh  = None

        self._pip2_visible  = True
        self._pip2_canvas   = None
        self._pip2_view     = None
        self._pip2_label    = None
        self._pip2_i_tf     = MatrixTransform()
        self._pip2_i_mesh   = None
        self._pip2_i_key    = None
        self._pip2_int_tf   = MatrixTransform()
        self._pip2_int_mesh = None

        r = dome_radius
        self._cam_presets = [
            dict(elevation=28,  azimuth=-135, distance=r*2.2,  center=(0,0,r*0.2)),  # 0 overview
            None,                                                                       # 1 chase intruder
            dict(elevation=85,  azimuth=0,    distance=r*2.5,  center=(0,0,0)),       # 2 top-down
            dict(elevation=12,  azimuth=90,   distance=r*2.0,  center=(0,0,r*0.3)),  # 3 side
        ]

        self._build_canvas()
        self._build_scene()
        self._build_hud()
        self._build_pip()
        self._build_pip2()

    # ────────────────────────────────────────────────────── canvas / input ────

    def _build_canvas(self):
        self.canvas = scene.SceneCanvas(
            title    = "ANTI-DRONE DEFENSE — 3D VIEW",
            size     = (920, 700),
            position = (0, 0),           # left half of screen; dashboard takes right half
            bgcolor  = "#060a0e",
            keys     = "interactive",
            show     = True,
        )
        # Update HUD camera range to match actual canvas size
        self._canvas_w, self._canvas_h = 920, 700
        self.view = self.canvas.central_widget.add_view()
        r = self._dome_radius
        self.view.camera = scene.TurntableCamera(
            elevation=28, azimuth=-135,          # look from NE toward dome + radar
            distance=r * 2.2,                    # close enough to actually see things
            center=(0, 0, r * 0.2),              # look slightly above ground
            fov=60,
        )

        @self.canvas.events.key_press.connect
        def on_key(event):
            key = event.key.name
            with self._lock:
                if key == "Space":
                    self._shared_state["paused"] = not self._shared_state.get("paused", False)
                elif key == "R":
                    self._shared_state["restart"] = True
                elif key == "Q":
                    self._shared_state["quit"] = True
                elif key == "C":
                    self._cycle_camera()
                elif key in ("0", "1", "2", "3", "4", "5", "6"):
                    self._shared_state["sim_speed"] = {
                        "0": 0.10, "1": 0.25, "2": 0.5, "3": 1.0,
                        "4": 2.0,  "5": 4.0,  "6": 8.0,
                    }[key]
                elif key in ("F", "f"):
                    self._toggle_pip()

    # ────────────────────────────────────────────────────────── 3D scene ─────

    def _build_scene(self):
        r = self._dome_radius

        # Ground
        ground = visuals.Plane(
            width=1600, height=1600, width_segments=32, height_segments=32,
            color=(0.10, 0.13, 0.10, 1.0), parent=self.view.scene,
        )
        ground.transform = scene.transforms.STTransform(translate=(0, 0, 0))

        visuals.GridLines(color=(0.20, 0.28, 0.20, 0.6), parent=self.view.scene)

        # Dome wireframe — single merged Line visual
        self._dome_line = None
        self._draw_dome((0.0, 0.7, 0.15, 0.7))

        # Range rings
        self._draw_range_rings()

        # Cardinals
        for lbl, pos in [("N",(0,250,1)), ("S",(0,-250,1)), ("E",(250,0,1)), ("W",(-250,0,1))]:
            visuals.Text(lbl, color=(0.45,0.60,0.45,0.8), font_size=16, pos=pos,
                         parent=self.view.scene)

        # Protected assets
        for bx, by in [(30,20),(-25,30),(10,-35),(-30,-20)]:
            bv, bf, _ = create_box(8, 6, 6)
            m = visuals.Mesh(vertices=bv["position"], faces=bf,
                             color=(0.55,0.50,0.38,1.0), shading=None, parent=self.view.scene)
            m.transform = scene.transforms.STTransform(translate=(bx, by, 3))

        # Radar tower (GLB or procedural fallback)
        _rtv, _rtf, _rtc = _build_radar_tower_geom(target_height=12.0)
        _rt_mesh = visuals.Mesh(vertices=_rtv, faces=_rtf, vertex_colors=_rtc,
                                shading="smooth", parent=self.view.scene)
        _rt_mesh.transform = scene.transforms.STTransform(translate=(0, 0, 0))

        # ── Radar 3-D cone (search sweep + lock beam) ─────────────────────────
        _NC = 22
        _cv = np.zeros((_NC + 1, 3), dtype=np.float32)
        _cf = np.array([[0, i + 1, (i + 1) % _NC + 1] for i in range(_NC)], dtype=np.uint32)
        _cc = np.zeros((_NC + 1, 4), dtype=np.float32)
        self._radar_cone = visuals.Mesh(
            vertices=_cv, faces=_cf, vertex_colors=_cc,
            parent=self.view.scene)
        self._radar_cone.set_gl_state("additive", depth_test=False)
        self._radar_cone_n = _NC

        # Lock beam: apex → target
        self._radar_lock_line = visuals.Line(
            pos=np.zeros((2, 3), dtype=np.float32),
            color=(0.0, 1.0, 0.28, 0.0), width=2,
            parent=self.view.scene)

        # Lock ring: circle pulsing around the target
        _NR = 33
        self._radar_lock_ring = visuals.Line(
            pos=np.zeros((_NR, 3), dtype=np.float32),
            color=(0.0, 1.0, 0.28, 0.0), width=2,
            parent=self.view.scene)
        self._radar_cone_n    = _NC
        self._radar_locked    = False
        self._radar_lock_pulse = 0.0

        # ── drone meshes (built once, rebuilt on intruder-key change) ─────────
        self._intruder_mesh   = None
        self._intruder_tf     = MatrixTransform()
        self._interceptor_tf  = MatrixTransform()
        self._build_interceptor_mesh()

        # Trails
        self._intruder_trail   = visuals.Line(
            pos=np.zeros((2,3),dtype=np.float32), color=(1.0,0.15,0.05,0.8),
            width=2, parent=self.view.scene)
        self._intruder_trail.visible = False

        self._intercept_trail  = visuals.Line(
            pos=np.zeros((2,3),dtype=np.float32), color=(0.1,0.5,1.0,0.8),
            width=2, parent=self.view.scene)
        self._intercept_trail.visible = False

        # Predicted intercept
        self._predict_marker = visuals.Markers(parent=self.view.scene)
        self._predict_marker.set_data(
            pos=np.array([[0,0,-9999]],dtype=np.float32),
            face_color=(1.0,0.7,0.0,0.0), size=1, symbol="x")
        self._predict_marker.visible = False

        self._predict_line = visuals.Line(
            pos=np.zeros((2,3),dtype=np.float32),
            color=(1.0,0.7,0.0,0.5), width=1, parent=self.view.scene)
        self._predict_line.visible = False

        # Intercept flash text
        self._flash_text = visuals.Text(
            "★ INTERCEPT! ★", color=(1.0,1.0,0.0,0.0),
            font_size=22, bold=True, pos=(0,0,100), parent=self.view.scene)

        # Telemetry labels (3D billboarded text near each drone)
        self._i_telem   = visuals.Text("", color=(1.0,0.4,0.3,1.0),
            font_size=9, pos=(0,0,250), parent=self.view.scene)
        self._i_telem.visible = False

        self._int_telem = visuals.Text("", color=(0.2,0.7,1.0,1.0),
            font_size=9, pos=(0,0,0), parent=self.view.scene)
        self._int_telem.visible = False

    def _build_interceptor_mesh(self):
        bv, bf, bc = _build_quad_geom(
            _INTERCEPTOR_SCALE,
            body_rgba  = (0.10, 0.45, 0.90, 1.0),
            rotor_rgba = (0.20, 0.65, 1.00, 0.85),
        )
        self._interceptor_mesh = visuals.Mesh(
            vertices=bv, faces=bf, vertex_colors=bc, shading="flat",
            parent=self.view.scene)
        self._interceptor_mesh.transform = self._interceptor_tf
        self._interceptor_mesh.visible   = False

    def _build_intruder_mesh(self, intruder_key: str):
        if self._intruder_mesh is not None:
            self._intruder_mesh.parent = None

        scale = _INTRUDER_SCALES.get(intruder_key, 10.0)

        if intruder_key == "shahed136":
            bv, bf, bc = _build_shahed_geom(
                scale,
                wing_rgba = (0.80, 0.10, 0.08, 1.0),
                fuse_rgba = (0.60, 0.08, 0.06, 1.0),
            )
        elif intruder_key == "fpv_attack":
            bv, bf, bc = _build_quad_geom(
                scale,
                body_rgba  = (0.88, 0.42, 0.05, 1.0),
                rotor_rgba = (1.00, 0.60, 0.15, 0.85),
            )
        else:  # consumer_quad
            bv, bf, bc = _build_quad_geom(
                scale,
                body_rgba  = (0.75, 0.10, 0.05, 1.0),
                rotor_rgba = (1.00, 0.25, 0.10, 0.85),
            )

        self._intruder_mesh = visuals.Mesh(
            vertices=bv, faces=bf, vertex_colors=bc, shading="flat",
            parent=self.view.scene)
        self._intruder_mesh.transform = self._intruder_tf
        self._intruder_mesh.visible   = False
        self._last_i_key = intruder_key

    # ── dome ──────────────────────────────────────────────────────────────────

    def _draw_dome(self, color):
        if hasattr(self, "_dome_line") and self._dome_line is not None:
            self._dome_line.parent = None

        r  = self._dome_radius
        ca = np.array(color, dtype=np.float32)

        pts, conn = [], []
        N_RING_PTS = 33   # points per latitude ring
        N_LAT      = 7    # latitude rings
        N_LON      = 10   # longitude lines
        N_LON_PTS  = 8    # points per meridian

        for li in range(N_LAT):
            lat = math.pi / 2 * li / (N_LAT - 1)
            cl  = math.cos(lat)
            sl  = math.sin(lat)
            for j in range(N_RING_PTS):
                lon = 2 * math.pi * j / (N_RING_PTS - 1)
                pts.append([r*cl*math.cos(lon), r*cl*math.sin(lon), r*sl])
            conn.extend([True] * (N_RING_PTS - 1) + [False])

        for li in range(N_LON):
            lon = 2 * math.pi * li / N_LON
            cl_lon, sl_lon = math.cos(lon), math.sin(lon)
            for j in range(N_LON_PTS):
                lat = math.pi / 2 * j / (N_LON_PTS - 1)
                cl  = math.cos(lat)
                sl  = math.sin(lat)
                pts.append([r*cl*cl_lon, r*cl*sl_lon, r*sl])
            conn.extend([True] * (N_LON_PTS - 1) + [False])

        pos_arr  = np.array(pts,  dtype=np.float32)
        conn_arr = np.array(conn[:len(pts) - 1], dtype=bool)

        self._dome_line = visuals.Line(
            pos=pos_arr, connect=conn_arr,
            color=ca, width=1.5,
            parent=self.view.scene,
        )

    def update_dome_color(self, status):
        colors = {
            "CLEAR":       (0.00, 0.70, 0.15, 0.70),
            "TRACKING":    (0.90, 0.75, 0.00, 0.80),
            "BREACH":      (1.00, 0.15, 0.05, 0.90),
            "INTERCEPTED": (0.00, 0.85, 1.00, 1.00),
        }
        ca = np.array(colors.get(status, (0.0, 0.7, 0.15, 0.7)), dtype=np.float32)
        self._dome_line.set_data(color=ca)

    def _draw_range_rings(self):
        specs = [
            ( 50, (0.15,0.25,0.15,0.5), "50m"),
            (100, (0.15,0.30,0.15,0.6), "100m"),
            (200, (0.00,0.65,0.15,0.9), "200m ◄ DOME"),
            (400, (0.15,0.22,0.15,0.4), "400m"),
        ]
        for radius, color, label in specs:
            pts = [[radius*math.cos(2*math.pi*j/128),
                    radius*math.sin(2*math.pi*j/128), 0.1] for j in range(129)]
            visuals.Line(pos=np.array(pts, dtype=np.float32),
                         color=np.array(color, dtype=np.float32),
                         width=2.0 if radius==200 else 1.0,
                         parent=self.view.scene)
            lx = radius*math.cos(math.pi/4)+2
            ly = radius*math.sin(math.pi/4)+2
            visuals.Text(label, color=color, font_size=8, pos=(lx,ly,1.0),
                         parent=self.view.scene)

    def _update_radar_sweep(self, state=None):
        r    = self._dome_radius
        a    = self._radar_sweep_angle
        apex = np.array([0.0, 0.0, 12.0], dtype=np.float32)   # tower-top at centre
        n    = self._radar_cone_n

        rdr      = (state or {}).get("radar_return") or {}
        detected = rdr.get("detected", False)
        conf     = (state or {}).get("track_confidence", 0.0)
        i_pos    = (state or {}).get("intruder_pos")

        if detected and i_pos and conf > 0.35:
            # ── LOCKED: narrow cone aimed at target ───────────────────────────
            target = np.array(i_pos, dtype=np.float32)
            diff   = target - apex
            dist   = float(np.linalg.norm(diff))
            if dist > 2.0:
                direction = diff / dist
                v, f, c = _make_cone(apex, direction, 6.0, dist,
                                     (0.10, 1.0, 0.28, 0.45), n=n)
                self._radar_cone.set_data(vertices=v, faces=f, vertex_colors=c)

                self._radar_lock_pulse = (self._radar_lock_pulse + 0.28) % (2 * math.pi)
                beam_a = 0.55 + 0.35 * math.sin(self._radar_lock_pulse)
                self._radar_lock_line.set_data(
                    pos=np.array([apex, target], dtype=np.float32),
                    color=(0.10, 1.0, 0.28, float(beam_a)))

                # Pulsing ring centred on target, perpendicular to beam axis
                p1, p2 = _perp_vecs(direction)
                ring_r = max(4.0, dist * 0.06)
                ring_a = 0.45 + 0.40 * math.sin(self._radar_lock_pulse)
                NR = 33
                ring_pts = np.array([
                    target + ring_r * (math.cos(2 * math.pi * j / (NR - 1)) * p1
                                       + math.sin(2 * math.pi * j / (NR - 1)) * p2)
                    for j in range(NR)], dtype=np.float32)
                self._radar_lock_ring.set_data(
                    pos=ring_pts, color=(0.10, 1.0, 0.28, float(ring_a)))
                self._radar_locked = True
                return

        # ── SEARCH: wide cone sweeping 360° around Z, tilted 20° above horizon ─
        self._radar_locked = False
        el_rad = math.radians(20)
        cos_el = math.cos(el_rad)
        direction = np.array([
            math.cos(a) * cos_el,
            math.sin(a) * cos_el,
            math.sin(el_rad),
        ], dtype=np.float32)
        v, f, c = _make_cone(apex, direction, 13.0, r * 1.3,
                              (0.04, 0.82, 0.15, 0.18), n=n)
        self._radar_cone.set_data(vertices=v, faces=f, vertex_colors=c)

        # Hide lock visuals while searching
        _a2 = apex + np.array([0, 0, 0.01], dtype=np.float32)
        self._radar_lock_line.set_data(
            pos=np.array([apex, _a2], dtype=np.float32),
            color=(0.0, 1.0, 0.28, 0.0))
        _dummy = np.tile(apex, (33, 1))
        self._radar_lock_ring.set_data(
            pos=_dummy, color=(0.0, 1.0, 0.28, 0.0))

    # ────────────────────────────────────────────────────────── HUD (2D) ─────

    def _build_hud(self):
        W, H = self._canvas_w, self._canvas_h
        self._hud_view = self.canvas.central_widget.add_view()
        self._hud_view.camera = scene.PanZoomCamera(aspect=1)
        self._hud_view.camera.set_range(x=(0, W), y=(0, H))
        self._hud_view.interactive = False
        hv = self._hud_view.scene

        # Left panel — taller to fit 4 data rows
        _hud_quad(0, H - 170, 630, 170, (0.04, 0.06, 0.04, 0.82), hv)

        self._hud_status = visuals.Text(
            "● STATUS: CLEAR", color=(0.0, 1.0, 0.4, 1.0),
            font_size=16, bold=True,
            anchor_x="left", anchor_y="top", pos=(10, H), parent=hv)

        # Intruder: range, bearing, elevation, altitude, speed
        self._hud_intruder = visuals.Text(
            "INTRUDER  RNG:---m  BRG:---°  EL:---°  ALT:---m  SPD:---m/s",
            color=(1.0, 0.35, 0.2, 1.0), font_size=10,
            anchor_x="left", anchor_y="top", pos=(10, H - 30), parent=hv)

        # Radar track: confidence, SNR, threat %
        self._hud_radar = visuals.Text(
            "         RADAR CONF:---%  SNR:---dB  THREAT:--%",
            color=(0.88, 0.30, 0.18, 0.85), font_size=10,
            anchor_x="left", anchor_y="top", pos=(10, H - 50), parent=hv)

        # Interceptor row
        self._hud_intercept = visuals.Text(
            "INTERCEPTOR  SEP:---m  SPD:---m/s  TTI:---",
            color=(0.2, 0.65, 1.0, 1.0), font_size=10,
            anchor_x="left", anchor_y="top", pos=(10, H - 72), parent=hv)

        # TTI countdown — large, shown when TTI < 15 s
        self._hud_tti = visuals.Text(
            "", color=(1.0, 0.60, 0.0, 1.0), font_size=20, bold=True,
            anchor_x="right", anchor_y="top", pos=(620, H - 28), parent=hv)
        self._hud_tti.visible = False

        # Mission timer top-right
        self._hud_timer = visuals.Text(
            "T+0.0s  1.0×",
            color=(1.0, 1.0, 1.0, 0.9), font_size=11,
            anchor_x="right", anchor_y="top", pos=(W - 10, H), parent=hv)

        # Bottom controls bar
        _hud_quad(0, 0, W, 20, (0.04, 0.06, 0.04, 0.72), hv)
        visuals.Text(
            "Drag=orbit  Scroll=zoom  SPACE=pause  C=cam  F=fpv  R=restart  Q=quit  0-6=speed",
            color=(0.30, 0.45, 0.30, 0.9), font_size=8,
            anchor_x="left", anchor_y="bottom", pos=(8, 3), parent=hv)

        # Threat bar
        _hud_quad(10, H - 160, 200, 14, (0.08, 0.10, 0.08, 0.8), hv)
        visuals.Text("THREAT", color=(0.30, 0.45, 0.30, 0.8), font_size=9,
                     anchor_x="left", anchor_y="bottom", pos=(10, H - 146), parent=hv)
        self._threat_fill = visuals.Line(
            pos=np.array([[10, H - 153, 0], [11, H - 153, 0]], dtype=np.float32),
            color=(0.0, 0.8, 0.15, 0.9), width=10, parent=hv)

        # Debrief overlay
        cx, cy = W // 2, H // 2
        self._debrief_bg    = _hud_quad(cx - 250, cy - 150, 500, 300,
                                         (0.05, 0.07, 0.05, 0.92), hv)
        self._debrief_bg.visible = False
        self._debrief_title = visuals.Text(
            "", color=(0.0, 1.0, 0.4, 1.0), font_size=22, bold=True,
            anchor_x="center", anchor_y="center", pos=(cx, cy + 60), parent=hv)
        self._debrief_title.visible = False
        self._debrief_stats = visuals.Text(
            "", color=(0.8, 0.8, 0.8, 1.0), font_size=12,
            anchor_x="center", anchor_y="center", pos=(cx, cy), parent=hv)
        self._debrief_stats.visible = False

    # ──────────────────────────────────────────────────── FPV PiP window ────

    def _toggle_pip(self):
        """F key: toggle the interceptor nose-cam window on/off."""
        self._pip2_visible = not self._pip2_visible
        print("FPV INTERCEPTOR: ON" if self._pip2_visible else "FPV INTERCEPTOR: OFF")
        if self._pip2_canvas is not None:
            try:
                self._pip2_canvas.show(self._pip2_visible)
            except Exception:
                try:
                    if self._pip2_visible:
                        self._pip2_canvas.native.show()
                    else:
                        self._pip2_canvas.native.hide()
                except Exception:
                    pass

    def _build_pip(self):
        r  = self._dome_radius
        W, H = self._canvas_w, self._canvas_h
        pw, ph = W // 4, H // 4                   # 230 × 175 for 920×700 main
        px, py = W - pw - 10, H - ph - 10         # bottom-right of main canvas

        try:
            self._pip_canvas = scene.SceneCanvas(
                title="FPV",
                size=(pw, ph),
                position=(px, py),
                bgcolor=(0.02, 0.04, 0.02, 1.0),
                show=True,
            )
        except Exception as e:
            print(f"[PiP] Could not create FPV canvas: {e}")
            return

        # ── 3-D scene view ─────────────────────────────────────────────────
        self._pip_view = self._pip_canvas.central_widget.add_view()
        self._pip_view.camera = scene.TurntableCamera(
            elevation=20, azimuth=0, distance=r * 0.3,
            center=(0, 0, r * 0.1), fov=80,
        )
        self._pip_view.camera.interactive = False

        sv = self._pip_view.scene

        # Ground
        visuals.Plane(
            width=800, height=800,
            color=(0.07, 0.10, 0.07, 1.0),
            parent=sv,
        )

        # Simplified dome: equator ring + 4 meridians
        pts, conn = [], []
        N = 48
        for i in range(N + 1):
            a = 2 * math.pi * i / N
            pts.append([r * math.cos(a), r * math.sin(a), 0.2])
        conn.extend([True] * N + [False])
        for lon_deg in (0, 90, 180, 270):
            la = math.radians(lon_deg)
            for j in range(9):
                lt = math.pi / 2 * j / 8
                pts.append([r * math.cos(lt) * math.cos(la),
                             r * math.cos(lt) * math.sin(la),
                             r * math.sin(lt)])
            conn.extend([True] * 8 + [False])
        p_arr = np.array(pts, dtype=np.float32)
        c_arr = np.array(conn[:len(pts) - 1], dtype=bool)
        visuals.Line(pos=p_arr, connect=c_arr,
                     color=(0.0, 0.7, 0.15, 0.5), width=1, parent=sv)

        # Interceptor mesh (independent instance)
        bv, bf, bc = _build_quad_geom(
            _INTERCEPTOR_SCALE,
            body_rgba=(0.10, 0.45, 0.90, 1.0),
            rotor_rgba=(0.20, 0.65, 1.00, 0.85),
        )
        self._pip_int_mesh = visuals.Mesh(
            vertices=bv, faces=bf, vertex_colors=bc,
            shading="flat", parent=sv,
        )
        self._pip_int_mesh.transform = self._pip_int_tf
        self._pip_int_mesh.visible   = False

        # ── HUD overlay: border + label ─────────────────────────────────────
        hud = self._pip_canvas.central_widget.add_view()
        hud.camera = scene.PanZoomCamera(aspect=1)
        hud.camera.set_range(x=(0, pw), y=(0, ph))
        hud.interactive = False
        hv = hud.scene

        # 2-px bright-green border
        border = np.array([
            [1,      1,      0],
            [pw - 1, 1,      0],
            [pw - 1, ph - 1, 0],
            [1,      ph - 1, 0],
            [1,      1,      0],
        ], dtype=np.float32)
        visuals.Line(pos=border, color=(0.0, 1.0, 0.4, 1.0), width=2, parent=hv)

        self._pip_label = visuals.Text(
            "FPV — INTRUDER",
            color=(0.0, 1.0, 0.4, 1.0), font_size=8, bold=True,
            anchor_x="left", anchor_y="top",
            pos=(5, ph - 3),
            parent=hv,
        )

    def _build_pip_intruder_mesh(self, ikey: str):
        """Rebuild intruder mesh in PiP scene when intruder type changes."""
        if self._pip_view is None:
            return
        if self._pip_i_mesh is not None:
            self._pip_i_mesh.parent = None

        scale = _INTRUDER_SCALES.get(ikey, 10.0)
        if ikey == "shahed136":
            bv, bf, bc = _build_shahed_geom(
                scale,
                wing_rgba=(0.80, 0.10, 0.08, 1.0),
                fuse_rgba=(0.60, 0.08, 0.06, 1.0),
            )
        elif ikey == "fpv_attack":
            bv, bf, bc = _build_quad_geom(
                scale,
                body_rgba=(0.88, 0.42, 0.05, 1.0),
                rotor_rgba=(1.00, 0.60, 0.15, 0.85),
            )
        else:
            bv, bf, bc = _build_quad_geom(
                scale,
                body_rgba=(0.75, 0.10, 0.05, 1.0),
                rotor_rgba=(1.00, 0.25, 0.10, 0.85),
            )

        self._pip_i_mesh = visuals.Mesh(
            vertices=bv, faces=bf, vertex_colors=bc,
            shading="flat", parent=self._pip_view.scene,
        )
        self._pip_i_mesh.transform = self._pip_i_tf
        self._pip_i_mesh.visible   = False
        self._pip_i_key            = ikey

    # ────────────────────────────────── interceptor nose-cam pip2 (F-toggle) ──

    def _build_pip2(self):
        r  = self._dome_radius
        W, H = self._canvas_w, self._canvas_h
        pw, ph = W // 4, H // 4                    # 230 × 175
        px = W - pw - 10                            # same right edge as pip1
        py = H - ph * 2 - 20                        # directly above pip1 (10px gap)

        try:
            self._pip2_canvas = scene.SceneCanvas(
                title="FPV INTERCEPTOR",
                size=(pw, ph),
                position=(px, py),
                bgcolor=(0.02, 0.03, 0.05, 1.0),   # dark blue tint for contrast
                show=True,
            )
        except Exception as e:
            print(f"[PiP2] Could not create interceptor FPV canvas: {e}")
            return

        self._pip2_view = self._pip2_canvas.central_widget.add_view()
        self._pip2_view.camera = scene.TurntableCamera(
            elevation=15, azimuth=0, distance=r * 0.3,
            center=(0, 0, r * 0.1), fov=80,
        )
        self._pip2_view.camera.interactive = False

        sv = self._pip2_view.scene

        visuals.Plane(width=800, height=800,
                      color=(0.05, 0.07, 0.10, 1.0), parent=sv)

        # Simplified dome
        pts, conn = [], []
        N = 48
        for i in range(N + 1):
            a = 2 * math.pi * i / N
            pts.append([r * math.cos(a), r * math.sin(a), 0.2])
        conn.extend([True] * N + [False])
        for lon_deg in (0, 90, 180, 270):
            la = math.radians(lon_deg)
            for j in range(9):
                lt = math.pi / 2 * j / 8
                pts.append([r * math.cos(lt) * math.cos(la),
                             r * math.cos(lt) * math.sin(la),
                             r * math.sin(lt)])
            conn.extend([True] * 8 + [False])
        p_arr = np.array(pts, dtype=np.float32)
        c_arr = np.array(conn[:len(pts) - 1], dtype=bool)
        visuals.Line(pos=p_arr, connect=c_arr,
                     color=(0.0, 0.5, 0.9, 0.4), width=1, parent=sv)

        # Intruder mesh (the target we're chasing — shown, not self)
        self._pip2_int_mesh = None   # interceptor mesh — never shown (we are it)

        # HUD: border + label
        hud = self._pip2_canvas.central_widget.add_view()
        hud.camera = scene.PanZoomCamera(aspect=1)
        hud.camera.set_range(x=(0, pw), y=(0, ph))
        hud.interactive = False
        hv = hud.scene

        border = np.array([
            [1,      1,      0],
            [pw - 1, 1,      0],
            [pw - 1, ph - 1, 0],
            [1,      ph - 1, 0],
            [1,      1,      0],
        ], dtype=np.float32)
        visuals.Line(pos=border, color=(0.2, 0.6, 1.0, 1.0), width=2, parent=hv)

        self._pip2_label = visuals.Text(
            "FPV — INTERCEPTOR",
            color=(0.2, 0.6, 1.0, 1.0), font_size=8, bold=True,
            anchor_x="left", anchor_y="top",
            pos=(5, ph - 3),
            parent=hv,
        )

    def _build_pip2_intruder_mesh(self, ikey: str):
        if self._pip2_view is None:
            return
        if self._pip2_i_mesh is not None:
            self._pip2_i_mesh.parent = None

        scale = _INTRUDER_SCALES.get(ikey, 10.0)
        if ikey == "shahed136":
            bv, bf, bc = _build_shahed_geom(scale,
                wing_rgba=(0.80, 0.10, 0.08, 1.0),
                fuse_rgba=(0.60, 0.08, 0.06, 1.0))
        elif ikey == "fpv_attack":
            bv, bf, bc = _build_quad_geom(scale,
                body_rgba=(0.88, 0.42, 0.05, 1.0),
                rotor_rgba=(1.00, 0.60, 0.15, 0.85))
        else:
            bv, bf, bc = _build_quad_geom(scale,
                body_rgba=(0.75, 0.10, 0.05, 1.0),
                rotor_rgba=(1.00, 0.25, 0.10, 0.85))

        self._pip2_i_mesh = visuals.Mesh(
            vertices=bv, faces=bf, vertex_colors=bc,
            shading="flat", parent=self._pip2_view.scene)
        self._pip2_i_mesh.transform = self._pip2_i_tf
        self._pip2_i_mesh.visible   = False
        self._pip2_i_key            = ikey

    # ─────────────────────────────────────────────────── camera control ──────

    def _cycle_camera(self):
        self._cam_idx = (self._cam_idx + 1) % len(self._cam_presets)
        p = self._cam_presets[self._cam_idx]
        if p is not None:
            self.view.camera.elevation = p["elevation"]
            self.view.camera.azimuth   = p["azimuth"]
            self.view.camera.distance  = p["distance"]
            self.view.camera.center    = p.get("center", (0,0,0))

    # ─────────────────────────────────────────────────── intercept flash ─────

    def _trigger_flash(self, pos):
        self._flash_count = 6
        self._flash_text.pos   = (pos[0], pos[1], pos[2] + 12)
        self._flash_text.color = (1.0, 1.0, 0.0, 1.0)
        if self._flash_timer:
            self._flash_timer.stop()
        self._flash_timer = app.Timer(interval=0.3, connect=self._flash_tick, start=True)

    def _flash_tick(self, ev):
        if self._flash_count <= 0:
            self._flash_timer.stop()
            self._flash_text.color = (1.0, 1.0, 0.0, 0.0)
            return
        self._flash_count -= 1
        if self._flash_count % 2 == 0:
            self.update_dome_color("INTERCEPTED")
        else:
            self._dome_line.set_data(
                color=np.array((1.0, 1.0, 1.0, 0.5), dtype=np.float32))

    # ──────────────────────────────────────────────────────────── trails ─────

    def _update_trail(self, pts_list, new_pos, line_visual, rgb, max_pts=60):
        pts_list.append(list(new_pos))
        if len(pts_list) > max_pts:
            pts_list.pop(0)
        if len(pts_list) >= 2:
            n      = len(pts_list)
            alphas = np.linspace(0.05, 1.0, n)
            colors = np.column_stack([
                np.full(n, rgb[0]), np.full(n, rgb[1]),
                np.full(n, rgb[2]), alphas,
            ]).astype(np.float32)
            line_visual.set_data(pos=np.array(pts_list, dtype=np.float32), color=colors)
            line_visual.visible = True

    # ───────────────────────────────────────────────────────── HUD refresh ───

    def _refresh_hud(self, state):
        status = state.get("dome_status", "CLEAR")
        sc_map = {
            "CLEAR":       (0.0,1.0,0.4,1.0),
            "TRACKING":    (1.0,0.8,0.0,1.0),
            "BREACH":      (1.0,0.2,0.0,1.0),
            "INTERCEPTED": (0.0,0.9,1.0,1.0),
        }
        tag = " [PAUSED]" if state.get("paused") else ""
        self._hud_status.text  = f"● STATUS: {status}{tag}"
        self._hud_status.color = sc_map.get(status, (1,1,1,1))

        i_pos  = state.get("intruder_pos")
        i_spd  = state.get("intruder_speed", 0.0)
        rdr    = state.get("radar_return") or {}
        detected = rdr.get("detected", False)
        rng    = rdr.get("range") if detected else None
        snr    = rdr.get("snr", 0.0) if detected else None
        conf   = state.get("track_confidence", 0.0)
        rstr   = f"{rng:.0f}m" if rng else "no lock"

        # Intruder line: range, bearing, elevation, altitude, speed
        if i_pos:
            horiz = math.sqrt(i_pos[0]**2 + i_pos[1]**2)
            brg   = math.degrees(math.atan2(i_pos[0], i_pos[1])) % 360
            el    = math.degrees(math.atan2(i_pos[2], max(horiz, 1.0)))
            self._hud_intruder.text = (
                f"INTRUDER  RNG:{rstr}  BRG:{brg:05.1f}°  EL:{el:+.1f}°"
                f"  ALT:{i_pos[2]:.0f}m  SPD:{i_spd:.0f}m/s")
        else:
            self._hud_intruder.text = "INTRUDER  RNG:---  BRG:---  EL:---  ALT:---  SPD:---"

        # Radar / threat row
        if detected:
            conf_s = f"{conf*100:.0f}%"
            snr_s  = f"{snr:.1f}dB" if snr is not None else "---"
        else:
            conf_s, snr_s = "---%", "---dB"
        if i_pos:
            dist   = math.sqrt(i_pos[0]**2 + i_pos[1]**2 + i_pos[2]**2)
            threat = max(0.0, min(1.0, 1.0 - dist / (self._dome_radius * 2.5)))
        else:
            threat = 0.0
        self._hud_radar.text = (
            f"         RADAR CONF:{conf_s}  SNR:{snr_s}  THREAT:{threat*100:.0f}%")

        int_pos = state.get("interceptor_pos")
        tti     = state.get("tti", float("inf"))
        if int_pos and i_pos:
            sep     = math.sqrt(sum((int_pos[k]-i_pos[k])**2 for k in range(3)))
            int_spd = state.get("interceptor_speed", 0.0)
            tti_s   = f"{tti:.1f}s" if tti < 999 else "---"
            arrow   = " ◄" if tti < 10 else ""
            self._hud_intercept.text = (
                f"INTERCEPTOR  SEP:{sep:.0f}m  SPD:{int_spd:.0f}m/s  TTI:{tti_s}{arrow}")
        else:
            self._hud_intercept.text = "INTERCEPTOR  SEP:---  SPD:---  TTI:---"

        # TTI countdown widget (right side of panel, large font)
        if tti < 15 and int_pos and i_pos:
            if tti < 5:
                col = (1.0, 0.15, 0.05, 1.0)   # red
            elif tti < 10:
                col = (1.0, 0.55, 0.0, 1.0)    # orange
            else:
                col = (1.0, 0.85, 0.0, 0.9)    # yellow
            self._hud_tti.text    = f"TTI {tti:.1f}s"
            self._hud_tti.color   = col
            self._hud_tti.visible = True
        else:
            self._hud_tti.visible = False

        t   = state.get("mission_time", 0.0)
        spd = state.get("sim_speed", 1.0)
        self._hud_timer.text = f"T+{t:.1f}s  {spd:.2g}×"

        # Threat bar
        bar_w = max(1.0, threat * 195)
        H     = self._canvas_h
        tc    = (threat*2, 0.8, 0.0, 0.9) if threat < 0.5 else (1.0, (1-threat)*1.6, 0.0, 0.9)
        self._threat_fill.set_data(
            pos=np.array([[10, H-153, 0], [10+bar_w, H-153, 0]], dtype=np.float32),
            color=tc)

        # Debrief
        debrief = state.get("debrief")
        if debrief:
            r = debrief.get("result","")
            if r == "INTERCEPTED":
                ttl, tc2 = "★ INTERCEPTED ★", (0.0,0.9,1.0,1.0)
            elif r == "FAILURE":
                ttl, tc2 = "✗ MISSION FAILED", (1.0,0.2,0.0,1.0)
            else:
                ttl, tc2 = f"⚠ {r}", (1.0,0.7,0.0,1.0)
            dur = debrief.get("sim_time", 0.0)
            ca  = debrief.get("closest_approach", float("inf"))
            cas = f"{ca:.1f}m" if ca < 9999 else "---"
            self._debrief_title.text  = ttl
            self._debrief_title.color = tc2
            self._debrief_stats.text  = f"Duration: {dur:.1f}s    Closest approach: {cas}"
            self._debrief_bg.visible    = True
            self._debrief_title.visible = True
            self._debrief_stats.visible = True
        else:
            self._debrief_bg.visible    = False
            self._debrief_title.visible = False
            self._debrief_stats.visible = False

    # ─────────────────────────────────────────── 3D telemetry text update ────

    def _refresh_telem(self, state):
        i_pos   = state.get("intruder_pos")
        int_pos = state.get("interceptor_pos")
        i_key   = state.get("intruder_key", "shahed136")
        i_spd   = state.get("intruder_speed", 0.0)
        rdr     = state.get("radar_return") or {}
        rng     = rdr.get("range") if rdr.get("detected") else None
        status  = state.get("dome_status", "CLEAR")

        if i_pos:
            rstr = f"{rng:.0f}m" if rng else "---"
            label_map = {"shahed136":"SHAHED-136", "consumer_quad":"CONSUMER QUAD",
                         "fpv_attack":"FPV ATTACK"}
            type_name = label_map.get(i_key, i_key.upper())
            # Position label to the right and slightly above the drone
            off = min(40.0, self._dome_radius * 0.15)
            self._i_telem.pos = (i_pos[0] + off, i_pos[1], i_pos[2] + off * 0.5)
            self._i_telem.text = (
                f"{type_name}\n"
                f"ALT {i_pos[2]:.0f}m  SPD {i_spd:.0f}m/s\n"
                f"RNG {rstr}  [{status}]"
            )
            self._i_telem.visible = True
        else:
            self._i_telem.visible = False

        if int_pos:
            int_spd = state.get("interceptor_speed", 0.0)
            tti     = state.get("tti", float("inf"))
            tti_s   = f"{tti:.1f}s" if tti < 999 else "---"
            sep_s   = "---"
            if i_pos:
                sep   = math.sqrt(sum((int_pos[k]-i_pos[k])**2 for k in range(3)))
                sep_s = f"{sep:.0f}m"
            off = min(40.0, self._dome_radius * 0.15)
            self._int_telem.pos = (int_pos[0] - off, int_pos[1], int_pos[2] + off * 0.5)
            self._int_telem.text = (
                f"INTERCEPTOR\n"
                f"ALT {int_pos[2]:.0f}m  SPD {int_spd:.0f}m/s\n"
                f"SEP {sep_s}  TTI {tti_s}"
            )
            self._int_telem.visible = True
        else:
            self._int_telem.visible = False

    # ────────────────────────────────────────────────────── FPV PiP update ────

    def _update_pip(self, state: dict):
        """Intruder tail-cam — always on, drone visible ahead of camera."""
        if self._pip_canvas is None:
            return

        i_pos  = state.get("intruder_pos")
        i_orn  = state.get("intruder_orientation")
        i_key  = state.get("intruder_key")
        int_pos = state.get("interceptor_pos")
        int_orn = state.get("interceptor_orientation")

        if i_key and i_key != self._pip_i_key:
            self._build_pip_intruder_mesh(i_key)

        # Show intruder mesh (you're behind it watching), update interceptor pose
        if self._pip_i_mesh is not None:
            if i_pos and i_orn:
                self._pip_i_mesh.visible = True
                self._pip_i_tf.matrix = _pose_mat(i_pos, i_orn)
            else:
                self._pip_i_mesh.visible = False

        if self._pip_int_mesh is not None:
            if int_pos and int_orn:
                self._pip_int_mesh.visible = True
                self._pip_int_tf.matrix = _pose_mat(int_pos, int_orn)
            else:
                self._pip_int_mesh.visible = False

        if not i_pos or i_pos[2] < 2.0:
            if self._pip_label is not None:
                self._pip_label.text = "CAM — INTRUDER (STANDBY)"
            self._pip_canvas.update()
            return

        if self._pip_label is not None:
            self._pip_label.text = "CAM — INTRUDER"

        if i_orn is not None:
            pos_arr  = np.array(i_pos, dtype=float)
            nose, up = _quat_axes(i_orn, [1, 0, 0])
            cam_pos  = pos_arr + nose * (-25.0) + up * 8.0
            look_at  = pos_arr + nose * 20.0
            _set_cam(self._pip_view, cam_pos, look_at)

        self._pip_canvas.update()

    def _update_pip2(self, state: dict):
        """Interceptor nose-cam — toggled with F, interceptor mesh hidden."""
        if self._pip2_canvas is None or not self._pip2_visible:
            return

        i_pos   = state.get("intruder_pos")
        i_orn   = state.get("intruder_orientation")
        i_key   = state.get("intruder_key")
        int_pos = state.get("interceptor_pos")
        int_orn = state.get("interceptor_orientation")

        if i_key and i_key != self._pip2_i_key:
            self._build_pip2_intruder_mesh(i_key)

        # Show intruder (the target), hide self (interceptor)
        if self._pip2_i_mesh is not None:
            if i_pos and i_orn:
                self._pip2_i_mesh.visible = True
                self._pip2_i_tf.matrix = _pose_mat(i_pos, i_orn)
            else:
                self._pip2_i_mesh.visible = False

        if self._pip2_int_mesh is not None:
            self._pip2_int_mesh.visible = False   # you are the interceptor

        if not int_pos:
            if self._pip2_label is not None:
                self._pip2_label.text = "FPV — INTERCEPTOR (STANDBY)"
            self._pip2_canvas.update()
            return

        if self._pip2_label is not None:
            self._pip2_label.text = "FPV — INTERCEPTOR"

        pos_arr = np.array(int_pos, dtype=float)

        # Nose direction: toward intruder (interceptor is always chasing it)
        if i_pos:
            fwd = np.array(i_pos, dtype=float) - pos_arr
            l   = float(np.linalg.norm(fwd))
            fwd = fwd / l if l > 0.5 else np.array([0.0, 1.0, 0.0])
        elif int_orn is not None:
            # Not yet chasing — derive from orientation tilt (+Z body = thrust)
            thrust, _ = _quat_axes(int_orn, [0, 0, 1])
            fwd_xy    = np.array([thrust[0], thrust[1], 0.0])
            l         = float(np.linalg.norm(fwd_xy))
            fwd       = fwd_xy / l if l > 0.15 else np.array([0.0, 1.0, 0.0])
        else:
            fwd = np.array([0.0, 1.0, 0.0])

        up      = np.array([0.0, 0.0, 1.0])
        cam_pos = pos_arr + fwd * (-25.0) + up * 8.0
        look_at = pos_arr + fwd * 20.0
        _set_cam(self._pip2_view, cam_pos, look_at)

        self._pip2_canvas.update()

    # ──────────────────────────────────────────────────────── main update ────

    def update(self, ev):
        """Called by VisPy timer at ~60 Hz."""
        with self._lock:
            state = dict(self._shared_state)

        if state.get("app_quit"):
            app.quit()
            return

        i_key       = state.get("intruder_key")
        i_pos       = state.get("intruder_pos")
        i_orn       = state.get("intruder_orientation")
        int_pos     = state.get("interceptor_pos")
        int_orn     = state.get("interceptor_orientation")
        status      = state.get("dome_status", "CLEAR")
        predicted   = state.get("predicted_intercept")

        # Rebuild intruder mesh if type changed
        if i_key and i_key != self._last_i_key:
            self._build_intruder_mesh(i_key)

        # ── intruder mesh pose ────────────────────────────────────────────────
        if self._intruder_mesh is not None:
            if i_pos and i_orn:
                self._intruder_mesh.visible = True
                self._intruder_tf.matrix = _pose_mat(
                    i_pos, i_orn, scale=1.0)    # mesh already pre-scaled at build time
            else:
                self._intruder_mesh.visible = False

        # ── interceptor mesh pose ─────────────────────────────────────────────
        if int_pos and int_orn:
            self._interceptor_mesh.visible = True
            self._interceptor_tf.matrix = _pose_mat(int_pos, int_orn, scale=1.0)
        else:
            self._interceptor_mesh.visible = False

        # ── trails ────────────────────────────────────────────────────────────
        if i_pos:
            self._update_trail(self._intruder_trail_pts, i_pos,
                               self._intruder_trail, (1.0,0.15,0.05))
        if int_pos:
            self._update_trail(self._intercept_trail_pts, int_pos,
                               self._intercept_trail, (0.1,0.5,1.0))

        # ── predicted intercept ───────────────────────────────────────────────
        if predicted and int_pos:
            self._predict_marker.visible = True
            self._predict_marker.set_data(
                pos=np.array([predicted], dtype=np.float32),
                face_color=(1.0,0.7,0.0,0.9), size=14, symbol="x")
            self._predict_line.visible = True
            self._predict_line.set_data(
                pos=np.array([int_pos, predicted], dtype=np.float32),
                color=(1.0,0.7,0.0,0.5))
        else:
            self._predict_marker.visible = False
            self._predict_line.visible   = False

        # ── dome color on status change ───────────────────────────────────────
        if status != self._last_status:
            self.update_dome_color(status)
            if status == "INTERCEPTED" and i_pos:
                self._trigger_flash(i_pos)
            self._last_status = status

        # ── chase-intruder camera ─────────────────────────────────────────────
        if self._cam_idx == 1 and i_pos:
            bearing = math.degrees(math.atan2(i_pos[0], i_pos[1]))
            self.view.camera.azimuth   = bearing + 180
            self.view.camera.elevation = 15
            self.view.camera.distance  = self._dome_radius * 2

        # ── radar sweep ───────────────────────────────────────────────────────
        self._radar_sweep_angle += _RADAR_OMEGA / 20.0
        self._update_radar_sweep(state)

        # ── HUD + telemetry (throttled — text rebuild is expensive) ─────────
        self._frame += 1
        if self._frame % 2 == 0:    # HUD at ~10 Hz
            self._refresh_hud(state)
        if self._frame % 3 == 0:    # telemetry at ~7 Hz
            self._refresh_telem(state)
        self.canvas.update()
        self._update_pip(state)
        self._update_pip2(state)
