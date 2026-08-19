# Round 0 - GTX 1650 low-memory fine-tune: interim evidence summary

**Run:** `models/finetuned/round0_1650_lowmem_unfrozen/`
**Report generated:** 2026-08-19 10:40 EDT; updated 12:05 EDT after the run was stopped.
**Status:** **RUN STOPPED at epoch 19** of a maximum 100, by operator decision (section 2).
Best epoch is 13. The run neither early-stopped nor converged - it was ended deliberately
because its result was not going to be interpretable at any epoch (section 9).

> **Claim boundary.** Every number here is *internal validation on a merged public
> dataset whose train/val split is known to leak* (see
> [`round0_data_provenance_audit.md`](round0_data_provenance_audit.md)). Nothing here is a
> field-performance, target-camera, production-readiness, or Hailo-deployment claim.

---

## 1. Run configuration and environment

### Environment

| Item | Value |
| --- | --- |
| Host | `EddieGaming`, Windows 11 (10.0.26200) |
| GPU | NVIDIA GeForce GTX 1650, 4096 MiB, driver 595.97 |
| Python | 3.12.2 (`anti-drone-dome/venv312`) |
| torch / torchvision | 2.11.0+cu128 / 0.26.0+cu128 |
| ultralytics | 8.3.151 |
| CUDA visible | Yes - `torch.cuda.is_available() == True` |
| Repo branch | `feat/pre-camera-sprint` @ `5b4257e` |

### Training configuration

| Item | Value |
| --- | --- |
| Base checkpoint | `models/yolo11n_drone.pt` (sha256 `311b8bea...3123be`), `nc=1` overridden to `nc=3` |
| Architecture | YOLO11n - 181 layers, 2,590,425 params, 6.4 GFLOPs |
| Data | `data/merged/data.yaml` - 4,476 train / 789 val images, 3 classes |
| imgsz | 640 |
| Optimizer | AdamW, `lr0=0.001`, `lrf=0.01`, `weight_decay=0.0005`, `nbs=64` |
| Epochs / patience | 100 max, early-stop patience 15 |
| Frozen layers | None (`freeze: null`) - full unfrozen fine-tune |
| Low-memory options | `workers=0`, `cache=false` (no RAM image cache) |
| AMP | **Disabled** - ultralytics AMP check fails on GTX 1650 (known NaN / zero-mAP risk) |
| Augmentation | mosaic 1.0 (`close_mosaic=10`), scale 0.9, degrees 10, translate 0.2, flipud 0.1, fliplr 0.5, mixup 0.05, copy_paste 0.1, erasing 0.4 |
| Seed / deterministic | 0 / true |

### The run is in two segments with **different batch sizes**

| Segment | Epochs | Started | Batch | Iters/epoch | Wall time/epoch |
| --- | --- | --- | --- | --- | --- |
| A - initial | 1-14 | 2026-08-19 01:29 | **8** (explicit `--batch 8`) | 560 | ~885 s |
| B - resumed | 15- | 2026-08-19 09:51:49 | **5** (`batch=-1` to AutoBatch) | 896 | ~1,170-1,220 s |

Resume command (still running, PID 13160 under PID 11492):

```
venv312\Scripts\python.exe scripts\finetune.py \
  --resume models\finetuned\round0_1650_lowmem_unfrozen\weights\last.pt \
  --workers 0 --no-cache --device 0
```

> **Confound - batch size changed mid-run.** Segment A ran at batch 8; the resume passed
> no `--batch`, so ultralytics AutoBatch re-measured free VRAM (competing with desktop
> apps already holding ~1 GB) and selected **batch 5**. Because ultralytics scales weight
> decay and gradient accumulation against `nbs=64`, epochs 15+ are **not** a clean
> continuation of epochs 1-14. This run is therefore not a controlled experiment and
> should not be used as a hyperparameter datapoint.

---

## 2. Interruption: cause identified, only partly addressed

Segment A did not fail or crash. Evidence:

- `round0_1650_lowmem_cuda.err.log` truncates mid-epoch 15 at iteration 119/560 with **no
  Python traceback** - a grep for `traceback|error|exception|out of memory|killed` returns nothing.
