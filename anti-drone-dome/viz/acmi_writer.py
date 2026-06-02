"""
Writes Tacview-compatible ACMI 2.1 files in real time.
Tacview (free version from tacview.net) can load this file live
while the sim is running for professional 3D mission visualization.
"""

import math
import os
from datetime import datetime


class ACMIWriter:
    _REF_LAT = 43.0000
    _REF_LON = -79.0000
    _METERS_PER_DEG = 111111.0

    def __init__(self, missions_dir: str = None):
        if missions_dir is None:
            missions_dir = os.path.normpath(
                os.path.join(os.path.dirname(__file__), "..", "missions")
            )
        os.makedirs(missions_dir, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        self._filename = f"session_{ts}.acmi"
        self._filepath = os.path.join(missions_dir, self._filename)
        self._f = open(self._filepath, "w", encoding="utf-8")
        self._update_count = 0
        self._write_header()
        print(
            "\n"
            "╔══════════════════════════════════════════════════════╗\n"
            "║  TACVIEW EXPORT ACTIVE                               ║\n"
            f"║  File: missions/{self._filename:<35}║\n"
            "║  Open Tacview → File → Open → select this file      ║\n"
            "║  For live view: load file while simulation is running║\n"
            "╚══════════════════════════════════════════════════════╝"
        )

    def _write_header(self):
        self._f.write("FileType=text/acmi/tabular\n")
        self._f.write("FileVersion=2.0\n")
        self._f.write("0,ReferenceTime=2024-01-01T00:00:00Z\n")
        self._f.write(f"0,ReferenceLatitude={self._REF_LAT}\n")
        self._f.write(f"0,ReferenceLongitude={self._REF_LON}\n")
        self._f.write("0,Title=Anti-Drone Dome Defense\n")
        self._f.write("0,Author=DefenderProject\n")
        # Initial object declarations at their reference positions
        ref_lat = self._REF_LAT
        ref_lon = self._REF_LON
        self._f.write(f"1,T={ref_lon:.4f}|{ref_lat+0.002:.4f}|220,Name=Intruder,Type=Air+FixedWing,Color=Red,Coalition=Enemies\n")
        self._f.write(f"2,T={ref_lon:.4f}|{ref_lat-0.002:.4f}|5,Name=Interceptor,Type=Air+Rotorcraft,Color=Blue,Coalition=Allies\n")
        self._f.write(f"3,T={ref_lon:.4f}|{ref_lat-0.002:.4f}|10,Name=RadarStation,Type=Ground+Static,Color=Green,Coalition=Allies\n")
        self._f.write(f"4,T={ref_lon:.4f}|{ref_lat:.4f}|0,Name=DomeCenter,Type=Ground+Static,Color=Green,Coalition=Allies\n")
        self._f.flush()

    def _to_latlon(self, x, y, z):
        lat = self._REF_LAT + (y / self._METERS_PER_DEG)
        lon = self._REF_LON + (x / self._METERS_PER_DEG)
        return lat, lon, z

    @staticmethod
    def _quat_to_rpy(q):
        """Convert PyBullet quaternion (x,y,z,w) to roll/pitch/yaw in degrees."""
        x, y, z, w = q
        sinr = 2.0 * (w * x + y * z)
        cosr = 1.0 - 2.0 * (x * x + y * y)
        roll = math.degrees(math.atan2(sinr, cosr))
        sinp = 2.0 * (w * y - z * x)
        sinp = max(-1.0, min(1.0, sinp))
        pitch = math.degrees(math.asin(sinp))
        siny = 2.0 * (w * z + x * y)
        cosy = 1.0 - 2.0 * (y * y + z * z)
        yaw = math.degrees(math.atan2(siny, cosy))
        return roll, pitch, yaw

    def update(self, elapsed_seconds: float, intruder_state: dict,
               interceptor_state: dict, radar_state: dict = None):
        self._f.write(f"#{elapsed_seconds:.2f}\n")

        if intruder_state:
            pos = intruder_state.get("position", (0, 0, 0))
            lat, lon, alt = self._to_latlon(*pos)
            orn = intruder_state.get("orientation", (0, 0, 0, 1))
            roll, pitch, yaw = self._quat_to_rpy(orn)
            self._f.write(
                f"1,T={lon:.6f}|{lat:.6f}|{alt:.1f}|{roll:.1f}|{pitch:.1f}|{yaw:.1f}\n"
            )

        if interceptor_state:
            pos = interceptor_state.get("position", (0, 0, 0))
            if pos[2] > 1.0:
                lat, lon, alt = self._to_latlon(*pos)
                orn = interceptor_state.get("orientation", (0, 0, 0, 1))
                roll, pitch, yaw = self._quat_to_rpy(orn)
                self._f.write(
                    f"2,T={lon:.6f}|{lat:.6f}|{alt:.1f}|{roll:.1f}|{pitch:.1f}|{yaw:.1f}\n"
                )

        self._update_count += 1
        if self._update_count % 48 == 0:
            self._f.flush()

    def write_event(self, elapsed: float, event_type: str, message: str = ""):
        self._f.write(f"#{elapsed:.2f}\n")
        if event_type == "RADAR_LOCK":
            self._f.write("0,Event=Message|SourceId:3|Message:Radar Lock - Track Acquired\n")
        elif event_type == "DOME_BREACH":
            self._f.write("0,Event=Message|SourceId:1|Message:DOME BREACH - Intruder Inside Perimeter\n")
        elif event_type == "INTERCEPT":
            self._f.write("0,Event=Timeout|SourceId:2|AmmoType:INTERCEPT|TargetId:1|Outcome:Kill\n")
        elif event_type == "MISS":
            self._f.write("0,Event=Message|SourceId:1|Message:MISSION FAILED - Intruder Reached Target\n")
        else:
            self._f.write(f"0,Event=Message|SourceId:1|Message:{message or event_type}\n")
        self._f.flush()

    def close(self):
        try:
            self._f.flush()
            self._f.close()
        except Exception:
            pass
        print(f"[ACMI] Saved: {self._filepath}")

    @property
    def filename(self) -> str:
        return self._filename
