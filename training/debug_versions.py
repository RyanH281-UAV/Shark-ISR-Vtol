"""Run this in PowerShell where ROBOFLOW_API_KEY is set."""
import os
os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"

from roboflow import Roboflow

rf = Roboflow(api_key=os.environ["ROBOFLOW_API_KEY"])

datasets = [
    ("piies-workspace", "uav-shark-detection-zgxm7", "uav_shark"),
    ("shark-ml", "shark-ml", "shark_ml"),
    ("shark-research", "shark-detection-and-tracking", "shark_tracking"),
    ("salo-levy-nlqrn", "shark-detection-z5b2z", "salo_levy"),
]

for ws, proj, name in datasets:
    print(f"\n{'='*50}")
    print(f"Dataset: {name}  ({ws}/{proj})")
    try:
        p = rf.workspace(ws).project(proj)
        info = p.get_version_information()
        print(f"  Raw version info: {info}")
    except Exception as e:
        print(f"  ERROR: {e}")
