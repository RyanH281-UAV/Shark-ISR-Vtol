"""
02_merge_datasets.py — Merge the Roboflow shark datasets into one LEAKAGE-FREE set.

Why this was rewritten
----------------------
The previous version pooled each source's train+valid, random-shuffled, and
re-split 90/10. That leaks: Roboflow augmentation siblings (same source image,
different `.rf.<hash>`) and consecutive video frames landed on BOTH sides, so
the model "validated" on near-copies of its training images (mAP ~0.99 = memo-
risation, not detection).

What this version does
----------------------
1. Reads each data.yaml, finds every "shark" class index, keeps only shark
   annotations, remaps class id -> 0.
2. GROUPS images so leaks can't cross the split:
     - augmentation siblings  -> grouped by source image (strip `.rf.<hash>`)
     - video frames           -> grouped by clip id (strip `_mp4-0008` etc.)
   A whole group always lands on ONE side.
3. DETERMINISTIC group-disjoint split 80/10/10 train/val/test (hash of group id,
   no RNG, reproducible).
4. AUGMENT TRAIN-ONLY (approx): train keeps all sibling/frame copies; val/test
   keep ONE image per group, so the eval isn't inflated by near-duplicates.
5. KEEPS NEGATIVES: images with no shark (but e.g. boats / people / open water)
   become background images (empty label), capped per split — so false positives
   over empty water are actually measurable and trainable against.

Non-destructive: writes to merged_clean/ (your existing merged/ is left alone).

Output
------
    merged_clean/
        images/{train,val,test}/   labels/{train,val,test}/
        sharks.yaml        ← train + val   (training + honest in-distribution val)
        sharks_eval.yaml   ← val points at the held-out TEST split (final number)

NOTE: the existing best.pt was trained on the leaked data, so it cannot be
honestly re-scored on any subset (it saw everything). The true number requires
RETRAINING on this clean split, then `yolo val ... data=sharks_eval.yaml`.
For a pessimistic cross-source (aerial-only) number, filter test to uav_shark.
"""

import re
import shutil
import hashlib
import yaml
from pathlib import Path

DATASETS_DIR = Path(__file__).parent / "datasets"
MERGED_DIR = Path(__file__).parent / "merged_clean"

SHARK_ALIASES = {
    "shark", "sharks", "Shark", "Sharks",
    "White-Shark", "white-shark", "White Shark", "white shark",
    "Whitetip", "whitetip", "Bull-Shark", "bull-shark",
    "Tiger-Shark", "tiger-shark", "Tiger Shark",
    "Hammerhead", "hammerhead", "Reef-Shark", "reef-shark", "Reef Shark",
    "Great-White", "great-white", "Great White",
}

# split buckets (0..9) by group-hash → 80/10/10
VAL_BUCKETS = {0}
TEST_BUCKETS = {1}
# negatives capped relative to positives, per split, so background can't swamp
NEG_RATIO = 0.30

VIDEO_RE = re.compile(r"(.+?\.(?:mp4|mov|avi|mkv|webm|MP4|MOV))", re.IGNORECASE)


def load_class_names(data_yaml: Path) -> list[str]:
    with open(data_yaml) as f:
        cfg = yaml.safe_load(f)
    names = cfg.get("names", [])
    if isinstance(names, dict):
        names = [names[k] for k in sorted(names.keys())]
    return names


def find_shark_class_ids(names: list[str]) -> set[int]:
    return {i for i, name in enumerate(names) if name in SHARK_ALIASES}


def rewrite_label(src_label: Path, shark_class_ids: set[int]) -> list[str]:
    """Shark-only lines, class remapped to 0. Empty list = no shark (negative)."""
    if not src_label.exists():
        return []
    out = []
    for line in src_label.read_text().splitlines():
        parts = line.strip().split()
        if not parts:
            continue
        if int(parts[0]) in shark_class_ids:
            out.append("0 " + " ".join(parts[1:]))
    return out


def collect_image_label_pairs(dataset_dir: Path) -> list[tuple[Path, Path]]:
    pairs = []
    for split in ("train", "valid", "val", "test"):
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
            pairs.append((img_path, lbl_dir / (img_path.stem + ".txt")))
    return pairs


def group_id(dataset_name: str, img_path: Path) -> str:
    """Stable group key: collapses augmentation siblings AND video clips so all
    near-duplicates of one source share a key and never cross the split."""
    stem = img_path.stem
    base = re.split(r"\.rf\.", stem)[0]      # drop Roboflow augmentation hash
    m = VIDEO_RE.match(base)                 # collapse a whole video clip → one key
    key = m.group(1) if m else base
    return f"{dataset_name}::{key}"