- Windows System event log, 2026-08-19:
  - **04:59:04 - Event 1074, User32:** `MoUsoCoreWorker.exe` (Windows Update) *initiated the
    restart of computer EDDIEGAMING*.
  - 05:00:26 Event 6006 (event log stopped), then 05:01:03 Event 6013 *system uptime is 25 seconds*.
  - **05:01:46 - Event 1074:** a second restart initiated by `TrustedInstaller.exe`.

**Cause: an unattended Windows Update reboot killed the process.** Not a training, CUDA,
memory, or thermal fault.

The checkpoint was valid (`last.pt` at epoch 14) and the resume succeeded, so restarting was
correct. **The cause itself was never addressed** - Windows Update active hours / pause were
not changed. See section 10.

### Deliberate stop at epoch 19

The run was then **terminated on purpose** at 2026-08-19 ~11:55 EDT (`taskkill` on PIDs 13160
and 11492), with roughly 13 hours of training still outstanding. The reasoning:

- Its result was **uninterpretable at any epoch** - class `drone` has no data and the
  validation split leaks, so no amount of further training would produce a readable number.
- It was **already confounded** by the batch 8 to 5 change, so it could not serve as a
  hyperparameter datapoint either.
- The only remaining argument for finishing was ultralytics' end-of-run diagnostic plots, and
  those were **regenerated from `best.pt` in about 70 seconds** by re-running validation - so
  finishing bought nothing that was not already available.
- Training was also consuming a disk with 5.4 GB free.

Both checkpoints were verified loadable after termination; neither was corrupted. Work moves to
an RTX 3060 on a different machine, where the first run will be a **fresh baseline**, not a
resume of this one (section 9).

---

## 3. Results

### Best epoch so far - **epoch 13** (segment A, batch 8)

| Metric | Value |
| --- | --- |
| precision(B) | **0.9273** |
| recall(B) | **0.6550** |
| mAP@50(B) | **0.6761** |
| mAP@50-95(B) | **0.5338** |

Epoch 13 holds `best.pt` on ultralytics fitness (`0.1*mAP50 + 0.9*mAP50-95` = 0.5482). No
later epoch beat it, including epoch 19 (fitness 0.5389), so `best.pt` was never rewritten
after 04:41:19. Checkpoint verified loadable after termination: `epoch=12` (0-indexed),
`best_fitness=0.54805`.

### Per-class breakdown - the aggregate number is misleading

Measured by re-running validation on `best.pt` after the run was stopped
(`models/finetuned/round0_1650_lowmem_valbest/`):

| Class | Val images | Val boxes | P | R | mAP@50 | mAP@50-95 |
| --- | --- | --- | --- | --- | --- | --- |
| `drone` | 0 | **0** | - | - | - | **not evaluated - no data** |
| `fpv_drone` | **9** | **19** | 0.9622 | **0.3158** | **0.3582** | **0.1740** |
| `loitering_munition` | 697 | 697 | 0.8878 | **0.9943** | **0.9939** | **0.8934** |
| **all** | 789 | 716 | 0.9250 | 0.6550 | 0.6760 | **0.5337** |

**This is the most important table in the report.** The headline 0.5337 is the average of a
class that is essentially solved and a class that is broken, and it describes neither:

- **`loitering_munition` at mAP@50 0.994 with 0.994 recall is not a success - it is a leakage
  signature.** Near-perfect recall on real-world small-target detection is not plausible. Read
  alongside the 71 shared frames and the unrecoverable session identity of the 3,954 `shahed`
  images (provenance audit, section 4), the most probable explanation is that the model is being
  tested on frames it effectively trained on.
- **`fpv_drone` is not working.** Recall 0.316 means it misses roughly two of every three FPV
  drones present. High precision (0.962) with low recall means it fires rarely and is usually
  right when it does - the failure mode is silence, not false alarms. On **9 images and 19
  boxes**, even these figures carry almost no statistical weight.
- **`drone`, the class intended for deployment, was never evaluated** because the dataset
  contains no instances of it.

Any single aggregate mAP quoted from this run - including the 0.5337 above - should be
considered uninformative. Quote the per-class rows or nothing.

### Per-epoch history (all 17 completed epochs)

