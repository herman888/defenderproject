"""
Merge multiple YOLO-format datasets into a single train/val split at data/merged/.

Input:  One or more dataset folders, each with images/ + labels/ + data.yaml or classes.txt.
Output: data/merged/images/{train,val}, data/merged/labels/{train,val}, data/merged/data.yaml.

Class reconciliation: canonical classes are drone / fpv_drone / loitering_munition.
If a source dataset has unrecognised class names, the script STOPS and prints them —
re-run with --map old_name=canonical_name to resolve.
"""

from __future__ import annotations

import argparse
import random
import shutil
import sys
from collections import defaultdict
from pathlib import Path
from typing import Optional

import yaml  # PyYAML, bundled with ultralytics

REPO_ROOT   = Path(__file__).resolve().parent.parent
DATA_MERGED = REPO_ROOT / "data" / "merged"

CANONICAL_CLASSES = ["drone", "fpv_drone", "loitering_munition"]

# Auto-map obvious synonyms so common public dataset names work out of the box.
# Keys are lowercase source names → canonical name.
_AUTO_MAP: dict[str, str] = {
    "drone":              "drone",
    "uav":                "drone",
    "quadrotor":          "drone",
    "quadcopter":         "drone",
    "multirotor":         "drone",
    "dji":                "drone",
    "fpv":                "fpv_drone",
    "fpv_drone":          "fpv_drone",
    "fpv drone":          "fpv_drone",
    "racing drone":       "fpv_drone",
    "attack drone":       "fpv_drone",
    "loitering_munition": "loitering_munition",
    "loitering munition": "loitering_munition",
    "shahed":             "loitering_munition",
    "kamikaze":           "loitering_munition",
    "lancet":             "loitering_munition",
}


# ── dataset discovery ─────────────────────────────────────────────────────────

def _read_classes(dataset_dir: Path) -> list[str]:
    yaml_path = dataset_dir / "data.yaml"
    txt_path  = dataset_dir / "classes.txt"

    if yaml_path.exists():
        with yaml_path.open() as f:
            data = yaml.safe_load(f)
        names = data.get("names", [])
        if isinstance(names, dict):
            return [names[k] for k in sorted(names)]
        return list(names)

    if txt_path.exists():
        return [l.strip() for l in txt_path.read_text().splitlines() if l.strip()]

    # Fall back: infer from label files
    label_ids: set[int] = set()
    for lf in (dataset_dir / "labels").rglob("*.txt"):
        for line in lf.read_text().splitlines():
            parts = line.split()
            if parts:
                label_ids.add(int(parts[0]))
    if label_ids:
        print(f"  WARNING: no data.yaml/classes.txt in {dataset_dir.name}. "
              f"Found class ids: {sorted(label_ids)}. Treating as 'drone' x{len(label_ids)}.")
        return ["drone"] * (max(label_ids) + 1)
    return []


def _find_image_label_pairs(dataset_dir: Path) -> list[tuple[Path, Optional[Path]]]:
    """Return (image_path, label_path_or_None) pairs from a dataset folder.

    Handles two layouts:
      1. Flat:   dataset/images/ + dataset/labels/
      2. Nested: dataset/train/images/ + dataset/train/labels/ (Roboflow default)
    """
    pairs = []

    # Collect all image files under the dataset root
    for img in sorted(dataset_dir.rglob("*")):
        if img.suffix.lower() not in {".jpg", ".jpeg", ".png"}:
            continue

        # Try to find the matching label by replacing 'images' segment with 'labels'
        lbl: Optional[Path] = None
        parts = list(img.parts)
        for i, part in enumerate(parts):
            if part == "images":
                candidate_parts = parts[:i] + ["labels"] + parts[i + 1:]
                candidate = Path(*candidate_parts).with_suffix(".txt")
                if candidate.exists():
                    lbl = candidate
                    break

        # Fallback: label sits next to the image (flat layout)
        if lbl is None:
            sibling = img.with_suffix(".txt")
            if sibling.exists():
                lbl = sibling

        pairs.append((img, lbl))
    return pairs


# ── class reconciliation ──────────────────────────────────────────────────────

def _build_class_map(
    source_classes: list[str],
    user_map:       dict[str, str],
    dataset_name:   str,
) -> dict[int, int] | None:
    """
    Map source class indices → canonical class indices.
    Returns None and prints unresolved names if any class cannot be mapped.
    """
    unresolved: list[str] = []
    result: dict[int, int] = {}

    for src_id, src_name in enumerate(source_classes):
        key = src_name.lower().strip()
        canonical = user_map.get(key) or _AUTO_MAP.get(key)
        if canonical is None:
            unresolved.append(src_name)
            continue
        if canonical == "skip":
            # Explicitly skipped — boxes for this class will be dropped silently
            continue
        if canonical not in CANONICAL_CLASSES:
            print(f"  ERROR: '{src_name}' mapped to '{canonical}' which is not in canonical list: {CANONICAL_CLASSES}")
            sys.exit(1)
        result[src_id] = CANONICAL_CLASSES.index(canonical)

    if unresolved:
        print(f"\nERROR: Dataset '{dataset_name}' has unrecognised class names:")
        for name in unresolved:
            print(f"  '{name}'")
        print(f"\nRe-run with --map to resolve. Examples:")
        for name in unresolved:
            print(f"  --map \"{name}=drone\"  (or fpv_drone / loitering_munition / skip)")
        return None

    return result


def _remap_label_file(label_path: Path, class_map: dict[int, int]) -> str:
    lines_out = []
    for line in label_path.read_text().strip().splitlines():
        parts = line.split()
        if not parts:
            continue
        src_id = int(parts[0])
        dst_id = class_map.get(src_id)
        if dst_id is None:
            continue   # drop boxes for unmapped classes
        lines_out.append(f"{dst_id} " + " ".join(parts[1:]))
    return "\n".join(lines_out)


