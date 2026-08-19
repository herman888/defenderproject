# Candidate datasets for Round 1 and beyond

**Compiled:** 2026-08-19
**Status: RESEARCH ONLY. Nothing here has been downloaded.**

Every entry was checked against the dataset's official project page, original paper, or
authoritative repository. Where a licence could not be confirmed from an authoritative source,
that is stated rather than guessed.

> **Hard precondition - disk space.** `C:` currently has **5.5 GB free** (470.2 GB used). The
> project rule requires at least 25 GB free *after* estimating download and extraction size.
> **No dataset below may be downloaded until that is resolved.** Several are far larger than
> the entire free space available.

---

## 1. Summary table

| Dataset | Modality | Size | Licence | Intended use here | Download blocked by |
| --- | --- | --- | --- | --- | --- |
| DUT Anti-UAV | RGB | 10k images + 20 videos | Apache-2.0 (repo label) | **Training + evaluation** | disk space |
| Anti-UAV410 | Thermal IR | 410 videos, 438k boxes | **Not stated** | Evaluation (IR only) | licence unclear + disk |
| Anti-UAV (CVPR challenge) | RGB + IR | multi-modal | Challenge terms | Evaluation | terms + disk |
| SynDroneVision | Synthetic RGB | **~900 GB** | CC BY 4.0 | Augmentation only | **size** - infeasible |
| Drone-vs-Bird (WOSDETC) | RGB video | multi-year | Non-commercial + signed DUA | **Hard negatives** | signed agreement |
| SWIMSEG / SWINSEG | RGB sky/cloud | 1,013 + 115 images | Research use, cite | Hard negatives | verify terms |
| Target-camera footage | RGB + IR | to be collected | Own data | **Test set - the only valid one** | camera not yet in hand |

---

## 2. DUT Anti-UAV

| Field | Value |
| --- | --- |
| **Source** | https://github.com/wangdongdut/DUT-Anti-UAV |
| **Paper** | Zhao et al., *Vision-based Anti-UAV Detection and Tracking*, IEEE T-ITS 2022 - https://arxiv.org/pdf/2205.10851 |
| **Licence** | **Apache-2.0** per the repository label. Note: several secondary summaries claim MIT; the repository itself indicates Apache-2.0. **Re-verify the LICENSE file at download time** and record which was actually in force. |
| **Modality** | RGB (visible) |
| **Content** | Detection subset ~10,000 images with per-image annotations; tracking subset 20 videos (short- and long-term sequences) with `groundtruth.txt` per sequence. Manually annotated. |
| **Distribution** | Google Drive and Baidu links in the repo README; detection split into train / val / test archives. |
| **Citation** | Required (IEEE T-ITS 2022). |
| **Intended use** | **Training and evaluation.** This is the highest-value addition: it supplies generic `drone`-class imagery, which the current merged dataset entirely lacks. |
| **Why it matters here** | Directly fixes the zero-instance `drone` class documented in the provenance audit. |
| **Split note** | The tracking subset is video-based, so it yields genuine `split_group` identities - use whole sequences as split units, never frames. Its upstream detection train/val/test split should be **preserved**, not re-shuffled. |
| **Repo readiness** | `scripts/convert_dut.py` and `scripts/convert_dut_detection.py` already exist. |

---

## 3. Anti-UAV410 (thermal infrared benchmark)

| Field | Value |
| --- | --- |
| **Source** | https://github.com/HwangBo94/Anti-UAV410 |
| **Paper** | Huang et al., *Anti-UAV410: A Thermal Infrared Benchmark and Customized Scheme for Tracking Drones in the Wild*, IEEE TPAMI 2023 - https://dl.acm.org/doi/abs/10.1109/TPAMI.2023.3335338 |
| **Licence** | **NOT STATED on the official repository.** No licence file or usage terms were found. **Treat as all-rights-reserved until the authors confirm.** Do not redistribute, and do not use in anything external-facing without written permission. |
| **Modality** | **Thermal infrared only** - not RGB. Commonly mislabelled "RGB/IR"; the RGB-T multi-modal data belongs to the separate Anti-UAV challenge set (section 4). |
| **Content** | 410 sequences, 438k+ manually annotated boxes, average 1,069 frames per video. Official split: 200 train / 90 val / 120 test. |
| **Small-target profile** | 93.7% of targets are 32x32 px or smaller; mean target ~18x18 px, ~0.02% of frame area. |
| **Intended use** | **Evaluation of the IR/night path only.** Not for the RGB training mix - the sensor statistics differ fundamentally. |
| **Why it matters here** | The most credible available proxy for the small-target regime, and the InnoMaker camera has an IR-Cut night mode that will eventually need an IR benchmark. |
| **Blocker** | Licence must be clarified **before download**, not after. |
| **Repo readiness** | `scripts/convert_antiuav.py` exists. |