| Epoch | P | R | mAP@50 | mAP@50-95 |
| --- | --- | --- | --- | --- |
| 1 | 0.9907 | 0.4912 | 0.4925 | 0.3404 |
| 2 | 0.6771 | 0.5498 | 0.5282 | 0.4092 |
| 3 | 0.9913 | 0.4957 | 0.5359 | 0.4380 |
| 4 | 0.9752 | 0.5732 | 0.5881 | 0.4700 |
| 5 | 0.6082 | 0.5498 | 0.5670 | 0.4451 |
| 6 | 0.6922 | 0.6287 | 0.5964 | 0.4744 |
| 7 | 0.9514 | 0.6024 | 0.6137 | 0.4738 |
| 8 | 0.6024 | 0.5958 | 0.5281 | 0.4407 |
| 9 | 0.7234 | 0.6459 | 0.6257 | 0.4935 |
| 10 | 0.6869 | 0.6287 | 0.6043 | 0.4825 |
| 11 | 0.7993 | 0.5997 | 0.6081 | 0.4958 |
| 12 | 0.8315 | 0.6286 | 0.6191 | 0.4712 |
| **13** | **0.9273** | **0.6550** | **0.6761** | **0.5338** |
| 14 | 0.7972 | 0.6543 | 0.6432 | 0.4839 |
| *- Windows Update reboot; resume at batch 5 -* | | | | |
| 15 | 0.7512 | 0.6287 | 0.6206 | 0.4912 |
| 16 | 0.7124 | 0.7077 | 0.6510 | 0.4938 |
| 17 | 0.7997 | 0.6550 | 0.6659 | 0.5137 |
| 18 | 0.7603 | 0.6806 | 0.6805 | 0.5173 |
| 19 | 0.9937 | 0.6508 | 0.6742 | 0.5239 |

**Early-stop status:** never triggered. Best epoch is 13; 6 epochs elapsed since, against
patience 15. The run was stopped manually at epoch 19 rather than allowed to continue.

**Metric instability:** precision swings between 0.60 and 0.99 epoch-to-epoch. This is not
noise in the ordinary sense - it is a direct consequence of the class imbalance in section 5
(`fpv_drone` has only **19** validation boxes, so a handful of detections moves the mean
metric by several tenths). Treat any single-epoch figure from this run as low-confidence.

---

## 4. Comparison against prior local fine-tune runs

| Run | Base | Batch | Cache | Best epoch | P | R | mAP@50 | mAP@50-95 | Stopped |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `finetune_20260622_200022` | `yolo11n_drone.pt` | 32 | RAM | 45 | 0.9936 | 0.7596 | 0.7879 | **0.6311** | early @ 60 |
| `finetune_20260624_123457` | `yolo11n.pt` | 16 | RAM | 69 | 0.9199 | 0.7245 | 0.7855 | 0.5795 | early @ 84 |
| **this run (in progress)** | `yolo11n_drone.pt` | 8 to 5 | none | **13** *(of 17 so far)* | 0.9273 | 0.6550 | 0.6761 | **0.5338** | still running |

**Reading this honestly:** the current run is behind both prior runs, but it is at epoch 17
while their bests were at epochs 45 and 69. The gap is **consistent with an incomplete run**,
and is *not* evidence that the low-memory configuration is worse. No conclusion about
batch 8/5 versus batch 32 should be drawn until this run stops.

### Comparability caveats

1. **The prior runs' dataset identity cannot be verified.** Both point at
   `C:\Users\aclie\OneDrive\Documents\LARP\...\data\merged\data.yaml` - a different checkout
   path from the current `Documents\Side Projects\...`. There is no dataset manifest or
   checksum for `data/merged/`, so "same data" is an assumption, not a fact.
2. **The roadmap quotes the wrong epoch.** `onboard-perception-roadmap.md` cites
   `finetune_20260622_200022` as "precision 0.958, recall 0.760, mAP@50 0.790, mAP@50-95 0.619".
   Those are the values at the **final** epoch 60. The saved `best.pt` for that run is
   **epoch 45** (0.9936 / 0.7596 / 0.7879 / 0.6311). The published numbers do not describe the
   saved artifact. Recommend correcting the roadmap.
3. Prior runs used `cache=true` and `workers=4`; this run uses neither. The data pipeline differs.

---

## 5. Data split limitations and label / data-quality warnings

Full detail in [`round0_data_provenance_audit.md`](round0_data_provenance_audit.md). Summary of
what materially affects the numbers above:

