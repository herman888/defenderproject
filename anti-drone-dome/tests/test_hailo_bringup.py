"""Hardware-independent contract checks for the Hailo bring-up artifact."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
from hailo_bringup import SCHEMA, command_output


def test_hailo_bringup_schema_and_failed_command_capture():
    assert SCHEMA == "larp.hailo-bringup.v1"
    result = command_output(["command-that-does-not-exist-for-hailo-test"])
    assert result["returncode"] is None
    assert result["stderr"]
