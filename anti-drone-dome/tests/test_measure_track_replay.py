import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent; sys.path.insert(0, str(ROOT / "scripts"))
from measure_track_replay import SCHEMA, metrics


def test_track_replay_reports_truth_aware_metrics():
    rows = [{"timestamp_ns": 0, "tracker_id": "a", "ground_truth_id": "t"},
            {"timestamp_ns": 1_000_000_000, "tracker_id": None, "ground_truth_id": "t"},
            {"timestamp_ns": 2_000_000_000, "tracker_id": None, "ground_truth_id": "t"},
            {"timestamp_ns": 3_000_000_000, "tracker_id": "b", "ground_truth_id": "t"}]
    measured = metrics(rows)
    assert SCHEMA == "larp.track-replay.v1"
    assert measured["track_continuity_fraction"] == .5
    assert measured["id_switches"] == 1
    assert measured["time_to_reacquire_ms"] == 2000