---

## 4. Anti-UAV challenge benchmark (RGB + IR)

| Field | Value |
| --- | --- |
| **Source** | https://anti-uav.github.io/ and https://github.com/ZhaoJ9014/Anti-UAV |
| **Paper** | Jiang et al., *Anti-UAV: A Large Multi-Modal Benchmark for UAV Tracking* - https://arxiv.org/pdf/2101.08466 |
| **Licence** | Governed by challenge participation terms; **read the current edition's terms before download.** Not a blanket open licence. |
| **Modality** | Multi-modal - paired visible + thermal infrared sequences. |
| **Intended use** | **Evaluation**, particularly for the RGB-vs-IR comparison the roadmap will eventually need. |
| **Caution** | This is a *tracking* benchmark. Its protocol and metrics are not detection mAP; do not blend its numbers with detector metrics. |

---

## 5. SynDroneVision (synthetic)

| Field | Value |
| --- | --- |
| **Source** | https://zenodo.org/records/13360116 |
| **Paper** | Lenhard et al., WACV 2025 - https://arxiv.org/abs/2411.05633 / [CVF open access](https://openaccess.thecvf.com/content/WACV2025/papers/Lenhard_SynDroneVision_A_Synthetic_Dataset_for_Image-Based_Drone_Detection_WACV_2025_paper.pdf) |
| **Licence** | **CC BY 4.0** - redistribution and reuse permitted with attribution. Citation of the WACV 2025 paper requested. |
| **Modality** | Synthetic RGB, 2560x1489, generated in Unreal Engine 5.0 + Colosseum. |
| **Content** | 140,038 annotated images (131,238 train / 8,800 val / 4,000 test); ~7% background frames with no drone. YOLO-format labels. |
| **Size** | **~900 GB total** - train ~683 GB (10 parts), val ~55.2 GB, test ~26.5 GB, **labels only ~39.4 MB**. |
| **Intended use** | **Augmentation only.** The roadmap already states synthetic imagery must never be the final test set, and that rule holds. |
| **Feasibility** | **Not downloadable on this machine.** Even the smallest image archive (26.5 GB) exceeds total free disk space by ~5x. If pursued later, fetch the 39 MB label archive first to inspect class balance and scale distribution, then take a single training part only. |
| **Recommendation** | **Defer.** Real target-camera footage closes a larger evidence gap per GB than synthetic breadth does. |

---

## 6. Hard-negative sources

The current dataset has 536 empty-label images but **no curated hard negatives**. A drone
detector that has never seen a bird will confidently call a bird a drone, and nothing in the
present evaluation would reveal it.

### 6.1 Drone-vs-Bird Detection Challenge (WOSDETC) - highest value

| Field | Value |
| --- | --- |
| **Source** | https://wosdetc.wordpress.com/challenge/ , annotations at https://github.com/wosdetc/challenge |
| **Paper** | Coluccia et al., *The Drone-vs-Bird Detection Grand Challenge at ICASSP 2023*, IEEE - https://ieeexplore.ieee.org/document/10475518/ ; earlier review in [Sensors 21(8):2824](https://www.mdpi.com/1424-8220/21/8/2824) |
| **Licence** | **Open to the research community for non-commercial purposes only.** Access requires emailing `wosdetc@googlegroups.com` and **signing a data usage agreement**. |
| **Modality** | RGB video, real outdoor scenes, moving cameras, birds flying in-frame alongside UAVs. |
| **Intended use** | **Hard-negative testing** - the single most relevant source for the bird/drone confusion case. Also usable for training if the DUA permits. |
| **Blocker** | Signed agreement required. This is a **person-in-the-loop step, not a download** - start the request early, and confirm the non-commercial terms match this project's intent before signing. |

### 6.2 Sky and cloud imagery

