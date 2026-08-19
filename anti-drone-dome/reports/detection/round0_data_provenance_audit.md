# Round 0 data provenance and split-integrity audit

**Audited:** 2026-08-19
**Scope:** `data/merged/`, `data/public/`, `scripts/merge_datasets.py`, `scripts/fetch_public_datasets.py`
**Method:** read-only inspection. **No dataset file was created, moved, modified, or deleted.**

Companion to [`round0_1650_lowmem_summary.md`](round0_1650_lowmem_summary.md).

---

## 1. Headline findings

| # | Finding | Severity |
| --- | --- | --- |
| 1 | Class `drone` - the primary deployed class - has **zero labelled instances** in the entire merged dataset | **Critical** |
| 2 | Split is **frame-level random**, not source-level: 71 identical source frames appear in both train and val | **Critical** |
| 3 | **All 4** FPV source videos have frames on both sides of the split | **Critical** |
| 4 | 95% of all boxes are one class (`loitering_munition`); `fpv_drone` has 19 validation boxes total | **High** |
| 5 | One of two source datasets (`fpv-drone-4posq`) is **absent from `SOURCES.md`** | **High** |
| 6 | No dataset manifest, no per-file checksums, no recorded merge command | **High** |
| 7 | Merge discards the upstream train/valid/test split and re-shuffles everything | **High** |
| 8 | Mixed box/segment metadata; 224 segment annotations silently dropped | Medium |
| 9 | Source-dataset provenance is unrecoverable from merged filenames (all prefixed `images_`) | Medium |

---

## 2. What is actually in `data/merged/`

`data/merged/data.yaml`:

```yaml
names: [drone, fpv_drone, loitering_munition]
nc: 3
path: .../anti-drone-dome/data/merged
train: images/train
val: images/val
```

There is **no `test:` key**. The dataset has only two splits.

### Measured contents

| Split | Images | Boxes | Empty (background) label files |
| --- | --- | --- | --- |
| train | 4,476 | 4,161 | 453 |
| val | 789 | 716 | 83 |

### Class distribution - the critical finding

| id | Class | Train boxes | Val boxes | Share of all boxes |
| --- | --- | --- | --- | --- |
| 0 | `drone` | **0** | **0** | **0.0%** |
| 1 | `fpv_drone` | 207 | 19 | 4.6% |
| 2 | `loitering_munition` | 3,954 | 697 | 95.4% |

**Class `drone` is declared in `data.yaml` and reserved as index 0, but no image anywhere in
the merged dataset carries a `drone` box.** The model therefore has an output channel it can
never learn, and ultralytics excludes the class from mAP averaging. Every reported mAP for
every run on this dataset is an average over `fpv_drone` and `loitering_munition` only.

This directly contradicts the roadmap's Round 0 instruction: *"Start with one deployed class:
`drone`."* The dataset supports the opposite - it is essentially a Shahed detector with a small
FPV side-class.

`fpv_drone` validation rests on **19 boxes**. That is the mechanical explanation for the
epoch-to-epoch precision swings of 0.60-0.99 documented in the run summary.

---

## 3. Source provenance: known, undocumented, and unverifiable

### Sources present on disk

| Directory | In `SOURCES.md`? | Licence (as recorded) | Images (train/valid/test) | Total |
| --- | --- | --- | --- | --- |
| `data/public/shahed-ubivw` | **Yes** | CC BY 4.0 | 3,256 / 930 / 465 | 4,651 |
| `data/public/fpv-drone-4posq` | **No - undocumented** | CC BY 4.0 *(from script registry only)* | 506 / 72 / 36 | 614 |

`SOURCES.md` documents **only** `shahed-ubivw`:

```
## shahed-ubivw
- URL: https://universe.roboflow.com/lerrika-vwghl/shahed-ubivw
- License: CC BY 4.0
- Images: ~4.6k
- Version: 1
- Downloaded: 2026-06-22
- Notes: Shahed-136 drone images, single class
```

