# Shark Detector Training Pipeline

Fine-tunes YOLOv8s on merged aerial shark datasets → exports ONNX → compiles to Hailo `.hef`.

## Pipeline overview

```
Roboflow API → datasets/      01_download_datasets.py
datasets/    → merged_clean/  02_merge_datasets.py   (leakage-free split)
merged_clean → best.pt        03_train.py
best.pt      → best.onnx      04_export_onnx.py
best.onnx    → best.hef       hailo compile (WSL, Hailo DFC)
best.hef     → Pi 5           scp + update perception.yaml
```

> **Leakage note (2026-06-18):** the old `02_merge` random-split leaked
> augmentation siblings and video frames across train/val → mAP50 ~0.99 was
> memorisation, not detection. `02_merge` now does a **group-disjoint** split
> (siblings + video clips kept on one side), keeps **negatives** (open-water /
> non-shark images) for a real false-positive measure, and writes a held-out
> **test** split. Output dir is `merged_clean/` (old `merged/` left intact).

## Step 0 — Install dependencies

```bash
pip install -r requirements.txt
```

## Step 1 — Get Roboflow API key

1. Create free account at https://roboflow.com
2. Account settings → Roboflow API → copy your API key

## Step 2 — Download datasets

```bash
python 01_download_datasets.py --api-key YOUR_KEY_HERE
```

Downloads 4 datasets (~3,600 aerial shark images total, all CC BY 4.0 / MIT):
- UAV Shark Detection (Piies Workspace) — MIT
- Shark ML — CC BY 4.0
- Shark Detection & Tracking — CC BY 4.0
- Salo Levy Aerial Video — CC BY 4.0

## Step 3 — Merge and normalise

```bash
python 02_merge_datasets.py
```

Remaps all datasets to class 0 = shark. Groups by source image (strips Roboflow
`.rf.<hash>`) and by video clip, then splits **group-disjoint 80/10/10**
train/val/test — no near-duplicate ever crosses a split. Val/test keep one image
per group (augmentation is train-only). Non-shark images are kept as **background
negatives** (capped). Outputs `merged_clean/` plus:
- `sharks.yaml` — train + val (use for training; honest in-distribution val)
- `sharks_eval.yaml` — val points at the held-out **test** split (final number)

## Step 4 — Train

```bash
# Onboard energy-constrained model (recommended — matches the airframe budget):
python 03_train.py --model yolov8n.pt

# Larger variant:
python 03_train.py --model yolov8s.pt

# Quick test on CPU / low VRAM:
python 03_train.py --model yolov8n.pt --epochs 30 --device cpu
python 03_train.py --batch 8
```

> **Do not reuse the old `best.pt`.** It was trained on the leaked data (it saw
> every image), so it cannot be honestly re-scored. Retrain from scratch on the
> clean split. Pick **one** model variant and make the site/README say the same
> thing — the deployed `.hef` and the portfolio currently disagree (artifact = s,
> site = n).

Trains on `merged_clean/sharks.yaml`. Monitor `runs/detect/train/results.csv` —
now that val is honest, watch for a **train/val gap** (val mAP plateauing while
train keeps climbing = overfitting, no longer hidden by leakage).

## Step 5 — Export to ONNX

```bash
python 04_export_onnx.py
```

Produces `runs/detect/train/weights/best.onnx` (opset 11, required by Hailo DFC).

## Step 5.5 — Get the TRUE number (held-out test)

After retraining on the clean split, score the model on the held-out test split
it never saw:

```bash
yolo val model=runs/detect/train/weights/best.pt data=merged_clean/sharks_eval.yaml
```

Expect this to be **well below** the old 0.99 — that's the honest baseline.
For a pessimistic **cross-source aerial-only** number, evaluate on just the
`uav_shark__*` images in `merged_clean/images/test/`.

## Step 6 — Compile to .hef (WSL, Hailo DFC)

```bash
# In WSL Ubuntu-22.04 with Hailo DFC installed
# (download from developer.hailo.ai → Software Downloads → Dataflow Compiler)
pip install hailo_dataflow_compiler-*.whl

hailo optimize best.onnx --calib-set-path merged_clean/images/train/
hailo compile best.onnx --hw-arch hailo8l --output-dir .
```

## Step 7 — Deploy to Pi 5

```bash
scp best.hef pi@<pi-ip>:/home/pi/models/shark_detector.hef
```

Update `ros2_ws/src/shark_isr_perception/config/perception.yaml`:
```yaml
use_sim: false
hef_path: /home/pi/models/shark_detector.hef
```

## No GPU? Use Google Colab

Open `03_train_colab.ipynb` in Google Colab (free T4 GPU). Mount Google Drive,
run cells in order. Download `best.pt` at the end.

## Expected performance (honest)

The old "mAP50 0.987 / mAP50-95 0.845" was a **leakage artifact** — ignore it.
On a leakage-free split, small aerial targets realistically land **mAP50-95 ≈
0.3–0.5**. Set targets against the held-out test number from Step 5.5, not the
in-distribution val.
- False-positive rate over open water is now measurable (negatives in val/test) —
  track it; it's the real operational failure mode.
- Inference budget: perception needs **10 Hz** (`perception.yaml: camera_fps`).
  Both yolov8n and yolov8s on Hailo-8L (13 TOPS INT8) clear 10 Hz; the earlier
  "~5 ms / ~200 FPS" was optimistic — measure on-device before quoting it.