| Finding | Evidence | Effect on these metrics |
| --- | --- | --- |
| **Class `drone` has ZERO instances** | 0 boxes in train and val | The primary deployed class is untrained and unmeasured. mAP is computed over the other two classes only. |
| Extreme class imbalance | `loitering_munition` 3,954 train / 697 val; `fpv_drone` 207 / 19 | mAP is ~95% a Shahed-detection score. `fpv_drone` metrics rest on 19 boxes. |
| **71 identical source frames in both train and val** | matched by Roboflow base stem across splits | Validation is partly contaminated; mAP is optimistically biased. |
| **All 4 FPV source videos span both splits** | `Fpvkamikazedrone-*_mp4` sessions appear in train and val | Frame-level, not source-level, splitting - exactly what the roadmap forbids. |
| 178 duplicate base stems inside train | 4,476 files, 4,298 unique stems | Effective train set is smaller than stated. |
| Mixed box/segment metadata | train: 205 segments vs 4,159 boxes; val: 19 vs 716 | Segments discarded; boxes-only training is correct, but the dataset is not internally consistent. |
| 2 duplicate labels auto-removed | ultralytics warning on `images_Fpvkamikazedrone-...-14_png.rf.*` | Minor; noted for traceability. |
| Background / negative images | 453 train / 83 val empty label files | Present, but not from a curated hard-negative source (no birds / aircraft / glare set). |

**Consequence:** mAP@50-95 = 0.5338 is an *upper-biased* estimate on a contaminated split for
two classes, one of which is not the class the system is meant to deploy. It cannot be
compared to any published benchmark.

---

## 6. Model artifacts and hashes

| Artifact | Path | SHA-256 | Note |
| --- | --- | --- | --- |
| Base checkpoint | `models/yolo11n_drone.pt` | `311b8bea0a5a9f2b2dd407ade666a91831bbcb4dcd9d4b6580dbe33aac3123be` | stable |
| **Best (epoch 13)** | `models/finetuned/round0_1650_lowmem_unfrozen/weights/best.pt` | `7a2f26493130f09a31037349f2abc11accde67de1edca238e5febb76ae4eb4c4` | 16,079,841 B, mtime 2026-08-19 04:41:19 EDT |
| Last (epoch 19) | `.../weights/last.pt` | `ce79071e2ead3d341406d8bc784d94402983b27ee3f9bfab4c85f1651c03de37` | 16,080,545 B; now stable - hashed after the run was stopped |
| Prior run best | `models/finetuned/finetune_20260622_200022/weights/best.pt` | `98566edb6aeb9c89e79083ebf3397e4f716ebd9f6275edc6120d23dda90dde4d` | 5,475,098 B |
| Prior run best | `models/finetuned/finetune_20260624_123457/weights/best.pt` | `4972a321c1c56e0459ffa574e3b230263d33910a5d0d57c28306bcca53bea517` | 5,478,042 B |

`best.pt` / `last.pt` for the live run are ~16 MB because they still carry optimizer state;
ultralytics strips this at completion, yielding ~5.5 MB like the prior runs. **Re-hash after
the run ends** - the completion-time strip changes the file and therefore the hash.

Other run files present: `args.yaml`, `results.csv`, `labels.jpg`, `train_batch{0,1,2}.jpg`.

Validation diagnostics were **regenerated from `best.pt` after the stop** and live in
`models/finetuned/round0_1650_lowmem_valbest/`: `confusion_matrix.png`,
`confusion_matrix_normalized.png`, `PR_curve.png`, `P_curve.png`, `R_curve.png`,
`F1_curve.png`, and `val_batch{0,1,2}_{labels,pred}.jpg`. These were produced by a plain
validation pass, not by training, and can be reproduced at any time from the hashed `best.pt`.

### Dataset location

The dataset was copied to an external SSD at `D:/larp/data/` and verified byte-identical
against `round0_dataset_manifest.json` (aggregate
`737ba36c67a61a2c6e91f54ab177dab14515a213560656e02ae358e91b46769a`, 21,068 files). The SSD copy
has its stale ultralytics `.cache` files removed and its `data.yaml` `path:` re-pointed to
`D:/larp/data/merged`. The original under `anti-drone-dome/data/` is unchanged.

---

## 7. GPU, thermal, and latency observations

Sampled during epoch 17 (`nvidia-smi`, 2026-08-19 10:32-10:40 EDT):

