import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

from measure_camera import CONFIGURATIONS, SCHEMA, build_record, summary_table
from measure_pipeline import METRICS, NOT_MEASURED, build_stub


def test_camera_measurement_artifact_schema_without_hardware():
    record = build_record(ROOT, "test camera", 0, 2)
    assert record["schema"] == SCHEMA
    assert record["device"]["requested_device"] == "test camera"
    assert len(CONFIGURATIONS) == 4
    assert "Configuration" in summary_table({**record, "configurations": []})


def test_pipeline_stub_keeps_absent_metrics_explicit():
    record = build_stub(ROOT)
    assert record["measurement_status"] == NOT_MEASURED
    assert set(record["metrics"]) == set(METRICS)
    assert all(value == NOT_MEASURED for value in record["metrics"].values())