`fpv-drone-4posq` is on disk and in the merged dataset, but has **no provenance record**. Its
licence and URL exist only in the `ROBOFLOW_DATASETS` dict inside
`scripts/fetch_public_datasets.py` (workspace `object-detection-aw0vm`, version 1, CC BY 4.0,
~361 images). Note the registry says ~361 images while 614 are on disk - the version actually
downloaded is not confirmed.

### The merged set is exactly these two sources

4,651 + 614 = **5,265** = 4,476 train + 789 val. The arithmetic closes exactly, so no third
source contributed and nothing was dropped at merge time.

Val fraction = 789 / 5,265 = **0.1498**, matching the script's default `--val-split 0.15`.

### Sources in the registry but NOT downloaded

`fetch_public_datasets.py` also lists `shahed-maross`, `drone-detection-rjhv3`,
`drone-dataset-6w7eq`, and `thermal-drone-dataset`. None are on disk. `drone-detection-rjhv3`
and `drone-dataset-6w7eq` are precisely the generic-`drone` sources that would fix finding 1.

### What cannot be verified

- **No checksums** for any source archive or any merged file.
- **No recorded merge command** - the `--datasets`, `--map`, `--val-split`, and `--seed` values
  actually used are not written anywhere. `--seed` defaults to 42, so the split is *reproducible
  in principle*, but only if the exact inputs and flags are known, and they are not recorded.
- **No download date** for `fpv-drone-4posq`.
- **Roboflow version pinning** is by integer version only; the underlying project can be edited
  upstream.
- Whether prior fine-tune runs used *this* dataset is unverifiable (they reference an
  OneDrive path; see the run summary, section 4).

---

## 4. Train/validation leakage - measured, not estimated

### Root cause in `scripts/merge_datasets.py`

Two design choices combine to guarantee leakage:

1. **`_find_image_label_pairs()` uses `dataset_dir.rglob("*")`** - it sweeps every image under
   the source root, which for Roboflow layout means `train/`, `valid/`, and `test/` alike. The
   upstream split is **destroyed**, including the upstream test set.
2. **The split is a shuffle of that flat pool:**

   ```python
   rng.shuffle(pairs)
   n_val = max(1, int(len(pairs) * args.val_split))
   ```

   Frames are assigned independently at random, with no notion of source video, capture
   session, scene, or location.

Roboflow exports additionally contain multiple **augmented copies of the same source frame**
under different `.rf.<hash>` suffixes. A random shuffle scatters those copies across the split.

### Measured leakage

Base stems computed by stripping the `images_` prefix and the `.rf.<hash>.jpg` suffix:

| Measure | Value |
| --- | --- |
| Train files / unique base stems | 4,476 / 4,298 (**178 intra-train duplicates**) |
| Val files / unique base stems | 789 / 785 (4 intra-val duplicates) |
| **Base stems appearing in BOTH train and val** | **71** |

Examples of frames present on both sides:

```
Fpvkamikazedrone-2026_04_21-11_22_00_02_mp4-0006_jpg
Fpvkamikazedrone-2026_04_21-11_57_09_04_mp4-0002_jpg
Fpvkamikazedrone-2026_04_21-11_59_57_05_mp4-0005_jpg
Fpvkamikazedrone-Screenshot-2026-04-21-10-39-02-71_png
```

### Source-video-level leakage: total

Grouping FPV frames by originating `.mp4`:

| Group | Train frames | Val frames | Distinct sources | **Shared across split** |
| --- | --- | --- | --- | --- |
| `fpv-video` (named `.mp4` sessions) | 61 | 13 | 4 train / 4 val | **4 of 4 (100%)** |
| `fpv-screenshot` (one screen-capture session) | 461 | 79 | 1 pool | **shared** |
| `shahed` (Roboflow hashed names) | 3,954 | 697 | not recoverable | **unknown** |

Every FPV source video contributes frames to both training and validation:

