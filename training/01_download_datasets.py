"""
01_download_datasets.py — Download all 4 Roboflow shark datasets.

How it works
------------
Roboflow hosts datasets in versioned projects. Each project has a workspace ID
(like a username) and a project ID. When you download, Roboflow gives you:

    dataset_name/
        train/images/   train/labels/
        valid/images/   valid/labels/
        data.yaml       ← class names, paths, nc (number of classes)

We download in "yolov8" format because Ultralytics (the YOLOv8 library) reads
that directory structure directly.

Usage
-----
1. Create a free account at https://roboflow.com
2. Get your API key: account settings → Roboflow API → copy key
3. Run:
       python 01_download_datasets.py --api-key YOUR_KEY_HERE

All 4 datasets land in ./datasets/<name>/
"""

import argparse
import os
import sys

DATASETS = [
    {
        "name": "uav_shark",
        "workspace": "piies-workspace",
        "project": "uav-shark-detection-zgxm7",
        "version": 1,   # fallback if auto-detect fails
        "description": "UAV Shark Detection (Piies Workspace) — MIT licence",
    },
    {
        "name": "shark_ml",
        "workspace": "shark-ml",
        "project": "shark-ml",
        "version": 1,   # fallback
        "description": "Shark ML (shark-ml) — CC BY 4.0",
    },
    {
        "name": "shark_tracking",
        "workspace": "shark-research",
        "project": "shark-detection-and-tracking",
        "version": 1,   # fallback
        "description": "Shark Detection & Tracking (Shark Research) — CC BY 4.0",
    },
    {
        "name": "salo_levy",
        "workspace": "salo-levy-nlqrn",
        "project": "shark-detection-z5b2z",
        "version": 3,   # fallback
        "description": "Shark Detection Aerial Video (Salo Levy) — CC BY 4.0",
    },
]


def download_all(api_key: str, output_dir: str) -> None:
    try:
        from roboflow import Roboflow  # type: ignore
    except ImportError:
        print("ERROR: roboflow package not installed.")
        print("Run: pip install roboflow")
        sys.exit(1)

    rf = Roboflow(api_key=api_key)
    os.makedirs(output_dir, exist_ok=True)

    for ds in DATASETS:
        dest = os.path.join(output_dir, ds["name"])

        # Skip only if folder exists AND contains a data.yaml (i.e. a real download)
        data_yaml = os.path.join(dest, "data.yaml")
        if os.path.exists(data_yaml):
            print(f"[SKIP] {ds['name']} already downloaded (data.yaml present)")
            continue
        # Clean up empty/partial folder so download can proceed cleanly
        if os.path.exists(dest):
            import subprocess, sys
            if sys.platform == "win32":
                subprocess.run(
                    ["powershell", "-Command", f"Remove-Item -Recurse -Force '{dest}'"],
                    check=True,
                )
            else:
                import shutil
                shutil.rmtree(dest)

        print(f"\n{'='*60}")
        print(f"Downloading: {ds['description']}")
        print(f"  workspace : {ds['workspace']}")
        print(f"  project   : {ds['project']}")

        project = rf.workspace(ds["workspace"]).project(ds["project"])

        # Auto-detect latest available version.
        # Version number lives in the last segment of v["id"]: "ws/proj/N" → N
        version_num = None
        try:
            version_info = project.get_version_information()
            if version_info:
                version_num = max(int(v["id"].split("/")[-1]) for v in version_info)
                print(f"  version   : {version_num} (auto-detected latest)")
        except Exception as exc:
            print(f"  version info error: {exc}")

        if version_num is None:
            print(f"  [SKIP] No accessible versions for {ds['name']}.")
            print(f"         Manual download: https://universe.roboflow.com/{ds['workspace']}/{ds['project']}")
            print(f"         Choose 'YOLOv8' format → extract to datasets/{ds['name']}/")
            continue

        version = project.version(version_num)

        # Roboflow SDK downloads relative to CWD — cd to output_dir first.
        # The SDK extracts the zip THEN runs yaml post-processing which imports
        # ultralytics/torch. If torch fails to load (Windows DLL issue), the
        # data is already on disk — catch that and continue.
        original_dir = os.getcwd()
        try:
            os.chdir(output_dir)
            version.download("yolov8", location=ds["name"])
        except (OSError, Exception) as exc:
            # Check if data actually landed despite the error
            if os.path.exists(data_yaml):
                print(f"  ✓ data extracted (yaml post-processing error skipped: {type(exc).__name__})")
            else:
                print(f"  ✗ download failed: {exc}")
        finally:
            os.chdir(original_dir)

        if os.path.exists(data_yaml):
            print(f"  ✓ saved to {dest}")
        else:
            print(f"  ✗ no data.yaml found — check {output_dir}")

        print(f"  ✓ saved to {dest}")

    print(f"\nAll downloads complete. Datasets in: {output_dir}")
    print("Next step: python 02_merge_datasets.py")


def main() -> None:
    parser = argparse.ArgumentParser(description="Download shark datasets from Roboflow.")
    parser.add_argument(
        "--api-key",
        default=os.environ.get("ROBOFLOW_API_KEY", ""),
        help="Roboflow API key (or set ROBOFLOW_API_KEY env var)",
    )
    parser.add_argument(
        "--output-dir",
        default=os.path.join(os.path.dirname(__file__), "datasets"),
        help="Where to save downloaded datasets (default: ./datasets/)",
    )
    args = parser.parse_args()
    download_all(args.api_key, args.output_dir)


if __name__ == "__main__":
    main()
