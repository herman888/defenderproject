"""Mission-record artifact paths and event recording.

`_manifest_path` pins a portability bug: a plain `os.path.relpath` produced
traversals like `..\\..\\..\\..\\..\\..\\..\\..\\..\\Documents\\...` whenever
the record directory and an artifact lived on different branches of the tree,
which breaks as soon as either one moves.

The event assertions pin the *other* direction: `record_snapshot` already
drains `state["events"]`, so callers must not also record them, or every event
lands twice.
"""

from __future__ import annotations

import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from integration.mission_record import MissionRecorder, _manifest_path  # noqa: E402


def test_artifact_inside_run_dir_is_relative(tmp_path):
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    artifact = run_dir / "telemetry.jsonl"
    artifact.write_text("{}", encoding="utf-8")
    assert _manifest_path(str(artifact), str(run_dir)) == "telemetry.jsonl"


def test_artifact_outside_run_dir_is_absolute(tmp_path):
    run_dir = tmp_path / "records" / "run"
    run_dir.mkdir(parents=True)
    elsewhere = tmp_path / "missions"
    elsewhere.mkdir()
    artifact = elsewhere / "session.acmi"
    artifact.write_text("acmi", encoding="utf-8")

    resolved = _manifest_path(str(artifact), str(run_dir))
    assert os.path.isabs(resolved)
    assert not resolved.startswith(os.pardir)
    assert os.path.isfile(resolved)


def test_nested_artifact_stays_relative(tmp_path):
    run_dir = tmp_path / "run"
    nested = run_dir / "media"
    nested.mkdir(parents=True)
    artifact = nested / "frame.png"
    artifact.write_bytes(b"x")
    resolved = _manifest_path(str(artifact), str(run_dir))
    assert not os.path.isabs(resolved)
    assert not resolved.startswith(os.pardir)


def _recorder(tmp_path):
    return MissionRecorder(
        str(tmp_path / "records"),
        mission={"intruder_type": "shahed136", "pattern": "direct"},
        hardware_profile={"id": "test", "evidence": {"status": "design-placeholder"}},
    )


def test_snapshot_records_its_events_once(tmp_path):
    """A snapshot carrying events must produce exactly that many event rows."""
    recorder = _recorder(tmp_path)
    recorder.record_snapshot({
        "mission_time": 1.5,
        "dome_status": "TRACKING",
        "events": ["Radar track acquired", "Radar track locked"],
    })
    recorder.finalize({"result": "TEST"})

    events = [
        json.loads(line)
        for line in open(
            os.path.join(recorder.run_dir, "events.jsonl"), encoding="utf-8"
        )
    ]
    assert [e["message"] for e in events] == [
        "Radar track acquired",
        "Radar track locked",
    ]
    assert all(e["mission_time_s"] == pytest.approx(1.5) for e in events)
    assert all(e["status"] == "TRACKING" for e in events)


def test_manifest_counts_match_the_files(tmp_path):
    recorder = _recorder(tmp_path)
    for step in range(5):
        recorder.record_snapshot({
            "mission_time": float(step),
            "dome_status": "MONITORING",
            "events": ["tick"] if step % 2 == 0 else [],
        })
    recorder.finalize({"result": "TEST"})

    manifest = json.load(
        open(os.path.join(recorder.run_dir, "manifest.json"), encoding="utf-8")
    )
    telemetry_lines = sum(
        1 for _ in open(
            os.path.join(recorder.run_dir, "telemetry.jsonl"), encoding="utf-8"
        )
    )
    event_lines = sum(
        1 for _ in open(
            os.path.join(recorder.run_dir, "events.jsonl"), encoding="utf-8"
        )
    )
    assert manifest["sample_count"] == telemetry_lines == 5
    assert manifest["event_count"] == event_lines == 3


def test_manifest_artifact_hashes_are_present(tmp_path):
    recorder = _recorder(tmp_path)
    recorder.record_snapshot({"mission_time": 0.0, "dome_status": "CLEAR"})
    recorder.finalize({"result": "TEST"})

    manifest = json.load(
        open(os.path.join(recorder.run_dir, "manifest.json"), encoding="utf-8")
    )
    for name in ("telemetry", "events"):
        entry = manifest["artifacts"][name]
        assert len(entry["sha256"]) == 64
        assert entry["bytes"] == os.path.getsize(
            os.path.join(recorder.run_dir, entry["path"])
        )
