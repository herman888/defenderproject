# ML training and datasets

## Controller strategy

APN remains the nominal controller. PPO learns bounded residual corrections for
disturbances, keeping command limits and the classical baseline in the loop.
Absolute learned actions are available only as an explicit research mode.

## Observation v2

The 21-value observation is translation-invariant and includes relative
position, relative velocity, line of sight, closing speed, track confidence,
wind, battery state, and sensor age. This avoids encoding one launch pad or map
origin into the policy.

## Train

```powershell
python scripts\train_interceptor.py `
  --steps 1000000 `
  --envs 4 `
  --checkpoint-every 100000 `
  --device auto `
  --output models\interceptor_ppo_curriculum_v2
```

Training uses vectorized workers, progressive curriculum difficulty,
checkpoints, and periodic evaluation.

## Generate an expert dataset

```powershell
python scripts\generate_training_dataset.py `
  --episodes 1000 `
  --output datasets\interceptor_expert_v2
```

The compressed dataset includes observations, APN actions, episode IDs,
scenario IDs, and a manifest with seeds, geometry, latency, outcomes, frame,
units, and validation state.

## GPU verification

```powershell
.\.venv\Scripts\python.exe -c "import torch; print(torch.__version__, torch.cuda.is_available())"
```

An NVIDIA driver does not make a CPU-only PyTorch wheel CUDA-capable. Use
`--device cuda` only after the command reports CUDA available.

