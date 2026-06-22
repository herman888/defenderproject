"""Download / locate YOLO drone detector (single-class, Hugging Face)."""

from __future__ import annotations

import urllib.request
from pathlib import Path

_MODELS_DIR = Path(__file__).resolve().parent.parent / "models"
_DRONE_FILENAME = "yolo11n_drone.pt"
_HF_REPO = "marie-kjelberg/drone-detector"
_HF_URL = f"https://huggingface.co/{_HF_REPO}/resolve/main/{_DRONE_FILENAME}"


def ensure_drone_weights() -> Path:
    """Return path to drone YOLO weights; download once on first run."""
    _MODELS_DIR.mkdir(parents=True, exist_ok=True)
    dest = _MODELS_DIR / _DRONE_FILENAME
    if dest.exists() and dest.stat().st_size > 10_000:
        return dest

    print(f"Downloading drone detector ({_DRONE_FILENAME})...", flush=True)
    try:
        from huggingface_hub import hf_hub_download

        path = hf_hub_download(
            repo_id=_HF_REPO,
            filename=_DRONE_FILENAME,
            local_dir=str(_MODELS_DIR),
        )
        return Path(path)
    except ImportError:
        pass
    except OSError:
        pass

    # Fallback: direct HTTP download.
    tmp = dest.with_suffix(".tmp")
    urllib.request.urlretrieve(_HF_URL, tmp)
    tmp.replace(dest)
    return dest
