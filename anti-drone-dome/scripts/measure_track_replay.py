"""Measure tracking continuity from a deterministic recorded detection stream.

Input is JSONL with ``timestamp_ns``, ``tracker_id``, and optionally
``ground_truth_id``.  Missing truth labels are explicitly NOT MEASURED, never
converted into an ID-switch claim.
"""
from __future__ import annotations
import argparse
import json
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from bench_common import NOT_MEASURED, metadata, write_artifact

SCHEMA = "larp.track-replay.v1"


def metrics(rows: list[dict]) -> dict:
    """Calculate frame-wise metrics; truth-labelled rows may contain many targets."""
    if not rows:
        raise ValueError("recording has no rows")
    by_truth: dict[str, list[dict]] = {}
    for row in rows:
        if row.get("ground_truth_id") is not None:
            by_truth.setdefault(str(row["ground_truth_id"]), []).append(row)
    maintained = sum(bool(row.get("tracker_id")) for row in rows) / len(rows)
    dropout_events = 0
    duration_min = (rows[-1]["timestamp_ns"] - rows[0]["timestamp_ns"]) / 60e9
    switches = 0 if by_truth else NOT_MEASURED
    reacquire: list[float] = []
    for truth_rows in by_truth.values():
        truth_rows.sort(key=lambda row: row["timestamp_ns"])
        last_track, loss_started_ns = None, None
        for row in truth_rows:
            current = row.get("tracker_id")
            if current is None:
                if last_track is not None and loss_started_ns is None:
                    dropout_events += 1
                    loss_started_ns = row["timestamp_ns"]
                continue
            if last_track is not None and current != last_track:
                switches += 1
            if loss_started_ns is not None:
                reacquire.append((row["timestamp_ns"] - loss_started_ns) / 1e6)
                loss_started_ns = None
            last_track = current
    if not by_truth:
        dropout_events = sum(bool(previous.get("tracker_id")) and not current.get("tracker_id")
                             for previous, current in zip(rows, rows[1:]))
    return {"track_continuity_fraction": maintained,
            "dropout_events_per_minute": dropout_events / duration_min if duration_min else NOT_MEASURED,
            "id_switches": switches,
            "time_to_reacquire_ms": sum(reacquire)/len(reacquire) if reacquire else NOT_MEASURED}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True); parser.add_argument("--seed", type=int, default=20260812)
    args = parser.parse_args(); random.seed(args.seed)
    root = Path(__file__).resolve().parent.parent; source = Path(args.input)
    rows = [json.loads(line) for line in source.read_text(encoding="utf-8").splitlines() if line.strip()]
    rows.sort(key=lambda row: row["timestamp_ns"])
    record = {"schema": SCHEMA, **metadata(root, {"input": str(source), "seed": args.seed}),
              "measurement_status": "MEASURED", "metrics": metrics(rows),
              "limitations": ["Rows with ground_truth_id are grouped per truth target before dropout, switch, and reacquisition analysis.",
                              "ID switches and reacquisition require ground_truth_id in the replay stream.",
                              "This replay metric does not establish field track quality."]}
    print(write_artifact(root, "vision", "track_replay", record)); return 0


if __name__ == "__main__": raise SystemExit(main())
