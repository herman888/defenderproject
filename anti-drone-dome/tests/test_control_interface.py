from integration.control_interface import ControlIntent, MavlinkBenchLog, MspBenchLog


def test_bench_control_interfaces_never_transmit():
    intent = ControlIntent(1, "track-7", "hold", "bench trace")
    for implementation in (MspBenchLog(), MavlinkBenchLog()):
        record = implementation.record_intent(intent)
        assert record["transmitted"] is False
        assert record["intent"]["source_track_id"] == "track-7"
