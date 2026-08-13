"""Capture a reproducible Hailo bring-up record on the Pi that has the HAT+.

Run this from the repository root after committing this script.  It intentionally
records absent hardware and missing instruments as evidence rather than guessing.
"""
from __future__ import annotations

import argparse
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from bench_common import NOT_MEASURED, metadata, write_artifact

SCHEMA = "larp.hailo-bringup.v3"


def command_output(command: list[str]) -> dict[str, object]:
    """Return complete stdout/stderr even when a diagnostic command fails."""
    try:
        run = subprocess.run(command, text=True, capture_output=True, timeout=30)
        return {"command": command, "returncode": run.returncode,
                "stdout": run.stdout, "stderr": run.stderr}
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"command": command, "returncode": None, "stdout": "", "stderr": str(exc)}


def installed_version(command: list[str]) -> str:
    result = command_output(command)
    if result["returncode"] == 0:
        text = (result["stdout"] or result["stderr"]).strip()
        return text or "INSTALLED (VERSION COMMAND RETURNED NO TEXT)"
    return "NOT INSTALLED"


def first_available_version(commands: tuple[list[str], ...]) -> str:
    """Try version commands without assuming the locally installed DFC layout."""
    for command in commands:
        if shutil.which(command[0]) is not None:
            return installed_version(command)
    return "NOT INSTALLED"


def validate_artifact(record: dict) -> None:
    """Validate a record without needing Hailo hardware or its runtime."""
    required = {"schema", "schema_version", "created_utc", "git_commit", "host",
                "configuration", "measurement_status", "operator", "device_present",
                "device_pcie_visible", "commands", "versions", "idle_baseline",
                "failure_or_resolution", "limitations"}
    missing = required - set(record)
    if record.get("schema") != SCHEMA or missing:
        raise ValueError(f"invalid Hailo bring-up artifact; missing={sorted(missing)}")
    if record["measurement_status"] not in {"pass", "partial", "fail"}:
        raise ValueError("measurement_status must be pass, partial, or fail")
    required_config = {"operation", "operator", "idle_power_meter_reading_w", "resolution_note"}
    missing_config = required_config - set(record["configuration"])
    if missing_config:
        raise ValueError(f"configuration missing={sorted(missing_config)}")
    for name in ("identify", "scan", "pci_scan"):
        if name not in record["commands"]:
            raise ValueError(f"commands missing {name}")
    for name in ("hailort_cli", "hailort_python", "pcie_driver", "firmware",
                 "dataflow_compiler", "os", "python"):
        if name not in record["versions"]:
            raise ValueError(f"versions missing {name}")


def temperature_c() -> float | str:
    for candidate in (Path("/sys/class/thermal/thermal_zone0/temp"),):
        try:
            return int(candidate.read_text().strip()) / 1000.0
        except (OSError, ValueError):
            pass
    result = command_output(["vcgencmd", "measure_temp"])
    if result["returncode"] == 0:
        try:
            return float(str(result["stdout"]).split("=")[1].split("'")[0])
        except (IndexError, ValueError):
            pass
    return NOT_MEASURED


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--operator", default=os.environ.get("USER", "NOT MEASURED"))
    parser.add_argument("--idle-power-w", type=float,
                        help="Reading from an external inline power meter; omit if unavailable.")
    parser.add_argument("--resolution-note", default="NOT MEASURED",
                        help="What was fixed after a prior failed run, if applicable.")
    args = parser.parse_args()
    root = Path(__file__).resolve().parent.parent
    cli_available = shutil.which("hailortcli") is not None
    pci_scan = command_output(["lspci", "-nn"]) if shutil.which("lspci") else {
        "command": ["lspci", "-nn"], "returncode": None, "stdout": "",
        "stderr": "lspci is not installed or not on PATH"}
    identify = command_output(["hailortcli", "fw-control", "identify"]) if cli_available else {
        "command": ["hailortcli", "fw-control", "identify"], "returncode": None,
        "stdout": "", "stderr": "hailortcli is not installed or not on PATH"}
    scan = command_output(["hailortcli", "scan"]) if cli_available else {
        "command": ["hailortcli", "scan"], "returncode": None,
        "stdout": "", "stderr": "hailortcli is not installed or not on PATH"}
    device_pcie_visible = "hailo" in str(pci_scan["stdout"]).lower()
    device_present = cli_available and (identify["returncode"] == 0 or scan["returncode"] == 0)
    versions = {
        "hailort_cli": installed_version(["hailortcli", "--version"]) if cli_available else "NOT INSTALLED",
        "hailort_python": installed_version([sys.executable, "-m", "pip", "show", "hailort"]),
        "pcie_driver": installed_version(["sh", "-lc", "modinfo hailo_pci 2>/dev/null | grep '^version:'"]),
        "firmware": (str(identify["stdout"]).strip() if identify["returncode"] == 0 else NOT_MEASURED),
        "dataflow_compiler": first_available_version((["hailo", "--version"], ["hailo_dataflow_compiler", "--version"])),
        "os": platform.platform(), "python": sys.version,
    }
    status = "pass" if device_present else ("partial" if cli_available or device_pcie_visible else "fail")
    record = {"schema": SCHEMA, **metadata(root, {"operation": "hailo_bringup",
              "operator": args.operator,
              "idle_power_meter_reading_w": args.idle_power_w if args.idle_power_w is not None else NOT_MEASURED,
              "resolution_note": args.resolution_note}),
              "measurement_status": status, "operator": args.operator,
              "device_present": device_present, "device_pcie_visible": device_pcie_visible,
              "commands": {"identify": identify, "scan": scan, "pci_scan": pci_scan},
              "versions": versions,
              "idle_baseline": {"temperature_c": temperature_c(),
                                "power_draw_w": args.idle_power_w if args.idle_power_w is not None else NOT_MEASURED,
                                "power_method": "external inline meter" if args.idle_power_w is not None else NOT_MEASURED},
              "failure_or_resolution": args.resolution_note,
              "limitations": ["A missing external power meter is recorded as NOT MEASURED.",
                              "This is a bring-up record, not an inference benchmark."]}
    validate_artifact(record)
    path = write_artifact(root, "hailo", "bringup", record)
    print(f"Hailo bring-up: {status.upper()} | device present: {device_present}")
    print(f"Artifact: {path}")
    if not device_present:
        print("No usable Hailo device was detected. The artifact records diagnostics; fix the recorded issue and rerun.")
    return 0 if device_present else 2


if __name__ == "__main__":
    raise SystemExit(main())
