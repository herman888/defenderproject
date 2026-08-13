"""Hardware-independent contract checks for the Hailo bring-up artifact."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
from hailo_bringup import SCHEMA, command_output, validate_artifact


def test_hailo_bringup_schema_and_failed_command_capture():
    assert SCHEMA == "larp.hailo-bringup.v2"
    result = command_output(["command-that-does-not-exist-for-hailo-test"])
    assert result["returncode"] is None
    assert result["stderr"]


def test_hailo_bringup_artifact_schema_rejects_missing_required_values():
    record = {"schema": SCHEMA, "schema_version": 1, "created_utc": "2026-08-12T00:00:00Z",
              "git_commit": "a" * 40, "host": {}, "configuration": {}, "measurement_status": "fail",
              "operator": "tester", "device_present": False, "device_pcie_visible": False,
              "commands": {"identify": {}, "scan": {}, "pci_scan": {}},
              "versions": {name: "NOT MEASURED" for name in ("hailort_cli", "hailort_python", "pcie_driver", "firmware", "dataflow_compiler", "os", "python")},
              "idle_baseline": {}, "failure_or_resolution": "NOT MEASURED", "limitations": []}
    validate_artifact(record)
    del record["versions"]["firmware"]
    try:
        validate_artifact(record)
    except ValueError:
        pass
    else:
        raise AssertionError("artifact without firmware version was accepted")
