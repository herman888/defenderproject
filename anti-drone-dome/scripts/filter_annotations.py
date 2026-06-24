"""
Filter loitering_munition (class 2) annotations by bounding-box aspect ratio.

73% of the Shahed training boxes cover only the engine/propeller (portrait-shaped,
w/h < 0.8). This script removes those bad annotations, keeping only boxes where
width >= height * MIN_RATIO (i.e., box is not absurdly tall).

Applies to both train and val split in data/merged/labels/.

Usage:
    python scripts/filter_annotations.py [--min-ratio 0.8] [--dry-run]
"""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path

REPO_ROOT  = Path(__file__).resolve().parent.parent
LABEL_ROOT = REPO_ROOT / "data" / "merged" / "labels"

DEFAULT_MIN_RATIO = 0.8   # w/h — boxes narrower than this are engine-only


def filter_split(split_dir: Path, min_ratio: float, dry_run: bool) -> dict:
    stats = {"files_checked": 0, "files_changed": 0, "boxes_kept": 0, "boxes_removed": 0}

    for label_file in sorted(split_dir.glob("*.txt")):
        stats["files_checked"] += 1
        lines = label_file.read_text().splitlines()
        kept, removed = [], []

        for line in lines:
            parts = line.strip().split()
            if len(parts) < 5:
                kept.append(line)
                continue

            if parts[0] != "2":
                kept.append(line)
                stats["boxes_kept"] += 1
                continue

            w, h = float(parts[3]), float(parts[4])
            ratio = w / h if h > 0 else 0
            if ratio >= min_ratio:
                kept.append(line)
                stats["boxes_kept"] += 1
            else:
                removed.append(line)
                stats["boxes_removed"] += 1

        if removed:
            stats["files_changed"] += 1
            if not dry_run:
                label_file.write_text("\n".join(kept) + ("\n" if kept else ""))

    return stats


def main() -> None:
    parser = argparse.ArgumentParser(description="Filter engine-only Shahed annotations.")
    parser.add_argument("--min-ratio", type=float, default=DEFAULT_MIN_RATIO,
                        help=f"Minimum w/h ratio to keep a class-2 box (default: {DEFAULT_MIN_RATIO})")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print stats without modifying files")
    args = parser.parse_args()

    print(f"Filter: keep class-2 boxes where w/h >= {args.min_ratio}")
    print(f"Mode:   {'DRY RUN (no changes)' if args.dry_run else 'LIVE (files will be modified)'}")
    print()

    total = {"files_checked": 0, "files_changed": 0, "boxes_kept": 0, "boxes_removed": 0}

    for split in ["train", "val"]:
        split_dir = LABEL_ROOT / split
        if not split_dir.exists():
            print(f"  [{split}] directory not found, skipping")
            continue

        stats = filter_split(split_dir, args.min_ratio, args.dry_run)
        print(f"  [{split}] files checked: {stats['files_checked']:,}")
        print(f"  [{split}] files modified: {stats['files_changed']:,}")
        print(f"  [{split}] class-2 boxes kept:    {stats['boxes_kept']:,}")
        print(f"  [{split}] class-2 boxes removed: {stats['boxes_removed']:,}")
        print()

        for k in total:
            total[k] += stats[k]

    print(f"Total class-2 boxes removed: {total['boxes_removed']:,}")
    print(f"Total class-2 boxes kept:    {total['boxes_kept']:,}")

    if args.dry_run:
        print("\nRe-run without --dry-run to apply changes.")
    else:
        print("\nDone. Re-run merge_datasets.py is NOT needed — labels are edited in-place.")
        print("Next: python scripts/finetune.py --batch 16")


if __name__ == "__main__":
    main()
