"""
04_export_onnx.py — Export trained best.pt → best.onnx for Hailo DFC.

How it works
------------
PyTorch (.pt) is the native training format. Hailo's Dataflow Compiler (DFC)
cannot read .pt — it needs ONNX (Open Neural Network Exchange), a standard
interchange format supported by all major ML frameworks.

The export process:
  1. Load best.pt (your fine-tuned shark detector).
  2. Trace through the model with a dummy input (640×640 image).
  3. Record every operation as ONNX graph nodes.
  4. Write best.onnx.

Opset 11 is required — Hailo DFC does not support higher opset versions.

After this step
---------------
On a Linux machine with Hailo DFC installed (your WSL Ubuntu 22.04):

    pip install hailo_dataflow_compiler-*.whl   # from developer.hailo.ai
    hailo optimize best.onnx --calib-set-path merged/images/val/
    hailo compile best.onnx --hw-arch hailo8l --output-dir .
    # → produces best.hef

Then on the Pi 5:
    scp best.hef pi@<ip>:/home/pi/models/shark_detector.hef

And update config/perception.yaml:
    use_sim: false
    hef_path: /home/pi/models/shark_detector.hef

Usage
-----
    python 04_export_onnx.py
    python 04_export_onnx.py --weights path/to/custom/best.pt
"""

import argparse
import torch  # must load before ultralytics on Windows (fbgemm.dll load-order bug)
from pathlib import Path


BEST_PT = Path(__file__).parent / "runs" / "detect" / "train" / "weights" / "best.pt"
ONNX_OUT = Path(__file__).parent / "runs" / "detect" / "train" / "weights" / "best.onnx"


def export(weights: Path) -> None:
    try:
        from ultralytics import YOLO  # type: ignore
    except ImportError:
        print("ERROR: ultralytics not installed.  pip install ultralytics")
        return

    if not weights.exists():
        print(f"ERROR: {weights} not found. Run 03_train.py first.")
        return

    print(f"Exporting: {weights}")
    print(f"  → ONNX opset 11 (required by Hailo DFC)")

    model = YOLO(str(weights))
    export_path = model.export(
        format="onnx",
        opset=11,
        simplify=True,   # run onnx-simplifier — cleaner graph, better DFC compat
        imgsz=640,
        dynamic=False,   # fixed batch=1 required for Hailo
    )

    print(f"\nExport complete: {export_path}")
    print()
    print("Next steps (run in WSL Ubuntu-22.04 with Hailo DFC installed):")
    print(f"  hailo optimize {export_path} --calib-set-path merged/images/val/")
    print(f"  hailo compile  {export_path} --hw-arch hailo8l --output-dir .")
    print("  # → produces best.hef")
    print()
    print("Then deploy:")
    print("  scp best.hef pi@<pi-ip>:/home/pi/models/shark_detector.hef")
    print("  # Update config/perception.yaml: use_sim: false, hef_path: ...")


def main() -> None:
    parser = argparse.ArgumentParser(description="Export YOLOv8 best.pt to ONNX for Hailo DFC.")
    parser.add_argument(
        "--weights",
        type=Path,
        default=BEST_PT,
        help=f"Path to trained weights (default: {BEST_PT})",
    )
    args = parser.parse_args()
    export(args.weights)


if __name__ == "__main__":
    main()
