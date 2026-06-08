# Shark Detector Training Pipeline

Fine-tunes YOLOv8s on merged aerial shark datasets → exports ONNX → compiles to Hailo `.hef`.

## Pipeline overview

```
Roboflow API → datasets/   01_download_datasets.py
datasets/    → merged/     02_merge_datasets.py
merged/      → best.pt     03_train.py
best.pt      → best.onnx   04_export_onnx.py
best.onnx    → best.hef    hailo compile (WSL, Hailo DFC)
best.hef     → Pi 5        scp + update perception.yaml
```

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

Remaps all datasets to class 0 = shark. Filters non-shark annotations.
Outputs `merged/` with unified YOLO structure.

## Step 4 — Train

```bash
# With GPU (recommended):
python 03_train.py

# Quick test on CPU (reduced epochs):
python 03_train.py --epochs 30 --device cpu

# Low VRAM GPU:
python 03_train.py --batch 8
```

Training on ~3,200 train images, ~360 val. Expect 30–60 min on GPU, 6–12 hrs on CPU.
Monitor: `runs/detect/train/results.csv` — watch `metrics/mAP50(B)` increase.

Target: mAP50 > 0.6 means the model reliably detects sharks at 50% IoU threshold.

## Step 5 — Export to ONNX

```bash
python 04_export_onnx.py
```

Produces `runs/detect/train/weights/best.onnx` (opset 11, required by Hailo DFC).

## Step 6 — Compile to .hef (WSL, Hailo DFC)

```bash
# In WSL Ubuntu-22.04 with Hailo DFC installed
# (download from developer.hailo.ai → Software Downloads → Dataflow Compiler)
pip install hailo_dataflow_compiler-*.whl

hailo optimize best.onnx --calib-set-path merged/images/val/
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

## Expected performance

On ~3,600 aerial images with YOLOv8s fine-tuned 100 epochs:
- mAP50 target: > 0.60
- False positive rate: moderate (small dataset — improves significantly if FLAIR nurse shark dataset added)
- Inference on Hailo-8L: ~5 ms/frame → well within 10 Hz camera rate
