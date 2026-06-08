"""
02_merge_datasets.py — Merge 4 Roboflow shark datasets into one unified set.

How it works
------------
Each Roboflow download has a data.yaml like this:

    nc: 3                          # number of classes
    names: ['boat', 'shark', 'swimmer']

The class id in the .txt label files is the INDEX into that names list.
So "shark" might be class 1 in one dataset and class 0 in another.

This script:
  1. Reads each data.yaml to find the index of "shark" in that dataset.
  2. Copies every image whose label file contains at least one shark annotation.
  3. Rewrites label files: keeps only shark lines, remaps class id to 0.
  4. Splits all merged images 90% train / 10% val (respects original splits if clean).
  5. Writes merged/sharks.yaml for use in training.

Output structure
----------------
    merged/
        images/
            train/  ← all training images from all datasets
            val/    ← all validation images from all datasets
        labels/
            train/  ← rewritten .txt files (class 0 = shark only)
            val/
        sharks.yaml ← dataset config for Ultralytics YOLOv8

Usage
-----
    python 02_merge_datasets.py

Expects datasets/ folder created by 01_download_datasets.py.
"""

import os
import shutil
import random
import yaml  # pip install pyyaml
from pathlib import Path

DATASETS_DIR = Path(__file__).parent / "datasets"
MERGED_DIR = Path(__file__).parent / "merged"
SHARK_ALIASES = {
    "shark", "sharks", "Shark", "Sharks",
    "White-Shark", "white-shark", "White Shark", "white shark",
    "Whitetip", "whitetip", "Bull-Shark", "bull-shark",
}
RANDOM_SEED = 42
VAL_FRACTION = 0.10  # 10% of each dataset goes to val


def load_class_names(data_yaml: Path) -> list[str]:
    with open(data_yaml) as f:
        cfg = yaml.safe_load(f)
    names = cfg.get("names", [])
    if isinstance(names, dict):
        names = [names[k] for k in sorted(names.keys())]
    return names


def find_shark_class_ids(names: list[str]) -> set[int]:
    """Return ALL class indices that map to a shark variant."""
    return {i for i, name in enumerate(names) if name in SHARK_ALIASES}


def rewrite_label(src_label: Path, shark_class_ids: set[int]) -> list[str]:
    """Return rewritten lines with only shark annotations, class remapped to 0."""
    if not src_label.exists():
        return []
    lines = src_label.read_text().splitlines()
    out = []
    for line in lines:
        parts = line.strip().split()
        if not parts:
            continue
        if int(parts[0]) in shark_class_ids:
            out.append("0 " + " ".join(parts[1:]))
    return out


def collect_image_label_pairs(dataset_dir: Path) -> list[tuple[Path, Path]]:
    """Return (image_path, label_path) pairs from train/ and valid/ splits."""
    pairs = []
    for split in ("train", "valid", "val"):
        img_dir = dataset_dir / split / "images"
        lbl_dir = dataset_dir / split / "labels"
        if not img_dir.exists():
            img_dir = dataset_dir / "images" / split
            lbl_dir = dataset_dir / "labels" / split
        if not img_dir.exists():
            continue
        for img_path in sorted(img_dir.iterdir()):
            if img_path.suffix.lower() not in (".jpg", ".jpeg", ".png"):
                continue
            lbl_path = lbl_dir / (img_path.stem + ".txt")
            pairs.append((img_path, lbl_path))
    return pairs


def merge() -> None:
    random.seed(RANDOM_SEED)

    for split in ("train", "val"):
        (MERGED_DIR / "images" / split).mkdir(parents=True, exist_ok=True)
        (MERGED_DIR / "labels" / split).mkdir(parents=True, exist_ok=True)

    total_images = 0
    total_skipped = 0

    for ds_dir in sorted(DATASETS_DIR.iterdir()):
        if not ds_dir.is_dir():
            continue

        data_yaml = ds_dir / "data.yaml"
        if not data_yaml.exists():
            # Try one level deeper (Roboflow sometimes nests)
            nested = list(ds_dir.glob("*/data.yaml"))
            if nested:
                data_yaml = nested[0]
                ds_dir = data_yaml.parent
            else:
                print(f"[SKIP] No data.yaml in {ds_dir}")
                continue

        names = load_class_names(data_yaml)
        shark_ids = find_shark_class_ids(names)

        if not shark_ids:
            print(f"[WARN] No 'shark' class found in {ds_dir.name}: {names}")
            continue

        print(f"\nProcessing: {ds_dir.name}")
        print(f"  Classes   : {names}")
        print(f"  Shark ids : {shark_ids}")

        pairs = collect_image_label_pairs(ds_dir)
        print(f"  Images    : {len(pairs)}")

        # Shuffle then split if the dataset doesn't already have a clean val set
        random.shuffle(pairs)
        n_val = max(1, int(len(pairs) * VAL_FRACTION))
        val_pairs = pairs[:n_val]
        train_pairs = pairs[n_val:]

        ds_count = 0
        ds_skipped = 0

        for split, split_pairs in [("train", train_pairs), ("val", val_pairs)]:
            for img_path, lbl_path in split_pairs:
                lines = rewrite_label(lbl_path, shark_ids)
                if not lines:
                    # Image has no shark annotations — skip it
                    ds_skipped += 1
                    continue

                # Unique filename: dataset_name + original stem
                stem = f"{ds_dir.name}__{img_path.stem}"
                dst_img = MERGED_DIR / "images" / split / (stem + img_path.suffix)
                dst_lbl = MERGED_DIR / "labels" / split / (stem + ".txt")

                shutil.copy2(img_path, dst_img)
                dst_lbl.write_text("\n".join(lines) + "\n")
                ds_count += 1

        print(f"  Kept      : {ds_count}  (skipped {ds_skipped} with no shark)")
        total_images += ds_count
        total_skipped += ds_skipped

    # Write sharks.yaml
    n_train = len(list((MERGED_DIR / "images" / "train").iterdir()))
    n_val = len(list((MERGED_DIR / "images" / "val").iterdir()))

    sharks_yaml = {
        "path": str(MERGED_DIR.resolve()),
        "train": "images/train",
        "val": "images/val",
        "nc": 1,
        "names": ["shark"],
    }
    yaml_path = MERGED_DIR / "sharks.yaml"
    with open(yaml_path, "w") as f:
        yaml.dump(sharks_yaml, f, default_flow_style=False, sort_keys=False)

    print(f"\n{'='*60}")
    print(f"Merge complete.")
    print(f"  Train images : {n_train}")
    print(f"  Val images   : {n_val}")
    print(f"  Total kept   : {total_images}")
    print(f"  Total skipped: {total_skipped} (no shark annotation)")
    print(f"  Dataset yaml : {yaml_path}")
    print(f"\nNext step: python 03_train.py")


if __name__ == "__main__":
    merge()
