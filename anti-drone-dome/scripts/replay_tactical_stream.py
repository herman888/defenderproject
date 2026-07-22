"""Replay a validated AEGIS tactical JSONL recording over UDP."""

from __future__ import annotations

import argparse
import os
import sys

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
    args = parser.parse_args()
    if args.rate <= 0:
        parser.error("--rate must be positive")
    try:
        endpoint = UdpEndpoint.parse(args.udp)
        sent = replay_tactical_recording(
            args.input,
            endpoint,
            rate=args.rate,
            wait=not args.no_wait,
        )
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    print(f"Replayed {sent} validated tactical packets to {args.udp}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
