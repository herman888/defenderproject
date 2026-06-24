"""
Fetch public anti-drone datasets. Manual-download sources print instructions;
Roboflow sources are downloaded automatically with a valid API key.

Output: data/public/<dataset-name>/ in YOLO format; data/public/SOURCES.md provenance log.

IMPORTANT — run this script in a dedicated venv (venv-dataprep), NOT the main project venv.
Roboflow's pip package always installs opencv-python-headless as a dependency, which will
break cv2.imshow in your main environment. The venv-dataprep is disposable; the downloaded
datasets land in data/public/ which the main venv reads directly.

Setup (one-time):
  python -m venv venv-dataprep
  venv-dataprep\\Scripts\\activate
  pip install roboflow pyyaml requests
  $env:ROBOFLOW_API_KEY = "your_key_here"
  python scripts/fetch_public_datasets.py
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime
from pathlib import Path

REPO_ROOT   = Path(__file__).resolve().parent.parent
PUBLIC_DIR  = REPO_ROOT / "data" / "public"
SOURCES_MD  = PUBLIC_DIR / "SOURCES.md"

# ── Roboflow dataset definitions ──────────────────────────────────────────────

ROBOFLOW_DATASETS = {
    "shahed-ubivw": {
        "workspace": "lerrika-vwghl",
        "project":   "shahed-ubivw",
        "version":   1,
        "license":   "CC BY 4.0",
        "images":    "~4.6k",
        "notes":     "Shahed-136 drone images, single class",
        "url":       "https://universe.roboflow.com/lerrika-vwghl/shahed-ubivw",
    },
    "shahed-maross": {
        "workspace": "maross",
        "project":   "shahed",
        "version":   1,
        "license":   "CC BY 4.0",
        "images":    "~12.3k",
        "notes":     "Multi-class: Shahed-136, Lancet, KARGU loitering munitions",
        "url":       "https://universe.roboflow.com/maross/shahed",
    },
    "fpv-drone-4posq": {
        "workspace": "object-detection-aw0vm",
        "project":   "fpv-drone-4posq",
        "version":   1,
        "license":   "CC BY 4.0",
        "images":    "~361",
        "notes":     "FPV racing/attack drone, single class",
        "url":       "https://universe.roboflow.com/object-detection-aw0vm/fpv-drone-4posq",
    },
    # ── Round 2: fills the 'drone' class (had 0 training examples in round 1) ──
    "drone-detection-rjhv3": {
        "workspace": "myspace-5b8mg",
        "project":   "drone-detection-rjhv3",
        "version":   2,
        "license":   "CC BY 4.0",
        "images":    "~3.4k",
        "notes":     "Generic drone detection, multiple drone types, daylight",
        "url":       "https://universe.roboflow.com/myspace-5b8mg/drone-detection-rjhv3",
    },
    "drone-dataset-6w7eq": {
        "workspace": "artificial-intelligence-nzz1a",
        "project":   "drone-dataset-6w7eq",
        "version":   1,
        "license":   "CC BY 4.0",
        "images":    "~1.3k",
        "notes":     "Generic consumer/commercial drone images",
        "url":       "https://universe.roboflow.com/artificial-intelligence-nzz1a/drone-dataset-6w7eq",
    },
    "thermal-drone-dataset": {
        "workspace": "new-workspace-at15m",
        "project":   "thermal_drone_dataset",
        "version":   1,
        "license":   "CC BY 4.0",
        "images":    "~600",
        "notes":     "Thermal/IR drone images — low light and night detection",
        "url":       "https://universe.roboflow.com/new-workspace-at15m/thermal_drone_dataset",
    },
}

# ── FPV dataset candidates (for user to pick from) ───────────────────────────
# Search: universe.roboflow.com/search?q=class%3Afpv
# Updated: 2026-06-22

FPV_CANDIDATES = [
    {
        "workspace": "object-detection-aw0vm",
        "project":   "fpv-drone-4posq",
        "version":   1,
        "images":    361,
        "license":   "CC BY 4.0",
        "url":       "https://universe.roboflow.com/object-detection-aw0vm/fpv-drone-4posq",
        "notes":     "Specified baseline; mix of FPV frames, single class",
    },
    {
        "workspace": "mobilin228s",
        "project":   "fpv-drone",
        "version":   1,
        "images":    500,
        "license":   "CC BY 4.0",
        "url":       "https://universe.roboflow.com/mobilin228s/fpv-drone",
        "notes":     "500 images; confirm slug at URL before running — workspace slug may differ",
    },
    {
        "workspace": "new-workspace-at15m",
        "project":   "thermal_drone_dataset",
        "version":   1,
        "images":    600,
        "license":   "CC BY 4.0",
        "url":       "https://universe.roboflow.com/new-workspace-at15m/thermal_drone_dataset",
        "notes":     "Thermal/IR drone images — directly relevant for InnoMaker night mode",
    },
    {
        "workspace": "military-drone",
        "project":   "drone_mil-u8fqk",
        "version":   1,
        "images":    800,
        "license":   "CC BY 4.0",
        "url":       "https://universe.roboflow.com/military-drone/drone_mil-u8fqk",
        "notes":     "Military drone detection; may include loitering munition imagery",
    },
]


# ── manual-download sources ───────────────────────────────────────────────────

def _print_manual_instructions() -> None:
    print("""
