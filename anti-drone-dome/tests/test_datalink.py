"""Test: DataLink broadcast/receive init, round trip, malformed data handling."""

import sys
import os
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from comms.datalink import DataLink


def run_tests():
    results = []

    # Test 1: Broadcaster initializes without error
    try:
        broadcaster = DataLink(role="broadcast", port=15550)
        results.append(("DataLink broadcaster initializes", True))
    except Exception as e:
        results.append(("DataLink broadcaster initializes", False, str(e)))
        _print_results(results)
        return

    # Test 2: Receiver initializes without error
    try:
        receiver = DataLink(role="receive", port=15551)
        results.append(("DataLink receiver initializes", True))
    except Exception as e:
        results.append(("DataLink receiver initializes", False, str(e)))
        broadcaster.close()
        _print_results(results)
        return

    # Test 3: Send doesn't crash (full round-trip requires two processes — verify no-crash)
    try:
        track = {
            "detected": True,
            "position_estimate": (5.0, 3.0, 7.0),
            "velocity": (1.0, -0.5, 0.2),
            "snr": 20.0,
        }
        broadcaster.send_track(track)
        results.append(("Send track completes without error", True))
    except Exception as e:
        results.append(("Send track completes without error", False, str(e)))

    # Test 4: Malformed data handled gracefully
    try:
        broadcaster.send_track({})
        broadcaster.send_track({"detected": False})
        broadcaster.send_track(None)
    except Exception as e:
        results.append(("Malformed data handled gracefully", False, str(e)))
    else:
        results.append(("Malformed data handled gracefully", True))

    broadcaster.close()
    receiver.close()
    _print_results(results)


def _print_results(results):
    print("\n=== test_datalink.py ===")
    for item in results:
        name, passed = item[0], item[1]
        detail = item[2] if len(item) > 2 else ""
        status = "PASS" if passed else "FAIL"
        print(f"  [{status}] {name}" + (f" ({detail})" if detail else ""))


if __name__ == "__main__":
    run_tests()