| Metric | Observed |
| --- | --- |
| GPU temperature | 60-61 C |
| GPU utilisation | 53-78% |
| GPU memory used | 2,708-2,716 MiB of 4,096 MiB |
| Power draw | ~13-22 W of a 50 W cap |
| Throttle reasons | `0x0000000000000001` (GpuIdle only) - **no thermal or power throttling observed** |
| Reported train GPU_mem | 2.23 G at batch 8; 1.68 G at batch 5 |
| Iteration time | ~1.25-1.65 s/it (batch 5) |

Utilisation below 100% with `workers=0` is expected: single-threaded host-side data loading is
the bottleneck, not the GPU. Thermals are comfortable; the 4 GB VRAM ceiling, not heat, is the
binding constraint on this machine.

### Measured inference speed - training host only

From the post-stop validation pass on `best.pt` (GTX 1650, 640 px, batch 8, FP32, AMP off):

| Stage | Per image |
| --- | --- |
| preprocess | 0.8 ms |
| **inference** | **28.3 ms** |
| postprocess | 9.1 ms |
| total | ~38.2 ms (~26 fps) |

**This is a GTX 1650 desktop-GPU figure and nothing more.** It is not a Pi number, not a Hailo
number, and not an end-to-end camera-to-observation latency. It excludes capture, transport,
tracking, and telemetry. Its only legitimate use is as a sanity check that the model runs at a
plausible speed on a full-size GPU. **No onboard performance claim can be derived from it.**

---

## 8. Hailo deployment readiness - gap analysis

There are four artifacts between here and a defensible onboard claim. **Only the first exists.**

| # | Artifact | State | Evidence |
| --- | --- | --- | --- |
| 1 | PyTorch `.pt` training artifact | **EXISTS** (interim) | `best.pt`, hashed above; run still in progress |
| 2 | *Validated* model | **DOES NOT EXIST** | No frozen source-level test set; split leaks (section 5); no per-class metrics, no false-positive review, no small-target binning |
| 3 | Hailo-compiled `.hef` | **DOES NOT EXIST** | `find -iname '*.hef' -o -iname '*.onnx'` returns zero results. `artifacts/hailo/compile_20260812T230955Z.json`: `measurement_status: "BLOCKED"`, `stderr: "no Dataflow Compiler command supplied"`. No ONNX export step has been run at all. |
| 4 | Pi camera-to-observation benchmark | **DOES NOT EXIST** | All four `artifacts/hailo/bringup_*.json` records: `measurement_status: "fail"`, `device_present: false`, `hostname: EddieGaming`, note *"Windows development host; Pi 5 and Hailo AI HAT+ not present on this host."* `hailortcli` and `lspci` are not on PATH. |

### Two documentation defects found while checking this

- **`onboard-perception-roadmap.md` states "AI HAT+ 2 / Hailo-10H bring-up passed."** No
  artifact in the repository supports this. Every bring-up record is a *failure on the Windows
  host with no device attached*. Either a passing record from the Pi is missing from the repo,
  or the claim is wrong. It should not stand as written.
- **`scripts/finetune.py` docstring targets "Hailo-8L (13 TOPS)"** and cites vendor FPS figures
  ("~50-70 FPS at 640px"), while the roadmap targets **Hailo-10H / AI HAT+ 2**. The same
  docstring calls the GPU a "4GB RTX 3050"; the actual GPU is a GTX 1650. These are stale
  comments, but they are the kind a reviewer will catch.

### The next required gate

**Gate 3 cannot be attempted, and Gate 2 should not be attempted yet.** The blocking order is:

1. **Fix the data before the model.** A `.hef` compiled from a model validated on a leaked
   split just launders the leak into hardware. Gate 2 requires a source-level frozen test set.
2. **Then export ONNX and run the Hailo Dataflow Compiler on an x86_64 Linux host.** The DFC
   does not run on Windows; `hailo_compile_record.py` already records this correctly as
   `BLOCKED`. Calibration images for INT8 quantisation must come from the frozen manifest and
   be recorded.
3. **Then bench on the actual Pi 5 + AI HAT+ 2**, producing a bring-up record with
   `device_present: true` before any latency claim.

Until step 3 produces a passing record, **no onboard performance claim of any kind is
supportable**, and the roadmap's "bring-up passed" line should be corrected.

---

## 9. Conclusion

**Verdict: NOT DEPLOYABLE. Not yet a candidate.**

- The run is **incomplete** (stopped at epoch 19/100) and was **never a controlled experiment** -
  batch size changed from 8 to 5 mid-run after a Windows Update reboot.