=== MANUAL DOWNLOAD REQUIRED -- 2 datasets ===

[1] DUT Anti-UAV  (visible light + IR, MIT licence, ~10k images)
  Paper   : https://arxiv.org/abs/2306.15767
  GitHub  : https://github.com/wangdongdut/DUT-Anti-UAV
  Download: Google Drive link is in the repo README
            (README -> "Dataset Download" section)

  Steps:
    1. Open the Google Drive link from the README
    2. Download the zip(s) and extract to:
         data/public_raw/dut-anti-uav/
    3. Run the converter:
         python scripts/convert_dut.py

[2] Anti-UAV RGB+IR  (paired RGB/IR videos, ICCV workshop dataset)
  Paper   : https://arxiv.org/abs/2101.08466
  GitHub  : https://github.com/ZhaoJ9014/Anti-UAV
  Download: Google Drive  (link in README -> "Dataset")
            Baidu Drive   (password: sagx)

  Steps:
    1. Download from Google Drive or Baidu and extract to:
         data/public_raw/anti-uav/
    2. Run the converter:
         python scripts/convert_antiuav.py
""")


# ── FPV candidate selector ────────────────────────────────────────────────────

def _print_fpv_candidates() -> None:
    print("""
=== FPV DATASET CANDIDATES -- pick one to add ===

Verify each URL in a browser before running -- Roboflow workspace/project
slugs can change. Re-run with --fpv <index> once you've confirmed.
""")
    for i, c in enumerate(FPV_CANDIDATES):
        print(f"  [{i}] {c['workspace']}/{c['project']}  v{c['version']}")
        print(f"       {c['images']} images  |  {c['license']}")
        print(f"       {c['url']}")
        print(f"       {c['notes']}")
        print()
    print("Re-run with:  python scripts/fetch_public_datasets.py --fpv 0")
    print("          or: python scripts/fetch_public_datasets.py --fpv 2  (thermal IR)")


# ── Roboflow download ─────────────────────────────────────────────────────────

def _roboflow_download(key: str, name: str, meta: dict, out_dir: Path) -> bool:
    try:
        from roboflow import Roboflow
    except ImportError:
        print("ERROR: roboflow not installed. Run: pip install roboflow")
        return False

    out_dir.mkdir(parents=True, exist_ok=True)
    print(f"\nDownloading {name} from Roboflow ...", flush=True)
    try:
        rf      = Roboflow(api_key=key)
        project = rf.workspace(meta["workspace"]).project(meta["project"])
        version = project.version(meta["version"])
        version.download("yolov8", location=str(out_dir), overwrite=True)
    except Exception as exc:
        print(f"  ERROR: {exc}")
        return False

    print(f"  Saved to {out_dir}")
    return True


# ── SOURCES.md ────────────────────────────────────────────────────────────────

def _append_source(name: str, meta: dict, version: int | None = None) -> None:
    PUBLIC_DIR.mkdir(parents=True, exist_ok=True)
    entry = f"""
## {name}

