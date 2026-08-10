"""Read-only Betaflight interrogation.  It cannot send actuation or write commands."""
from __future__ import annotations

import argparse
import re
import time
from pathlib import Path

from bench_common import NOT_MEASURED, metadata, write_artifact

SCHEMA = "larp.fc-interrogation.v1"
READ_ONLY_COMMANDS = ("version", "status", "resource", "serial", "get serialrx_provider", "dump")
FORBIDDEN = ("save", "defaults", "set ", "feature ", "resource ", "serial ", "motor", "arm", "bl", "dfu")


def root_path() -> Path:
    return Path(__file__).resolve().parent.parent


def ports() -> list[dict]:
    from serial.tools import list_ports
    return [{"device": item.device, "description": item.description, "hwid": item.hwid, "vid": f"{item.vid:04X}" if item.vid is not None else NOT_MEASURED, "pid": f"{item.pid:04X}" if item.pid is not None else NOT_MEASURED, "serial_number": item.serial_number or NOT_MEASURED} for item in list_ports.comports()]


def safe_command(command: str) -> None:
    lowered = command.lower().strip()
    if command not in READ_ONLY_COMMANDS or any(token in lowered for token in FORBIDDEN):
        raise ValueError(f"refusing non-read-only command: {command!r}")


def read_until_idle(serial_port, initial_s: float = 2.0, idle_s: float = .4, maximum_s: float = 20.0) -> str:
    deadline, last, chunks = time.monotonic() + maximum_s, time.monotonic(), []
    while time.monotonic() < deadline:
        available = serial_port.in_waiting
        if available:
            chunks.append(serial_port.read(available)); last = time.monotonic()
        elif time.monotonic() - last > max(initial_s, idle_s):
            break
        time.sleep(.03)
    return b"".join(chunks).decode("utf-8", errors="replace")


def interrogate(port: str, baud: int) -> tuple[dict, str]:
    import serial
    transcript = []
    with serial.Serial(port, baudrate=baud, timeout=.1, write_timeout=.5) as connection:
        connection.dtr = True; connection.rts = True
        # Betaflight's CLI entry marker is '#'. This is not a configuration
        # command; all subsequent commands remain hard-whitelisted read-only.
        connection.write(b"#\r\n"); connection.flush()
        transcript.append({"command": "cli_entry_hash", "output": read_until_idle(connection, initial_s=.5, maximum_s=2)})
        for command in READ_ONLY_COMMANDS:
            safe_command(command)
            connection.write((command + "\n").encode("ascii")); connection.flush()
            transcript.append({"command": command, "output": read_until_idle(connection, maximum_s=35 if command == "dump" else 8)})
    raw = "\n".join(f"# {item['command']}\n{item['output']}" for item in transcript)
    def match(pattern):
        found = re.search(pattern, raw, re.IGNORECASE | re.MULTILINE)
        if not found:
            return NOT_MEASURED
        return (found.group(1) if found.lastindex else found.group(0)).strip()
    summary = {"firmware_target": match(r"#\s*Betaflight\s*/\s*([^\s]+)"), "betaflight_version": match(r"Betaflight\s*/\s*[^\s]+\s+([^\s]+)"), "board_identifier": match(r"Board:\s*([^\s]+)"), "mcu_identifier": match(r"MCU\s+([^,\r\n]+)"), "unique_id": match(r"unique id:\s*([^\r\n]+)"), "flash_total_or_free": match(r"(?:flash|Flash)[^\r\n]*")}
    return summary, raw


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", default="COM5"); parser.add_argument("--baud", type=int, default=115200)
    parser.add_argument("--confirm-props-removed-no-battery", action="store_true", required=True)
    args = parser.parse_args()
    config = {"operation": "Betaflight CLI interrogation", "port": args.port, "baud": args.baud, "commands": READ_ONLY_COMMANDS, "actuation_enabled": False}
    summary, raw = interrogate(args.port, args.baud)
    record = {"schema": SCHEMA, **metadata(root_path(), config), "safety": {"props_removed_and_no_battery_confirmed": True, "write_commands_sent": False, "actuation_enabled": False}, "serial_ports": ports(), "fc": summary, "ardupilot_fit": {"status": NOT_MEASURED, "reason": "Requires the measured board target/flash result and a separately cited target-build size check; no flashing is performed by this tool."}}
    raw_path = root_path() / "artifacts" / "fc"; raw_path.mkdir(parents=True, exist_ok=True)
    path = write_artifact(root_path(), "fc", "interrogation", record)
    dump_path = path.with_name(path.stem.replace("interrogation", "raw_dump") + ".txt"); dump_path.write_text(raw, encoding="utf-8")
    print(path); print(dump_path); return 0


if __name__ == "__main__": raise SystemExit(main())
