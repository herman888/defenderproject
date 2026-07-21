"""
MAVLink bridge to ArduCopter SITL — Stage B interceptor flight control.

The guidance module produces a GuidanceSetpoint (LOCAL_NED) each step.
This bridge forwards it as SET_POSITION_TARGET_LOCAL_NED to ArduPilot
SITL and reads back LOCAL_POSITION_NED so the caller can sync the
PyBullet interceptor body used for rendering and intercept detection.

The PyBullet Drone.apply_setpoint() call is replaced entirely; guidance/
and dome/ code require no changes — they still see an interceptor with
position, velocity, and state identical to what they've always consumed.

Quick-start (Windows)
─────────────────────
Option A — Mission Planner SITL (easiest):
  1. Open Mission Planner → Simulation tab → ArduCopter → Start
  2. Mission Planner connects on TCP 5760; SITL also outputs to UDP 14550
  3. python main.py --sitl --sitl-port 14550

Option B — standalone ArduCopter binary (WSL2 / Linux):
  sim_vehicle.py -v ArduCopter \\
      --home=43.0,-79.0,0,0 \\
      --out=udp:127.0.0.1:14560 -w
  python main.py --sitl --sitl-port 14560

Option C — SITL binary direct (Windows native):
  ArduCopter.exe --home=43.0,-79.0,0,0
  python main.py --sitl --sitl-port 5762

Coordinate frames
─────────────────
  Sim  : ENU — East=+X, North=+Y, Up=+Z, origin = dome centre.
  ArduPilot LOCAL_NED: North=+X, East=+Y, Down=-Z.
  GuidanceSetpoint already stores LOCAL_NED — fields pass to MAVLink unchanged.
  Incoming LOCAL_POSITION_NED  → ned_to_enu() → sim ENU cached in _pos_enu/_vel_enu.
"""

import threading
import time

from pymavlink import mavutil

import config
from guidance.setpoint import ned_to_enu

# ── MAVLink type-mask bit constants ─────────────────────────────────────────
# Each bit SET = "ignore this field in SET_POSITION_TARGET_LOCAL_NED"
_M = mavutil.mavlink
_IGNORE_POS      = (_M.POSITION_TARGET_TYPEMASK_X_IGNORE |
                    _M.POSITION_TARGET_TYPEMASK_Y_IGNORE |
                    _M.POSITION_TARGET_TYPEMASK_Z_IGNORE)
_IGNORE_VEL      = (_M.POSITION_TARGET_TYPEMASK_VX_IGNORE |
                    _M.POSITION_TARGET_TYPEMASK_VY_IGNORE |
                    _M.POSITION_TARGET_TYPEMASK_VZ_IGNORE)
_IGNORE_ACCEL    = (_M.POSITION_TARGET_TYPEMASK_AX_IGNORE |
                    _M.POSITION_TARGET_TYPEMASK_AY_IGNORE |
                    _M.POSITION_TARGET_TYPEMASK_AZ_IGNORE)
_IGNORE_YAW      = _M.POSITION_TARGET_TYPEMASK_YAW_IGNORE
_IGNORE_YAW_RATE = _M.POSITION_TARGET_TYPEMASK_YAW_RATE_IGNORE


def _build_type_mask(sp) -> int:
    """Build MAVLink type_mask from GuidanceSetpoint: set IGNORE bits for None fields."""
    mask = _IGNORE_YAW_RATE  # never use yaw_rate in this bridge
    if sp.position is None:
        mask |= _IGNORE_POS
    if sp.velocity is None:
        mask |= _IGNORE_VEL
    if sp.accel is None:
        mask |= _IGNORE_ACCEL
    if sp.yaw is None:
        mask |= _IGNORE_YAW
    return mask