- **URL**: {meta.get('url', 'manual')}
- **License**: {meta.get('license', 'unknown')}
- **Images**: {meta.get('images', 'unknown')}
- **Version**: {version or meta.get('version', 'n/a')}
- **Downloaded**: {datetime.now().strftime('%Y-%m-%d')}
- **Notes**: {meta.get('notes', '')}
"""
    with SOURCES_MD.open("a") as f:
        if SOURCES_MD.stat().st_size == 0:
            f.write("# Dataset Provenance\n\nAuto-generated by fetch_public_datasets.py\n")
        f.write(entry)


# ── CLI ───────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Fetch public anti-drone datasets. Roboflow sources require ROBOFLOW_API_KEY."
    )
    parser.add_argument("--roboflow-only", action="store_true",
                        help="Skip manual-download instructions, only run Roboflow pulls.")
    parser.add_argument("--fpv", type=int, default=None, metavar="INDEX",
                        help="FPV candidate index to download (see --list-fpv). "
                             "If omitted, fpv-drone-4posq (index 0) is downloaded by default.")
    parser.add_argument("--list-fpv", action="store_true",
                        help="Print FPV dataset candidates and exit.")
    parser.add_argument("--skip-shahed", action="store_true",
                        help="Skip Shahed dataset downloads.")
    parser.add_argument("--round2", action="store_true",
                        help="Download round-2 datasets: generic drone + thermal IR (fills 'drone' class).")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print what would be downloaded without doing it.")
    args = parser.parse_args()

    if args.list_fpv:
        _print_fpv_candidates()
        return

    # ── API key check ──────────────────────────────────────────────────────────
    api_key = os.environ.get("ROBOFLOW_API_KEY", "").strip()
    if not api_key:
        print("""
ERROR: ROBOFLOW_API_KEY not set.

To get your key:
  1. Go to https://app.roboflow.com
  2. Settings → Roboflow API → copy your Private API Key

Then set it:
  Windows PowerShell:
    $env:ROBOFLOW_API_KEY = "your_key_here"
    python scripts/fetch_public_datasets.py

  Or permanently via System → Environment Variables → New user variable.
""")
        sys.exit(1)

    if not args.roboflow_only:
        _print_manual_instructions()

    if args.dry_run:
        print("DRY RUN — no downloads will happen.")

    # ── Roboflow: Shahed datasets ──────────────────────────────────────────────
    if not args.skip_shahed:
        for name, meta in [
            ("shahed-ubivw", ROBOFLOW_DATASETS["shahed-ubivw"]),
            ("shahed-maross", ROBOFLOW_DATASETS["shahed-maross"]),
        ]:
            out = PUBLIC_DIR / name
            if args.dry_run:
                print(f"  Would download: {meta['workspace']}/{meta['project']} → {out}")
                continue
            if _roboflow_download(api_key, name, meta, out):
                _append_source(name, meta)

    # ── Roboflow: FPV dataset ──────────────────────────────────────────────────
    fpv_idx = args.fpv if args.fpv is not None else 0
    if fpv_idx >= len(FPV_CANDIDATES):
        print(f"ERROR: --fpv index {fpv_idx} out of range. Run --list-fpv to see options.")
        sys.exit(1)

    fpv = FPV_CANDIDATES[fpv_idx]
    fpv_name = fpv["project"]
    fpv_out  = PUBLIC_DIR / fpv_name

    if fpv_idx != 0:
        print(f"\nSelected FPV dataset [{fpv_idx}]: {fpv['workspace']}/{fpv['project']}")
        print(f"Verify the URL is still valid: {fpv['url']}")
    if args.dry_run:
        print(f"  Would download FPV: {fpv['workspace']}/{fpv['project']} → {fpv_out}")
    else:
        if _roboflow_download(api_key, fpv_name, fpv, fpv_out):
            _append_source(fpv_name, fpv)

    # ── Round 2: generic drone + thermal datasets ──────────────────────────────
    if args.round2:
        print("\n── Round 2 datasets (fills 'drone' class + thermal IR) ──────────")
        for name in ("drone-detection-rjhv3", "drone-dataset-6w7eq", "thermal-drone-dataset"):
            meta = ROBOFLOW_DATASETS[name]
            out  = PUBLIC_DIR / name
            if args.dry_run:
                print(f"  Would download: {meta['workspace']}/{meta['project']} → {out}")
                continue
            if _roboflow_download(api_key, name, meta, out):
                _append_source(name, meta)

    print(f"\nSources log: {SOURCES_MD}")
    print("Next: python scripts/convert_dut.py  (after manual DUT download)")
    print("      python scripts/convert_antiuav.py  (after manual Anti-UAV download)")
    print(f"      python scripts/merge_datasets.py --datasets {PUBLIC_DIR}/shahed-ubivw ...")


if __name__ == "__main__":
    main()