- Its best result (mAP@50-95 **0.5337**) is **below both prior local fine-tunes** (0.6311,
  0.5795), but at a much earlier epoch, so that comparison was never meaningful either.
- **The per-class breakdown is the disqualifying evidence, not the aggregate.** The model scores
  0.994 mAP@50 on `loitering_munition` - implausibly high, and best read as a leakage signature -
  while `fpv_drone` sits at 0.316 recall on 19 boxes, and `drone` was never evaluated at all
  because no such labels exist. A single averaged number over those three states is not a
  measurement of anything.
- The **validation split is contaminated** (71 shared frames, 4 of 4 shared source videos), so
  no number computed against it can be trusted in either direction.

### Evidence that is missing

1. A source-level (video / session / location) train/val/test split with a written manifest and checksums.
2. Any training data at all for class `drone`.
3. Per-class precision/recall, a confusion matrix, false-positive review, and small-target size bins.
4. Curated hard negatives (birds, aircraft, insects, cloud, glare, empty sky).
5. Any target-camera footage - the InnoMaker UVC camera is not yet in hand.
6. An ONNX export, a Hailo `.hef`, and a Pi bench with `device_present: true`.
7. Independent confirmation that prior runs used the same dataset as this one.

### Recommended next single controlled experiment

**Do not start another training round.** The next experiment is a **frozen benchmark**, and it
is cheap, measurable, and modest in scope:

> **Build `data/manifests/round1.json` - a source-level split - and re-evaluate the existing
> checkpoints on a frozen held-out test set. Train nothing.**

Concretely:

1. Re-derive splits from `data/public/*` by **source video / screenshot session / dataset**,
   never by shuffled frame. Hold out whole sessions for test.
2. Write a manifest recording, per source: URL, licence, version, download date, image count,
   class mapping, per-file SHA-256, and split assignment.
3. Run `scripts/compare_detection_models.py` (already present) over the frozen test set for
   `yolo11n_drone.pt`, `finetune_20260622_200022/best.pt`, `finetune_20260624_123457/best.pt`,
   and this run's `best.pt` (hashed above, no further training needed).
4. Report per-class P/R/mAP plus a false-positive review.

The single sharpest thing to watch: **whether `loitering_munition` holds anywhere near 0.994
mAP@50 on a clean source-level split.** If it collapses, the leak was doing the work and every
prior number in this project needs restating. If it holds, the class really is easy and the
effort belongs entirely on `drone` and `fpv_drone`. Either answer is worth more than another
training round.

**Measurable outcome:** the delta between leaked-split mAP and clean-split mAP. That single
number tells you how much of the current 0.53-0.63 range is real. It is also the cheapest way
to find out - it needs no GPU time and no downloads.

*Only after that* is a training experiment worth running, and the first one should change a
single variable: collapse to one class (`drone`) or keep three, decided by the clean-split
per-class numbers.

---

## 10. Operational risks

| Risk | Evidence | Recommended action |
| --- | --- | --- |
| **Forced reboots kill long runs** | Two Windows Update restarts at 04:59 and 05:01 destroyed 14 epochs of work | **Carry this to the 3060.** Set Windows Update active hours or pause updates before starting any multi-hour run. Never mitigated on this host. |
| **C: drive has 5.4 GB free** | 470 GB used of 475.7 GB | Was the binding blocker on every dataset in the register. **Now largely relieved:** an external SSD (`D:`, exFAT, 772 GB free) holds the verified dataset copy and should host future datasets. |
| Batch-size drift on resume | `--batch` omitted, so AutoBatch re-selected 5 instead of 8 | Always pass an explicit `--batch`. This single omission is what made the run uninterpretable as an experiment. |
| **3060 results will not be comparable to these** | Ampere enables AMP (the 1650 fails the AMP check and trained FP32), plus more VRAM, larger batch, and `workers>0` | Treat the first 3060 run as a **new baseline**. Do not resume this checkpoint across machines; record the four changed variables explicitly. |
| Training off an external SSD | exFAT, no journaling, USB-attached | A disconnected cable kills a run. Prefer copying to internal storage for training and keeping the SSD as the canonical master; always eject cleanly. |
| Artifact hashes drift while a run is live | `last.pt` is rewritten every epoch | Hash and lock only after a run ends, via `scripts/lock_vision_model.py`. Both checkpoints here are now hashed and stable. |