```
Fpvkamikazedrone-2026_04_21-11_22_00_02_mp4
Fpvkamikazedrone-2026_04_21-11_26_49_03_mp4
Fpvkamikazedrone-2026_04_21-11_57_09_04_mp4
Fpvkamikazedrone-2026_04_21-11_59_57_05_mp4
```

The 461 `Fpvkamikazedrone-Screenshot-*` frames are timestamped seconds apart from one recording
session (`10-38-57` through `10-47-34`), split 461/79 across train/val - adjacent frames of the
same scene on opposite sides of the split.

For the 3,954 `shahed` images, Roboflow's hashed filenames destroy session identity, so
video-level leakage **cannot be ruled out and cannot be measured**. Given the source is a
single-topic Shahed-136 collection likely built from video, the prior should be that leakage is
present there too.

### Effect

Reported validation mAP is **optimistically biased by an unknown but non-trivial margin**. The
size of that bias is currently unmeasurable - which is exactly what the recommended next
experiment is designed to quantify.

---

## 5. Other data-quality issues

### Mixed box/segment metadata

ultralytics warns on every load:

```
train: len(segments) = 205, len(boxes) = 4159
val:   len(segments) = 19,  len(boxes) = 716
```

224 polygon annotations are discarded so that boxes-only training can proceed. Training is
**correct**, but the dataset is internally inconsistent and the source of the polygons is
unrecorded.

### Duplicate labels

```
images_Fpvkamikazedrone-Screenshot-2026-04-21-10-39-40-14_png.rf.91b6c4dc...jpg: 1 duplicate labels removed
images_Fpvkamikazedrone-Screenshot-2026-04-21-10-39-40-14_png.rf.e48b653d...jpg: 1 duplicate labels removed
```

Note both are the **same source frame** under two Roboflow hashes - a concrete instance of the
augmented-duplicate mechanism described above.

### Unlabelled images become silent negatives

In `_copy_split()`, an image with no matching label file is written with an **empty** `.txt`,
i.e. treated as a background/hard-negative example:

```python
else:
    (lbl_dir / (stem + ".txt")).write_text("")   # background example
```

This is reasonable *if* the image genuinely contains no target. If a label file was merely
missed by the path-matching heuristic, a positive image is silently converted into a negative
one, actively teaching the model to suppress a real target. **536 empty label files exist
(453 train + 83 val) and none has been reviewed** to confirm which category it belongs to.

### Provenance destroyed in filenames

`_copy_split()` builds names as `f"{img_path.parent.name}_{img_path.stem}"`. For Roboflow layout
the parent directory is always `images`, so **every** merged file is prefixed `images_` and the
source dataset name is lost. Source attribution survives only accidentally, via the residual
`Fpvkamikazedrone-` string in FPV filenames.

### Class mapping is silent and lossy

`_AUTO_MAP` maps `shahed`, `kamikaze`, and `lancet` to `loitering_munition`, and `fpv`,
`racing drone`, `attack drone` to `fpv_drone`. Unmapped classes are dropped **per box** with no
count reported. The mapping actually applied to each source is not recorded anywhere.

---

## 6. Recommended Round 1 data manifest and frozen test protocol

### 6.1 Manifest: `data/manifests/round1.json`

Write it once, check it into git (the manifest, not the data), and treat it as the only
authority on what the model saw.