# ── split + copy ──────────────────────────────────────────────────────────────

def _copy_split(
    pairs:       list[tuple[Path, Optional[Path]]],
    class_map:   dict[int, int],
    out_root:    Path,
    split:       str,
) -> dict[int, int]:
    counts: dict[int, int] = defaultdict(int)
    img_dir = out_root / "images" / split
    lbl_dir = out_root / "labels" / split
    img_dir.mkdir(parents=True, exist_ok=True)
    lbl_dir.mkdir(parents=True, exist_ok=True)

    for img_path, lbl_path in pairs:
        # Unique filename to avoid collision across datasets
        stem = f"{img_path.parent.name}_{img_path.stem}"
        shutil.copy2(img_path, img_dir / (stem + img_path.suffix))

        if lbl_path:
            remapped = _remap_label_file(lbl_path, class_map)
            (lbl_dir / (stem + ".txt")).write_text(remapped)
            for line in remapped.splitlines():
                parts = line.split()
                if parts:
                    counts[int(parts[0])] += 1
        else:
            (lbl_dir / (stem + ".txt")).write_text("")   # background example

    return dict(counts)


# ── CLI ───────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Merge YOLO datasets into data/merged/ with unified class list and train/val split."
    )
    parser.add_argument("--datasets", nargs="+", required=True,
                        help="Paths to dataset folders (each with images/ + labels/ + data.yaml).")
    parser.add_argument("--val-split", type=float, default=0.15,
                        help="Fraction of each dataset to put in val (default: 0.15).")
    parser.add_argument("--map", nargs="*", default=[],
                        metavar="old=new",
                        help="Class name remappings, e.g. --map uav=drone quadrotor=fpv_drone")
    parser.add_argument("--seed", type=int, default=42,
                        help="Random seed for train/val split (default: 42).")
    parser.add_argument("--out", default=None,
                        help=f"Output directory (default: {DATA_MERGED})")
    args = parser.parse_args()

    # Parse --map flags
    user_map: dict[str, str] = {}
    for entry in (args.map or []):
        if "=" not in entry:
            print(f"ERROR: --map entries must be old=new, got '{entry}'")
            sys.exit(1)
        k, v = entry.split("=", 1)
        user_map[k.lower().strip()] = v.strip()

    out_root = Path(args.out) if args.out else DATA_MERGED
    rng = random.Random(args.seed)

    all_ok = True
    dataset_infos: list[tuple[Path, dict[int, int], list, list]] = []

    # ── Validate and plan all datasets before writing anything ────────────────
    for ds_str in args.datasets:
        ds_path = Path(ds_str)
        if not ds_path.is_absolute():
            ds_path = Path.cwd() / ds_path
        if not ds_path.exists():
            print(f"ERROR: Dataset not found: {ds_path}")
            all_ok = False
            continue

        print(f"\nDataset: {ds_path.name}")
        src_classes = _read_classes(ds_path)
        print(f"  Source classes: {src_classes}")

        class_map = _build_class_map(src_classes, user_map, ds_path.name)
        if class_map is None:
            all_ok = False
            continue

        pairs = _find_image_label_pairs(ds_path)
        print(f"  Image/label pairs: {len(pairs)}")

        rng.shuffle(pairs)
        n_val  = max(1, int(len(pairs) * args.val_split))
        val_p  = pairs[:n_val]
        train_p = pairs[n_val:]
        print(f"  Split: {len(train_p)} train / {len(val_p)} val")
        dataset_infos.append((ds_path, class_map, train_p, val_p))

    if not all_ok:
        print("\nAborting — fix the errors above and re-run.")
        sys.exit(1)

    # ── Write merged dataset ──────────────────────────────────────────────────
    if out_root.exists():
        shutil.rmtree(out_root)

    train_counts: dict[int, int] = defaultdict(int)
    val_counts:   dict[int, int] = defaultdict(int)

    for ds_path, class_map, train_p, val_p in dataset_infos:
        print(f"\nCopying {ds_path.name} ...")
        tc = _copy_split(train_p, class_map, out_root, "train")
        vc = _copy_split(val_p,   class_map, out_root, "val")
        for k, v in tc.items():
            train_counts[k] += v
        for k, v in vc.items():
            val_counts[k] += v

    # ── data.yaml ─────────────────────────────────────────────────────────────
    data_yaml = {
        "path":  str(out_root),
        "train": "images/train",
        "val":   "images/val",
        "nc":    len(CANONICAL_CLASSES),
        "names": CANONICAL_CLASSES,
    }
    (out_root / "data.yaml").write_text(yaml.dump(data_yaml, default_flow_style=False))

    # ── Summary ───────────────────────────────────────────────────────────────
    total_train = sum(1 for _ in (out_root / "images" / "train").iterdir())
    total_val   = sum(1 for _ in (out_root / "images" / "val").iterdir())

    print(f"""
=== Merge complete ===
  Output          : {out_root}
  Train images    : {total_train}
  Val images      : {total_val}

  Class distribution (train):""")
    for cls_id, name in enumerate(CANONICAL_CLASSES):
        print(f"    [{cls_id}] {name:<22} {train_counts.get(cls_id, 0):>5} boxes")
    print(f"""
  Class distribution (val):""")
    for cls_id, name in enumerate(CANONICAL_CLASSES):
        print(f"    [{cls_id}] {name:<22} {val_counts.get(cls_id, 0):>5} boxes")
    print(f"""
  data.yaml       : {out_root / "data.yaml"}
=====================
Next step: python scripts/finetune.py
""")


if __name__ == "__main__":
    main()
