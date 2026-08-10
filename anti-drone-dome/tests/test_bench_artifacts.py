"""Structural checks for bench evidence contracts, independent of hardware."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from bench_camera import SCHEMA as CAMERA_SCHEMA, config_name
from bench_fc_readonly import READ_ONLY_COMMANDS, SCHEMA as FC_SCHEMA, safe_command


def test_camera_artifact_contract_constants_are_versioned():
    assert CAMERA_SCHEMA == "larp.camera-bench.v1"
    assert config_name(1920, 1080, "MJPG") == "1920x1080_mjpg"


def test_fc_interrogator_only_allows_explicit_read_queries():
    assert FC_SCHEMA == "larp.fc-interrogation.v1"
    for command in READ_ONLY_COMMANDS:
        safe_command(command)
    for command in ("save", "motor 0 2000", "set feature = ON", "resource MOTOR 1 NONE"):
        try:
            safe_command(command)
        except ValueError:
            pass
        else:
            raise AssertionError(f"unsafe command allowed: {command}")