```json
{
  "schema": "aegis.dataset-manifest.v1",
  "manifest_id": "round1",
  "created_utc": "...",
  "git_commit": "...",
  "canonical_classes": ["drone", "fpv_drone", "loitering_munition"],
  "sources": [
    {
      "name": "shahed-ubivw",
      "url": "https://universe.roboflow.com/lerrika-vwghl/shahed-ubivw",
      "version": 1,
      "licence": "CC BY 4.0",
      "attribution_required": true,
      "downloaded_utc": "2026-06-22",
      "archive_sha256": "...",
      "image_count": 4651,
      "class_map": {"shahed": "loitering_munition"},
      "modality": "RGB",
      "split_unit": "unknown-see-limitations",
      "intended_use": "training"
    }
  ],
  "files": [
    {"path": "...", "sha256": "...", "source": "...", "split": "train",
     "split_group": "<video/session id>", "boxes": 3, "classes": [2]}
  ],
  "split_rule": {
    "unit": "source_video_or_session",
    "fractions": {"train": 0.70, "val": 0.15, "test": 0.15},
    "seed": 42,
    "assignment": "hash(split_group) - deterministic, not shuffled"
  },
  "counts": {"per_class": {}, "per_split": {}, "per_source_per_split": {}},
  "known_limitations": []
}
```

Non-negotiable fields: per-file **SHA-256**, the **`split_group`** each file belongs to, the
**exact merge command**, and a `known_limitations` array that carries findings such as "shahed
session identity unrecoverable" forward rather than quietly dropping them.

### 6.2 Splitting rule

1. **Assign whole groups, never frames.** `split_group` is the source video, screen-capture
   session, or capture location. Assignment is `hash(split_group) mod N`, so it is deterministic
   and stable when new data is added - a re-shuffle must never move existing frames across the
   boundary.
2. **Where session identity is unrecoverable** (the 3,954 `shahed` images), treat the whole
   source as one group and **assign it entirely to one split**, or exclude it from `test`. Do
   not pretend a random split over it is clean.
3. **Deduplicate by base stem before splitting.** Collapse `.rf.<hash>` augmentation copies to
   their source frame; augmented variants must follow their parent.
4. **Preserve upstream test sets** where the source defines one, rather than `rglob`-ing them
   into the pool.
5. **Reserve `test` for evaluation only.** No hyperparameter selection, no early stopping, no
   model selection touches it.

### 6.3 Frozen test protocol

- **Freeze the test set before training anything.** Record its manifest hash. Any change to the
  test set means a new manifest ID and a note explaining why - never an in-place edit.
- **Report per class, not just aggregate:** precision, recall, mAP@50, mAP@50-95 for each of
  `drone`, `fpv_drone`, `loitering_munition`, plus support counts. A class with fewer than ~100
  test boxes is reported with an explicit low-confidence marker.
- **Report per source** as well as pooled, so one dominant source cannot hide a weak one.
- **Report by target size bin** (e.g. box area under 16^2, 16-32^2, 32-96^2, over 96^2 px). Small
  targets are the deployment case; a pooled mAP hides them.
- **Review false positives explicitly:** save the top-N highest-confidence false positives as
  images and look at them. This is the single fastest way to discover the model has learned
  "sky texture" rather than "aircraft".
- **Measure on hard negatives separately:** false-positive rate per frame on a bird/aircraft/
  cloud/glare/empty-sky set, reported as its own number, never averaged into mAP.
- **Fix the confidence and NMS thresholds** in the manifest, and report the operating point used.

### 6.4 Immediate remediation priorities

| Priority | Action | Why |
| --- | --- | --- |
| 1 | Record `fpv-drone-4posq` in `SOURCES.md` | A licensed dataset is in use with no provenance record |
| 2 | Decide the class taxonomy | Training a 3-class head where class 0 has zero instances is indefensible - either acquire `drone` data or drop to the two classes that exist |
| 3 | Add `split_group` derivation + group-wise splitting to `merge_datasets.py` | Root cause of findings 2, 3, 7 |
| 4 | Preserve source name in merged filenames | `{dataset_name}_{stem}`, not `{parent_dir}_{stem}` |
| 5 | Emit a manifest from the merge script itself | Provenance recorded automatically, not by hand |
| 6 | Review the 536 empty label files | Distinguish true negatives from missed labels |
| 7 | Report dropped-box counts during class mapping | Silent loss is currently invisible |

**None of items 3-7 should be run against `data/merged/` in place.** Produce a new
`data/merged_round1/` from a manifest so the current dataset stays intact for reproducing the
in-flight run.
