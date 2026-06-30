#!/usr/bin/env python3
"""Spin each Betaflight motor briefly via CLI. PROPS OFF + battery plugged in."""

from __future__ import annotations

import glob
import struct
import sys
import time

try:
    import serial
except ImportError:
    print("Install pyserial: pip install pyserial")
    sys.exit(1)

BAUD = 115200
THROTTLE = 1080
STOP = 1000
SPIN_SEC = 1.2


def find_fc_port() -> str:
    ports = sorted(glob.glob("/dev/cu.usbmodem*"))
    if not ports:
        print("No flight controller found. Plug USB and try again.")
        sys.exit(1)
    if len(ports) > 1:
        print(f"Multiple USB serial devices: {ports}")
        print(f"Using: {ports[0]}")
    return ports[0]


def msp(ser: serial.Serial, cmd: int, payload: bytes = b"") -> bytes:
    size = len(payload)
    chk = size ^ cmd
    for b in payload:
        chk ^= b
    ser.write(b"$M<" + bytes([size, cmd]) + payload + bytes([chk]))
    time.sleep(0.35)
    return ser.read(512)


def battery_voltage(ser: serial.Serial) -> float:
    r = msp(ser, 110)
    if r.startswith(b"$M>") and r[3] >= 2:
        return struct.unpack("<H", r[5:7])[0] / 10.0
    return 0.0


def cli(ser: serial.Serial, cmd: str, wait: float = 0.4) -> None:
    ser.write((cmd + "\n").encode())
    time.sleep(wait)
    if ser.in_waiting:
        ser.read(ser.in_waiting)


def stop_all(ser: serial.Serial) -> None:
    for i in range(4):
        cli(ser, f"motor {i} {STOP}", 0.25)


def main() -> None:
    port = sys.argv[1] if len(sys.argv) > 1 else find_fc_port()

    print("=" * 50)
    print("Betaflight motor test")
    print("=" * 50)
    print(f"Port: {port}")
    print("REQUIRED: all propellers REMOVED")
    print("REQUIRED: LiPo battery plugged into the drone")
    print()
    ans = input("Type YES if props are off and battery is in: ").strip()
    if ans.upper() != "YES":
        print("Aborted.")
        return

    ser = serial.Serial(port, BAUD, timeout=1)
    time.sleep(0.3)
    ser.reset_input_buffer()

    v = battery_voltage(ser)
    print(f"Battery voltage: {v:.1f} V")
    if v < 10.0:
        print("No battery detected (need ~10V+). Plug LiPo in and try again.")
        ser.close()
        return

    ser.write(b"#")
    time.sleep(0.8)
    ser.reset_input_buffer()

    print("\nSpinning motors 1-4 one at a time (low throttle)...")
    try:
        for motor in range(4):
            print(f"  Motor {motor + 1} spinning...")
            cli(ser, f"motor {motor} {THROTTLE}", 0.5)
            time.sleep(SPIN_SEC)
            cli(ser, f"motor {motor} {STOP}", 0.3)
            time.sleep(0.4)
    finally:
        stop_all(ser)
        cli(ser, "exit")
        ser.close()

    print("\nDone. All motors stopped. Unplug the battery.")


if __name__ == "__main__":
    main()
