# Installation and quick start

## Requirements

- Python 3.10 or newer
- A virtual environment
- OpenGL-capable graphics for the accelerated tactical camera
- Optional NVIDIA CUDA-enabled PyTorch for PPO or YOLO acceleration

```powershell
cd anti-drone-dome
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python main.py --auto-start --render-backend opengl
```

On macOS or Linux, activate with `source .venv/bin/activate`. The legacy
`run_mac.sh` helper can reuse the adjacent `gym-pybullet-drones` environment.

## First verification

```powershell
python -m pytest -q
python main.py --auto-start --render-backend tiny
```

The Tiny Renderer path is the compatibility fallback. OpenGL accelerates the
tactical camera, but PyBullet rigid-body physics remains CPU-based.

## Optional capabilities

| Capability | Command or requirement |
|---|---|
| Cached OSM geometry | `python scripts\download_osm_map.py` |
| Rendered EO perception | `python main.py --camera-perception` |
| YOLO-in-loop perception | `python main.py --camera-model <weights>` |
| Residual PPO inference | `python main.py --ml-model <model.zip>` |
| Unreal/Cesium telemetry | `python main.py --telemetry-udp 127.0.0.1:49000` |

!!! note
    Simulation coordinates are local ENU metres. Configure only approved test
    locations before downloading OSM data.

