"""
Convert DUT Anti-UAV Detection dataset (Pascal VOC XML) to YOLO format.

Input layout (after extracting train.zip / val.zip):
  train_extracted/train/img/   + train_extracted/train/xml/
  val_extracted/val/img/       + val_extracted/val/xml/

Output: data/public/dut-anti-uav/  with images/ + labels/ + data.yaml
Single class: UAV -> drone (class 0)
"""

from __future__ import annotations

import shutil
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
RAW_DIR   = REPO_ROOT / "data" / "public_raw" / "dut-anti-uav"
OUT_DIR   = REPO_ROOT / "data" / "public" / "dut-anti-uav"


def _convert_xml(xml_path: Path, img_w: int, img_h: int) -> list[str]:
    tree = ET.parse(xml_path)
    root = tree.getroot()
    lines = []
    for obj in root.findall("object"):
        bb = obj.find("bndbox")
        if bb is None:
            continue
        xmin = float(bb.find("xmin").text)
        ymin = float(bb.find("ymin").text)
        xmax = float(bb.find("xmax").text)
        ymax = float(bb.find("ymax").text)
        cx = (xmin + xmax) / 2 / img_w
        cy = (ymin + ymax) / 2 / img_h
        w  = (xmax - xmin) / img_w
        h  = (ymax - ymin) / img_h
        lines.append(f"0 {cx:.6f} {cy:.6f} {w:.6f} {h:.6f}")
    return lines


def _process_split(split_extracted: Path, split_name: str, out_dir: Path) -> int:
    img_src = split_extracted / split_name / "img"
    xml_src = split_extracted / split_name / "xml"

    if not img_src.exists():
        print(f"  WARNING: {img_src} not found — skipping")
        return 0

    out_imgs = out_dir / "images"
    out_lbls = out_dir / "labels"
    out_imgs.mkdir(parents=True, exist_ok=True)
    out_lbls.mkdir(parents=True, exist_ok=True)

    imgs = sorted(img_src.glob("*.jpg")) + sorted(img_src.glob("*.png"))
    converted = 0
    for img_path in imgs:
        stem = f"{split_name}_{img_path.stem}"
        shutil.copy2(img_path, out_imgs / (stem + img_path.suffix))

        xml_path = xml_src / (img_path.stem + ".xml")
        if xml_path.exists():
            try:
                import cv2
                img = cv2.imread(str(img_path))
                h, w = img.shape[:2] if img is not None else (412, 550)
            except Exception:
                w, h = 550, 412
            lines = _convert_xml(xml_path, w, h)
            (out_lbls / (stem + ".txt")).write_text("\n".join(lines))
        else:
            (out_lbls / (stem + ".txt")).write_text("")
        converted += 1

    return converted


def main() -> None:
    if OUT_DIR.exists():
        shutil.rmtree(OUT_DIR)
    OUT_DIR.mkdir(parents=True)

    total = 0
    for split_name, extracted_folder in [
        ("train", RAW_DIR / "train_extracted"),
        ("val",   RAW_DIR / "val_extracted"),
    ]:
        if not extracted_folder.exists():
            print(f"  Skipping {split_name} — {extracted_folder} not found")
            continue
        print(f"Converting {split_name} split ...")
        n = _process_split(extracted_folder, split_name, OUT_DIR)
        print(f"  {n} images converted")
        total += n

    import yaml
    (OUT_DIR / "data.yaml").write_text(yaml.dump({
        "path":  str(OUT_DIR),
        "train": "images",
        "val":   "images",
        "nc":    1,
        "names": ["drone"],
    }))
    (OUT_DIR / "classes.txt").write_text("drone\n")

    print(f"\nDone. {total} total images -> {OUT_DIR}")
    print(f"Next: add {OUT_DIR} to merge_datasets.py --datasets ...")


if __name__ == "__main__":
    main()
