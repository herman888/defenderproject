"""Replay a validated AEGIS tactical JSONL recording over UDP."""

from __future__ import annotations

import argparse
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from integration.tactical_stream import (  # noqa: E402
    UdpEndpoint,
    replay_tactical_recording,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, help="Tactical JSONL recording")
    parser.add_argument(
        "--udp",
        default="127.0.0.1:49000",
        metavar="HOST:PORT",
        help="Replay destination (default: 127.0.0.1:49000)",
    )
    parser.add_argument(
        "--rate",
        type=float,
        default=1.0,
        help="Mission-time playback multiplier (default: 1.0)",
    )
    parser.add_argument(
        "--no-wait",
        action="store_true",
        help="Send packets immediately while preserving their timestamps",
    )
    parser.add_argument(
        "--loop",
        type=int,
        default=1,
        metavar="N",
        help=(
            "Replay the recording N times; 0 repeats indefinitely. A single "
            "mission is only a few seconds of playback, so a continuous "
            "display needs this (default: 1)"
        ),
    )
    parser.add_argument(
        "--loop-gap",
        type=float,
        default=1.5,
        metavar="SECONDS",
        help="Pause between repeats, so the final state is readable (default: 1.5)",
    )
    args = parser.parse_args()
    if args.rate <= 0:
        parser.error("--rate must be positive")
    if args.loop < 0:
        parser.error("--loop must be zero or positive")

    try:
        endpoint = UdpEndpoint.parse(args.udp)
        total = 0
        passes = 0
        while args.loop == 0 or passes < args.loop:
            total += replay_tactical_recording(
                args.input,
                endpoint,
                rate=args.rate,
                wait=not args.no_wait,
            )
            passes += 1
            if args.loop == 0 or passes < args.loop:
                time.sleep(max(args.loop_gap, 0.0))
    except KeyboardInterrupt:
        print(f"\nStopped after {passes} pass(es), {total} packets.")
        return 0
    except (OSError, ValueError) as exc:
        parser.error(str(exc))

    print(
        f"Replayed {total} validated tactical packets to {args.udp} "
        f"over {passes} pass(es)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
