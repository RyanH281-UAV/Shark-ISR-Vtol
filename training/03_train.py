"""
03_train.py — Fine-tune YOLOv8s on the merged shark dataset.

How fine-tuning works
---------------------
YOLOv8s (small) is pre-trained on COCO (80 classes, 118k images). It has already
learned general visual features: edges, textures, shapes, water, objects.

Fine-tuning means:
  1. Load yolov8s.pt (Ultralytics downloads it automatically if not present).
  2. Replace the detection head: 80 classes → 1 class (shark).
  3. Train on your merged aerial dataset. The backbone weights are frozen for the
     first few epochs (feature extraction), then unfrozen (end-to-end tuning).
  4. The model learns: "these specific pixel patterns at ~41 px = shark dorsal fin".

Key training concepts
---------------------
  epochs    : how many full passes through the dataset. 100 is a good start.
  imgsz     : images are resized to this square. 640 matches the Hailo model input.
  batch     : images processed in parallel. Larger = faster but needs more VRAM.
  patience  : early stopping — halts if val mAP doesn't improve for N epochs.
  freeze    : freeze backbone for first N layers (speeds up early training).

Output
------
  runs/detect/train/
    weights/best.pt   ← best val mAP checkpoint  ← USE THIS for export
    weights/last.pt   ← last epoch checkpoint
    results.csv       ← mAP, precision, recall per epoch (plot with 04_plot.py)
    confusion_matrix.png

GPU vs CPU
----------
  - NVIDIA GPU (CUDA): training takes ~30-60 min for 100 epochs on 3600 images.
  - CPU only: ~6-12 hours. Reduce epochs to 30 for a quick test.
  - Google Colab (free T4 GPU): use 03_train_colab.ipynb instead.

Usage
-----
    python 03_train.py                     # default settings
    python 03_train.py --epochs 30         # quick test on CPU
    python 03_train.py --batch 8           # if GPU runs out of VRAM
    python 03_train.py --device cpu        # force CPU
"""

import argparse
import os
import torch  # must load before ultralytics to avoid Windows fbgemm.dll load-order bug
from pathlib import Path


# leakage-free split from 02_merge_datasets.py (group-disjoint train/val/test)
MERGED_YAML = Path(__file__).parent / "merged_clean" / "sharks.yaml"
RUNS_DIR = Path(__file__).parent / "runs"


def train(
    epochs: int,
    batch: int,
    imgsz: int,
    device: str,
    patience: int,
    freeze: int,
    model: str = "yolov8s.pt",
) -> None:
    try:
        from ultralytics import YOLO  # type: ignore
    except ImportError:
        print("ERROR: ultralytics not installed.")
        print("Run: pip install ultralytics")
        return

    if not MERGED_YAML.exists():
        print(f"ERROR: {MERGED_YAML} not found. Run 02_merge_datasets.py first.")
        return

    print("=" * 60)
    print("Training — shark detector")
    print(f"  dataset  : {MERGED_YAML}")
    print(f"  model    : {model} (pre-trained COCO backbone)")
    print(f"  epochs   : {epochs}")
    print(f"  batch    : {batch}")
    print(f"  imgsz    : {imgsz}")
    print(f"  device   : {device}")
    print(f"  patience : {patience}")
    print(f"  freeze   : first {freeze} backbone layers")
    print("=" * 60)

    yolo = YOLO(model)

    results = yolo.train(
        data=str(MERGED_YAML),
        epochs=epochs,
        imgsz=imgsz,
        batch=batch,
        device=device,
        patience=patience,
        freeze=freeze,
        project=str(RUNS_DIR / "detect"),
        name="train",
        exist_ok=True,
        # Augmentation — helps generalise to different water conditions
        hsv_h=0.015,    # hue shift (water colour varies)
        hsv_s=0.5,      # saturation
        hsv_v=0.4,      # brightness (sun glare, overcast)
        flipud=0.5,     # vertical flip (aerial imagery can be any orientation)
        fliplr=0.5,     # horizontal flip
        mosaic=1.0,     # mosaic augmentation (combines 4 images — good for small datasets)
        mixup=0.1,      # mixup augmentation
        degrees=15.0,   # rotation (drone can bank)
        scale=0.5,      # random scale (simulates altitude variation)
        translate=0.1,  # random translation
    )

    best_weights = RUNS_DIR / "detect" / "train" / "weights" / "best.pt"
    print(f"\nTraining complete.")
    print(f"  Best weights : {best_weights}")
    print(f"  Val mAP50    : {results.results_dict.get('metrics/mAP50(B)', 'N/A'):.3f}")
    print(f"\nNext step: python 04_export_onnx.py")


def main() -> None:
    parser = argparse.ArgumentParser(description="Fine-tune YOLO on the clean merged shark dataset.")
    parser.add_argument(
        "--model", default="yolov8s.pt",
        help="Base weights. yolov8n.pt for the energy-constrained onboard model; "
             "yolov8s.pt for the larger variant.",
    )
    parser.add_argument("--epochs", type=int, default=100)
    parser.add_argument("--batch", type=int, default=16, help="Batch size (reduce to 8 if OOM)")
    parser.add_argument("--imgsz", type=int, default=640, help="Input image size (must match Hailo)")
    parser.add_argument(
        "--device", default="0",
        help="Device: '0' for GPU 0, 'cpu' for CPU, '0,1' for multi-GPU"
    )
    parser.add_argument(
        "--patience", type=int, default=20,
        help="Early stopping: halt if val mAP doesn't improve for N epochs"
    )
    parser.add_argument(
        "--freeze", type=int, default=10,
        help="Freeze first N backbone layers (10 is good for small datasets)"
    )
    args = parser.parse_args()
    train(
        epochs=args.epochs,
        batch=args.batch,
        imgsz=args.imgsz,
        device=args.device,
        patience=args.patience,
        freeze=args.freeze,
        model=args.model,
    )


if __name__ == "__main__":
    main()