| Field | Value |
| --- | --- |
| **Source** | SWIMSEG (daytime) and SWINSEG (nighttime), Nanyang Technological University; SWINSEG via [IEEE DataPort](https://ieee-dataport.org/documents/singapore-whole-sky-nighttime-image-segmentation-database) |
| **Papers** | Dev et al., [*Color-based Segmentation of Sky/Cloud Images*](https://arxiv.org/abs/1606.03669); Dev et al., [*Nighttime sky/cloud image segmentation*](https://arxiv.org/pdf/1705.10583) |
| **Licence** | Research use with citation; **confirm exact terms on the IEEE DataPort record before download.** |
| **Modality** | Ground-based whole-sky RGB - 1,013 daytime patches (SWIMSEG) and 115 nighttime (SWINSEG), captured by the WAHRSIS sky imager over 12 months. |
| **Size** | Small - well within available disk space. |
| **Intended use** | **Hard negatives**: cloud edges, glare, and empty sky. These are target-free by construction, so they need no new labelling - each becomes an empty label file. |
| **Caveat** | Fixed upward-looking camera in one location (Singapore). Good for cloud/glare texture, not a substitute for varied backgrounds. |

### 6.3 Still needed, no authoritative source selected yet

| Negative class | Status |
| --- | --- |
| Manned aircraft at distance | No suitable dataset identified. FGVC-Aircraft is close-range ground/runway imagery, wrong regime. Candidate for own capture. |
| Insects near-camera | No public dataset found. **Own capture is the realistic path** - this artefact is specific to the lens and focal length. |
| Birds at drone-like scale | Partly covered by Drone-vs-Bird. General bird datasets (CUB-200, NABirds) are close-up portraits and are **not** appropriate. |

---

## 7. Target-camera footage plan

**This is the only data that can support a deployment claim, and none of it exists yet.**

Hardware: InnoMaker U20CAM-1080PD&N-S1 (USB 2.0 UVC, 1280x720 default, up to 1920x1080, day
colour + IR-Cut night). Not yet in hand - the roadmap lists camera and mount as purchase
priority 1.

### Collection protocol

1. **Fix the optical configuration first.** Record lens, focal length, field of view, mount
   orientation, and resolution/format as `measured` evidence. Changing any of these invalidates
   prior recordings as test data.
2. **Record sessions, not clips.** Every session gets an ID, and the session **is** the
   `split_group`. This is what makes a clean split possible by construction rather than by
   repair.
3. **Vary one axis per session** so the resulting report can attribute failures: range
   (near / medium / small-in-frame), lighting (bright, overcast, backlit, dusk, IR night),
   background (open sky, treeline, buildings, cluttered horizon), and motion (static camera,
   pan, vibration).
4. **Record deliberate negatives** - sessions with no drone at all, containing birds, aircraft,
   insects, cloud, and glare. Target roughly 30% of total frames.
5. **Log telemetry alongside video** per the roadmap's observation contract: UTC + monotonic
   timestamps, GPS quality, Pi temperature and throttling state, frame rate, dropped frames.
6. **Hold out whole sessions for test** and freeze them before any training.
7. **Record storage cost up front.** 1080p sessions consume disk quickly, and there is currently
   5.5 GB free - resolve storage before the first capture, not during.

Existing tooling: `scripts/capture_session.py` (MP4 + sidecar JSON), `scripts/extract_frames.py`,
`scripts/auto_label.py`, plus camera benchmarks already in `artifacts/camera/`.

---

## 8. Recommended sequencing

| Order | Action | Cost | Unblocks |
| --- | --- | --- | --- |
| 0 | **Free disk space on `C:`** to at least 25 GB clear | none | everything below |
| 1 | Build the Round 1 manifest and frozen split from **data already on disk** | none | honest baseline numbers |
| 2 | Email WOSDETC for the Drone-vs-Bird DUA | none | hard-negative evaluation (lead time is the reason to start now) |
| 3 | Download **DUT Anti-UAV** | moderate | fixes the empty `drone` class |
| 4 | Clarify Anti-UAV410 licence with the authors | none | IR evaluation path |
| 5 | Acquire camera + mount, begin session recording | hardware | the only valid test set |
| 6 | Reconsider SynDroneVision | very high (900 GB) | augmentation breadth - **lowest priority** |

Step 1 requires no downloads, no disk space, and no GPU time, and is the prerequisite for
interpreting every number that follows.