def bucket(group: str) -> int:
    return int(hashlib.md5(group.encode()).hexdigest(), 16) % 10


def split_for(group: str) -> str:
    b = bucket(group)
    if b in VAL_BUCKETS:
        return "val"
    if b in TEST_BUCKETS:
        return "test"
    return "train"


def merge() -> None:
    for split in ("train", "val", "test"):
        (MERGED_DIR / "images" / split).mkdir(parents=True, exist_ok=True)
        (MERGED_DIR / "labels" / split).mkdir(parents=True, exist_ok=True)

    # gather everything first: (split, group, stem, src_img, shark_lines, is_pos)
    records = []
    for ds_dir in sorted(DATASETS_DIR.iterdir()):
        if not ds_dir.is_dir():
            continue
        data_yaml = ds_dir / "data.yaml"
        if not data_yaml.exists():
            nested = list(ds_dir.glob("*/data.yaml"))
            if not nested:
                print(f"[SKIP] No data.yaml in {ds_dir}")
                continue
            data_yaml = nested[0]
            ds_dir = data_yaml.parent

        names = load_class_names(data_yaml)
        shark_ids = find_shark_class_ids(names)
        if not shark_ids:
            print(f"[WARN] No shark class in {ds_dir.name}: {names}")
            continue

        pairs = collect_image_label_pairs(ds_dir)
        print(f"{ds_dir.name}: {len(pairs)} images, shark ids {shark_ids}")
        for img_path, lbl_path in pairs:
            lines = rewrite_label(lbl_path, shark_ids)
            grp = group_id(ds_dir.name, img_path)
            records.append({
                "split": split_for(grp),
                "group": grp,
                "stem": f"{ds_dir.name}__{img_path.stem}",
                "img": img_path,
                "suffix": img_path.suffix,
                "lines": lines,
                "pos": bool(lines),
            })

    # write positives; val/test keep ONE image per group (no augmented dup inflation)
    seen_groups: dict[str, set[str]] = {"train": set(), "val": set(), "test": set()}
    counts = {s: {"pos": 0, "neg": 0} for s in ("train", "val", "test")}
    negatives: dict[str, list[dict]] = {"train": [], "val": [], "test": []}

    for r in sorted(records, key=lambda x: x["stem"]):
        s = r["split"]
        if not r["pos"]:
            negatives[s].append(r)            # held back, capped + added after
            continue
        if s in ("val", "test") and r["group"] in seen_groups[s]:
            continue                          # dedup augmentation siblings in eval
        seen_groups[s].add(r["group"])
        _write(r, s)
        counts[s]["pos"] += 1

    # add negatives, capped to NEG_RATIO of positives per split, group-deduped in eval
    for s in ("train", "val", "test"):
        cap = int(counts[s]["pos"] * NEG_RATIO)
        added = 0
        for r in negatives[s]:
            if added >= cap:
                break
            if s in ("val", "test") and r["group"] in seen_groups[s]:
                continue
            seen_groups[s].add(r["group"])
            _write(r, s)                       # empty label = background
            added += 1
        counts[s]["neg"] = added

    _write_yaml("sharks.yaml", val_split="val")
    _write_yaml("sharks_eval.yaml", val_split="test")

    print(f"\n{'='*60}\nMerge complete → {MERGED_DIR}")
    for s in ("train", "val", "test"):
        print(f"  {s:5}: {counts[s]['pos']} pos + {counts[s]['neg']} neg "
              f"= {counts[s]['pos'] + counts[s]['neg']}")
    print("  sharks.yaml      → train + val   (train here, honest in-dist val)")
    print("  sharks_eval.yaml → val=test      (final held-out number after RETRAIN)")
    print("\nNext: retrain on sharks.yaml (do NOT reuse the old best.pt — it saw "
          "everything), then `yolo val model=<new>/best.pt data=merged_clean/sharks_eval.yaml`.")


def _write(r: dict, split: str) -> None:
    dst_img = MERGED_DIR / "images" / split / (r["stem"] + r["suffix"])
    dst_lbl = MERGED_DIR / "labels" / split / (r["stem"] + ".txt")
    shutil.copy2(r["img"], dst_img)
    dst_lbl.write_text(("\n".join(r["lines"]) + "\n") if r["lines"] else "")


def _write_yaml(name: str, val_split: str) -> None:
    cfg = {
        "path": str(MERGED_DIR.resolve()),
        "train": "images/train",
        "val": f"images/{val_split}",
        "nc": 1,
        "names": ["shark"],
    }
    with open(MERGED_DIR / name, "w") as f:
        yaml.dump(cfg, f, default_flow_style=False, sort_keys=False)


if __name__ == "__main__":
    merge()
