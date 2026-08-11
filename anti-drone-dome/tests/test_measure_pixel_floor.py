import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from measure_pixel_floor import PATHS, SCHEMA, iou, threshold


def test_pixel_floor_schema_and_geometry_helpers():
    assert SCHEMA == "larp.pixel-floor.v1"
    assert set(PATHS) == {"full_frame_resize", "centre_crop", "native_tiles"}
    assert iou((0, 0, 10, 10), (0, 0, 10, 10)) == 1.0
    assert iou((0, 0, 1, 1), (2, 2, 3, 3)) == 0.0


def test_threshold_returns_lowest_passing_width_or_not_measured():
    rows = [{"target_width_px": 8, "detection_rate": .4}, {"target_width_px": 12, "detection_rate": .9}]
    assert threshold(rows, .5) == 12
    assert threshold(rows, .95) == "NOT MEASURED"
