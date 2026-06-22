# Training Setup — RTX 3080 / 32GB RAM

## 1. Pull the repo
```powershell
git pull origin main
cd anti-drone-dome
```

## 2. Install dependencies
```powershell
pip install torch torchvision --index-url https://download.pytorch.org/whl/cu126
pip install ultralytics opencv-python supervision pyyaml
```

Verify GPU:
```powershell
python -c "import torch; print(torch.cuda.get_device_name(0))"
```

## 3. Re-download datasets (gitignored — must re-fetch)
```powershell
python -m venv venv-dataprep
.\venv-dataprep\Scripts\Activate.ps1
pip install roboflow pyyaml requests
$env:ROBOFLOW_API_KEY = "your_key_here"   # from .env on old laptop
python scripts\fetch_public_datasets.py --roboflow-only
deactivate
```

## 4. Merge datasets
```powershell
python scripts\merge_datasets.py `
  --datasets data\public\shahed-ubivw data\public\fpv-drone-4posq `
  --map "1=loitering_munition" "airplane=fpv_drone" "antiaircraft=skip" "soldier=skip" "vehicle=skip"
```

Expected output:
- ~4,476 train images
- 3,954 loitering_munition boxes
- 207 fpv_drone boxes

## 5. Update finetune.py for 3080
Open `scripts/finetune.py` and change:
```python
batch=8    ->  batch=32
workers=2  ->  workers=8
```
`cache=True` is already set — it will now actually fit in 32GB RAM.

## 6. Train
```powershell
# Keep laptop awake
powercfg /change standby-timeout-ac 0
powercfg /change monitor-timeout-ac 0

python scripts\finetune.py
```

Training takes ~20-30 min on a 3080 (vs ~2hr on GTX 1650).

## 7. Results
After training, find outputs in:
```
models\finetuned\finetune_<timestamp>\
  weights\best.pt          <- use this for inference
  results.png              <- loss + mAP curves (hero shot for video)
  confusion_matrix_normalized.png
  val_batch0_pred.jpg      <- sample predictions
```

## 8. Test the fine-tuned model on camera
```powershell
python scripts\camera_detect.py --drone-only --model models\finetuned\<run>\weights\best.pt
```

Should now show `fpv_drone` and `loitering_munition` labels instead of generic `drone`.
