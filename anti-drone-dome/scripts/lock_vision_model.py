"""Checksum-lock a detector artifact into an AEGIS vision-model manifest."""

from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from integration.vision_model import lock_vision_model_artifact


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--artifact", required=True)
    args = parser.parse_args()
    locked = lock_vision_model_artifact(args.manifest, args.artifact)
    print(json.dumps({
        "model_id": locked["model_id"],
        "artifact": locked["artifact"],
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