# ── Bridge class ─────────────────────────────────────────────────────────────
class SITLBridge:
    """
    Connects to ArduCopter SITL, arms it, issues takeoff, then streams
    GuidanceSetpoints as SET_POSITION_TARGET_LOCAL_NED messages.

    Thread-safe: state is cached by a background recv thread and accessed
    via a lock, so the caller's 240 Hz physics loop never blocks on socket I/O.
    """

    HEARTBEAT_TIMEOUT = 30.0   # s — abort if no heartbeat within this
    ARM_TIMEOUT       = 10.0   # s
    MODE_TIMEOUT      =  5.0   # s

    def __init__(self, addr: str = "127.0.0.1", port: int = 14560):
        self._addr = addr
        self._port = port
        self._conn = None

        self._lock    = threading.Lock()
        self._pos_enu = (0.0, 0.0, 0.0)   # interceptor position in sim ENU
        self._vel_enu = (0.0, 0.0, 0.0)   # interceptor velocity in sim ENU

        self._connected    = False
        self._guided       = False
        self._armed        = False
        self._recv_running = False
        self._recv_thread  = None
        self._last_state_monotonic = None
        self._last_receive_error = None

    # ── Lifecycle ─────────────────────────────────────────────────────────────
    def connect(self) -> bool:
        """
        Connect to SITL, wait for heartbeat, set home, arm, enter GUIDED
        mode, and issue takeoff to PAD_ALTITUDE_M.  Returns True on success.
        """
        url = f"udpin:0.0.0.0:{self._port}"
        print(f"[SITL] Connecting  {url}  (SITL must be sending to 127.0.0.1:{self._port})")
        try:
            self._conn = mavutil.mavlink_connection(
                url, source_system=255, source_component=0)
        except Exception as exc:
            print(f"[SITL] mavlink_connection failed: {exc}")
            return False

        # ── Wait for heartbeat ───────────────────────────────────────────────
        print("[SITL] Waiting for heartbeat …")
        hb = self._conn.wait_heartbeat(timeout=self.HEARTBEAT_TIMEOUT)
        if hb is None:
            print("[SITL] No heartbeat — is SITL running and outputting to this port?")
            self._conn.close()
            self._conn = None
            return False
        tgt_sys  = self._conn.target_system
        tgt_comp = self._conn.target_component
        print(f"[SITL] Heartbeat received  system={tgt_sys}  comp={tgt_comp}")

        # ── Request LOCAL_POSITION_NED stream at 50 Hz ───────────────────────
        self._conn.mav.request_data_stream_send(
            tgt_sys, tgt_comp,
            mavutil.mavlink.MAV_DATA_STREAM_POSITION, 50, 1)

        # ── Pin home to match sim reference site ─────────────────────────────
        self._conn.mav.command_long_send(
            tgt_sys, tgt_comp,
            mavutil.mavlink.MAV_CMD_DO_SET_HOME,
            0,                           # confirmation
            0,                           # param1: use specified location
            0, 0, 0,                     # param2-4 unused
            config.HOME_LAT,
            config.HOME_LON,
            config.HOME_ALT,
        )
        print(f"[SITL] Home set  ({config.HOME_LAT}, {config.HOME_LON})")

        # ── GUIDED mode ──────────────────────────────────────────────────────
        if not self._set_guided():
            print("[SITL] Failed to enter GUIDED mode")
            self.close()
            return False

        # ── Arm ──────────────────────────────────────────────────────────────
        if not self._arm():
            print("[SITL] Failed to arm")
            self.close()
            return False

        # ── Takeoff ──────────────────────────────────────────────────────────
        self._conn.mav.command_long_send(
            tgt_sys, tgt_comp,
            mavutil.mavlink.MAV_CMD_NAV_TAKEOFF,
            0, 0, 0, 0, 0, 0, 0,
            float(config.PAD_ALTITUDE_M),
        )
        print(f"[SITL] Takeoff commanded  target={config.PAD_ALTITUDE_M} m")

        # ── Start background recv thread ─────────────────────────────────────
        self._connected    = True
        self._recv_running = True
        self._recv_thread  = threading.Thread(
            target=self._recv_loop, daemon=True, name="sitl-recv")
        self._recv_thread.start()

        print("[SITL] Bridge ready — interceptor climbing to pad altitude")
        return True

    def close(self):
        """Disarm vehicle and close MAVLink connection."""
        self._recv_running = False
        if self._recv_thread is not None:
            self._recv_thread.join(timeout=1.0)
        if self._conn and self._connected:
            try:
                # Disarm
                self._conn.mav.command_long_send(
                    self._conn.target_system,
                    self._conn.target_component,
                    mavutil.mavlink.MAV_CMD_COMPONENT_ARM_DISARM,
                    0, 0, 0, 0, 0, 0, 0, 0,
                )
            except Exception:
                pass
            try:
                self._conn.close()
            except Exception:
                pass
        self._conn      = None
        self._connected = False
        self._recv_thread = None
        print("[SITL] Bridge closed")

    # ── Setpoint streaming ────────────────────────────────────────────────────
    def send_setpoint(self, sp) -> None:
        """
        Forward a GuidanceSetpoint to ArduPilot as SET_POSITION_TARGET_LOCAL_NED.

        sp.position/velocity/accel are already in LOCAL_NED (from guidance/)
        so they pass through to the MAVLink message fields without conversion.
        None fields get their IGNORE bits set in type_mask.
        """
        if self._conn is None or not self._guided:
            return

        mask  = _build_type_mask(sp)
        pos   = sp.position or (0.0, 0.0, 0.0)
        vel   = sp.velocity or (0.0, 0.0, 0.0)
        acc   = sp.accel    or (0.0, 0.0, 0.0)
        yaw   = float(sp.yaw) if sp.yaw is not None else 0.0

        try:
            self._conn.mav.set_position_target_local_ned_send(
                int(time.time() * 1000) & 0xFFFFFFFF,
                self._conn.target_system,
                self._conn.target_component,
                mavutil.mavlink.MAV_FRAME_LOCAL_NED,
                mask,
                float(pos[0]), float(pos[1]), float(pos[2]),  # N, E, D
                float(vel[0]), float(vel[1]), float(vel[2]),  # vN, vE, vD
                float(acc[0]), float(acc[1]), float(acc[2]),  # aN, aE, aD
                yaw, 0.0,                                      # yaw, yaw_rate
            )
        except Exception as exc:
            print(f"[SITL] send_setpoint error: {exc}")

    # ── State access ──────────────────────────────────────────────────────────
    def get_state(self) -> tuple:
        """Return (pos_enu, vel_enu) in sim ENU coordinates (metres, m/s)."""
        with self._lock:
            return self._pos_enu, self._vel_enu

    def is_at_pad_altitude(self) -> bool:
        """True when SITL interceptor has climbed to within TAKEOFF_TOL_M of PAD_ALTITUDE_M."""
        _, _, z = self._pos_enu          # ENU z = altitude
        return z >= (config.PAD_ALTITUDE_M - config.TAKEOFF_TOL_M)

    def health(self) -> dict:
        age_s = None
        if self._last_state_monotonic is not None:
            age_s = max(0.0, time.monotonic() - self._last_state_monotonic)
        return {
            "connected": self._connected,
            "guided": self._guided,
            "armed": self._armed,
            "state_age_s": age_s,
            "last_receive_error": self._last_receive_error,
        }

    # ── Private ───────────────────────────────────────────────────────────────
    def _set_guided(self) -> bool:
        mode_map = self._conn.mode_mapping() or {}
        mode_id  = mode_map.get("GUIDED", 4)   # 4 = ArduCopter GUIDED fallback

        self._conn.mav.set_mode_send(
            self._conn.target_system,
            mavutil.mavlink.MAV_MODE_FLAG_CUSTOM_MODE_ENABLED,
            mode_id,
        )
        deadline = time.time() + self.MODE_TIMEOUT
        while time.time() < deadline:
            msg = self._conn.recv_match(type="HEARTBEAT", blocking=True, timeout=1.0)
            if msg and msg.custom_mode == mode_id:
                self._guided = True
                print(f"[SITL] GUIDED mode confirmed  (id={mode_id})")
                return True
        return False

    def _arm(self) -> bool:
        self._conn.mav.command_long_send(
            self._conn.target_system,
            self._conn.target_component,
            mavutil.mavlink.MAV_CMD_COMPONENT_ARM_DISARM,
            0, 1, 0, 0, 0, 0, 0, 0,
        )
        deadline = time.time() + self.ARM_TIMEOUT
        while time.time() < deadline:
            msg = self._conn.recv_match(type="COMMAND_ACK", blocking=True, timeout=1.0)
            if msg and msg.command == mavutil.mavlink.MAV_CMD_COMPONENT_ARM_DISARM:
                ok = (msg.result == mavutil.mavlink.MAV_RESULT_ACCEPTED)
                if ok:
                    self._armed = True
                    print("[SITL] Armed")
                else:
                    print(f"[SITL] Arm rejected (MAV_RESULT={msg.result})")
                return ok
        print("[SITL] Arm timed out")
        return False

    def _recv_loop(self):
        """Background thread: drain LOCAL_POSITION_NED and cache as ENU."""
        while self._recv_running:
            try:
                msg = self._conn.recv_match(
                    type=["LOCAL_POSITION_NED"],
                    blocking=True, timeout=0.05)
                if msg is None:
                    continue
                # LOCAL_NED: x=North, y=East, z=Down → ENU via ned_to_enu
                pos_enu = ned_to_enu((msg.x,  msg.y,  msg.z))
                vel_enu = ned_to_enu((msg.vx, msg.vy, msg.vz))
                with self._lock:
                    self._pos_enu = pos_enu
                    self._vel_enu = vel_enu
                    self._last_state_monotonic = time.monotonic()
                    self._last_receive_error = None
            except (OSError, AttributeError) as exc:
                self._last_receive_error = str(exc)
                if self._recv_running:
                    print(f"[SITL] receive error: {exc}")
                time.sleep(0.05)
