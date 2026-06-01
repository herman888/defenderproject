"""MAVLink UDP data link: broadcast track data and receive it back."""

import socket
import time
from pymavlink import mavutil

_BASE_LAT = 430000000   # 43.0000 degrees * 1e7
_BASE_LON = -790000000  # -79.0000 degrees * 1e7
_METERS_TO_DEGREES = 0.00001  # 1m = 0.00001 degrees


def _pos_to_mavlink(x, y, z):
    lat = int(_BASE_LAT + y * _METERS_TO_DEGREES * 1e7)
    lon = int(_BASE_LON + x * _METERS_TO_DEGREES * 1e7)
    alt = int(z * 1000)  # mm
    return lat, lon, alt


class DataLink:
    def __init__(self, role: str = "broadcast", port: int = 14550):
        self._role = role
        self._port = port
        self._seq = 0
        self._conn = None
        self._last_track = None
        self._sock = None
        self._setup(port)

    def _setup(self, port: int):
        for p in [port, port + 1, port + 2]:
            try:
                if self._role == "broadcast":
                    self._conn = mavutil.mavlink_connection(
                        f"udpout:127.0.0.1:{p}",
                        source_system=1,
                        source_component=1,
                    )
                    self._port = p
                    break
                else:
                    self._conn = mavutil.mavlink_connection(
                        f"udpin:0.0.0.0:{p}",
                        source_system=2,
                    )
                    self._conn.mav.srcSystem = 2
                    self._port = p
                    break
            except Exception as e:
                print(f"DATALINK: Port {p} failed: {e}")
                continue

    def send_track(self, track_data: dict):
        if self._conn is None or not track_data or not track_data.get("detected"):
            return
        try:
            pos = track_data.get("position_estimate", (0, 0, 0))
            vel = track_data.get("velocity", (0, 0, 0))
            lat, lon, alt = _pos_to_mavlink(*pos)
            vx = int(vel[0] * 100) if len(vel) > 0 else 0
            vy = int(vel[1] * 100) if len(vel) > 1 else 0
            vz = int(vel[2] * 100) if len(vel) > 2 else 0

            self._conn.mav.global_position_int_send(
                int(time.time() * 1000) & 0xFFFFFFFF,
                lat,
                lon,
                alt,
                alt,
                vx, vy, vz,
                65535,
            )
            self._seq += 1
            print(f"DATALINK: Broadcasting track — pos ({pos[0]:.1f}, {pos[1]:.1f}, {pos[2]:.1f}) "
                  f"vel ({vel[0] if len(vel) > 0 else 0:.1f}, "
                  f"{vel[1] if len(vel) > 1 else 0:.1f}, "
                  f"{vel[2] if len(vel) > 2 else 0:.1f}) seq={self._seq}")
        except Exception as e:
            pass  # Silent fail on send error

    def receive_track(self) -> dict:
        if self._conn is None:
            return None
        try:
            msg = self._conn.recv_match(type="GLOBAL_POSITION_INT", blocking=False)
            if msg is None:
                return None
            lat = msg.lat / 1e7
            lon = msg.lon / 1e7
            alt = msg.alt / 1000.0
            x = (lon - _BASE_LON / 1e7) / _METERS_TO_DEGREES
            y = (lat - _BASE_LAT / 1e7) / _METERS_TO_DEGREES
            z = alt
            vx = msg.vx / 100.0
            vy = msg.vy / 100.0
            vz = msg.vz / 100.0
            track = {
                "detected": True,
                "position_estimate": (x, y, z),
                "velocity": (vx, vy, vz),
                "timestamp": time.time(),
            }
            self._last_track = track
            return track
        except Exception:
            return self._last_track

    def close(self):
        if self._conn:
            try:
                self._conn.close()
            except Exception:
                pass
