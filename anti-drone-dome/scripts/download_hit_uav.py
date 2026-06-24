"""
Download and convert HIT-UAV Infrared Thermal Dataset to YOLO format.

Source: GitHub release v1.2.1 (CC0 license, ~812 MB)
  https://github.com/suojiashun/HIT-UAV-Infrared-Thermal-Dataset/releases

The zip contains Pascal VOC XML annotations + JPEGImages.
Classes: Person, Car, Bicycle, OtherVehicle, UAV.
We keep only UAV boxes (mapped to drone class 0) and include all 2,898
images as training examples (non-UAV images = hard negatives).

Output: data/public/hit-uav/  with images/ + labels/ + data.yaml
"""

from __future__ import annotations

import shutil
import sys
import urllib.request
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
OUT_DIR   = REPO_ROOT / "data" / "public" / "hit-uav"
RAW_ZIP   = REPO_ROOT / "data" / "public_raw" / "hit-uav.zip"

DOWNLOAD_URL = (
    "https://github.com/suojiashun/HIT-UAV-Infrared-Thermal-Dataset"
    "/releases/download/v1.2.1/HIT-UAV.zip"
)
DOWNLOAD_URL_ALT = (
    "https://github.com/suojiashun/HIT-UAV-Infrared-Thermal-Dataset"
    "/releases/download/v1.2/HIT-UAV.zip"
)


def _download(url: str, dest: Path) -> bool:
    dest.parent.mkdir(parents=True, exist_ok=True)
    print(f"Downloading HIT-UAV (~812 MB) ...")
    print(f"  -> {dest}")
    try:
        downloaded = [0]
        def _progress(count, block, total):
            downloaded[0] = count * block
            mb = downloaded[0] / (1024 * 1024)
            print(f"\r  {mb:.0f} MB downloaded", end="", flush=True)
        urllib.request.urlretrieve(url, dest, reporthook=_progress)
        print()
        return True
    except Exception as exc:
        print(f"\n  Download failed: {exc}")
        if dest.exists():
            dest.unlink()
        return False


def _xml_to_yolo_uav(xml_path: Path, img_w: int, img_h: int) -> tuple[list[str], int]:
    tree = ET.parse(xml_path)
    root = tree.getroot()
    lines = []
    uav_count = 0
    for obj in root.findall("object"):
        name_el = obj.find("name")
        if name_el is None or name_el.text is None:
            continue
        if name_el.text.strip().lower() != "uav":
            continue
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
        uav_count += 1
    return lines, uav_count


def _convert(extract_root: Path, out_dir: Path) -> int:
    # Dataset is in HIT-UAV/normal_xml/ — XML annotations + JPEGImages
    normal_xml_dirs = [p for p in extract_root.rglob("normal_xml")
                       if p.is_dir() and "__MACOSX" not in p.parts]
    if not normal_xml_dirs:
        print("ERROR: Could not find normal_xml/ folder in extracted zip.")
        for p in sorted(extract_root.rglob("*"))[:30]:
            print(f"    {p.relative_to(extract_root)}")
        return 0

    normal_xml = normal_xml_dirs[0]
    img_dir = normal_xml / "JPEGImages"
    ann_dir = normal_xml / "Annotations"

    if not img_dir.exists() or not ann_dir.exists():
        print(f"ERROR: Expected {img_dir} and {ann_dir}")
        print(f"  Contents of {normal_xml}:")
        for p in normal_xml.iterdir():
            print(f"    {p.name}")
        return 0
    print(f"  Images     : {img_dir}")
    print(f"  Annotations: {ann_dir}")

    img_index = {p.stem: p for p in img_dir.rglob("*")
                 if p.suffix.lower() in {".jpg", ".jpeg", ".png"}}
    print(f"  Total images: {len(img_index)}")

    out_imgs = out_dir / "images"
    out_lbls = out_dir / "labels"
    out_imgs.mkdir(parents=True, exist_ok=True)
    out_lbls.mkdir(parents=True, exist_ok=True)

    ann_files  = sorted(ann_dir.glob("*.xml"))
    copied = skipped = uav_boxes = 0

    for xml_path in ann_files:
        stem = xml_path.stem
        img_path = img_index.get(stem)
        if img_path is None:
            skipped += 1
            continue
        shutil.copy2(img_path, out_imgs / (stem + img_path.suffix))
        lines, n = _xml_to_yolo_uav(xml_path, 640, 512)
        (out_lbls / (stem + ".txt")).write_text("\n".join(lines))
        uav_boxes += n
        copied += 1

    import yaml
    (out_dir / "data.yaml").write_text(yaml.dump({
        "path":  str(out_dir),
        "train": "images",
        "val":   "images",
        "nc":    1,
        "names": ["drone"],
    }))
    (out_dir / "classes.txt").write_text("drone\n")

    print(f"\n-- HIT-UAV conversion complete --")
    print(f"  Images    : {copied}")
    print(f"  Skipped   : {skipped}")
    print(f"  UAV boxes : {uav_boxes}  (other classes dropped)")
    print(f"  Output    : {out_dir}")
    return copied


def main() -> None:
    import argparse
    parser = argparse.ArgumentParser(description="Download and convert HIT-UAV dataset.")
    parser.add_argument("--skip-download", action="store_true",
                        help=f"Skip download; use existing zip at {RAW_ZIP}")
    parser.add_argument("--zip", default=None,
                        help="Path to an already-downloaded HIT-UAV.zip.")
    args = parser.parse_args()

    zip_path = Path(args.zip) if args.zip else RAW_ZIP
    extract_root = zip_path.parent / "hit-uav-extracted"

    if not args.skip_download and not zip_path.exists():
        ok = _download(DOWNLOAD_URL, zip_path)
        if not ok:
            print("Trying alternate URL ...")
            ok = _download(DOWNLOAD_URL_ALT, zip_path)
        if not ok:
            print("\nManual download:")
            print("  https://github.com/suojiashun/HIT-UAV-Infrared-Thermal-Dataset/releases")
            print(f"  Save HIT-UAV.zip to: {zip_path}")
            print("  Then re-run: python scripts/download_hit_uav.py --skip-download")
            sys.exit(1)

    if not zip_path.exists() and not extract_root.exists():
        print(f"ERROR: zip not found at {zip_path}")
        sys.exit(1)

    # Extract if not already done
    if not extract_root.exists():
        print(f"\nExtracting {zip_path.name} ...")
        extract_root.mkdir(parents=True)
        with zipfile.ZipFile(zip_path, "r") as zf:
            members = zf.namelist()
            total = len(members)
            for i, m in enumerate(members):
                zf.extract(m, extract_root)
                if i % 500 == 0:
                    print(f"\r  {i}/{total} files ...", end="", flush=True)
        print(f"\r  {total}/{total} files extracted.")
    else:
        print(f"Using existing extraction at {extract_root}")

    if OUT_DIR.exists():
        shutil.rmtree(OUT_DIR)

    n = _convert(extract_root, OUT_DIR)
    if n == 0:
        print("ERROR: no images converted.")
        sys.exit(1)

    shutil.rmtree(extract_root)
    print(f"\nNext: add {OUT_DIR} to merge_datasets.py --datasets ...")


if __name__ == "__main__":
    main()
