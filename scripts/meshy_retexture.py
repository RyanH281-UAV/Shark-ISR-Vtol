#!/usr/bin/env python3
"""Retexture hornet.glb via the Meshy Text-to-Texture API.

Usage:
    export MESHY_API_KEY=msy_...        # meshy.ai → account → API keys
    python3 scripts/meshy_retexture.py  [--prompt "..."]

Uploads site-v3/public/models/hornet.glb as a base64 data URI, polls until the
job finishes, downloads the textured GLB to
site-v3/public/models/hornet_textured.glb. Rebuild site-v3 afterwards.
"""

import argparse
import base64
import json
import os
import sys
import time
import urllib.request

API = "https://api.meshy.ai/openapi/v1/retexture"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "site-v3", "public", "models", "hornet.glb")
DST = os.path.join(ROOT, "site-v3", "public", "models", "hornet_textured.glb")

DEFAULT_PROMPT = (
    "small UAV tiltrotor aircraft, matte dark grey composite airframe with "
    "carbon fiber weave on the wings, subtle recessed panel lines, "
    "safety-orange wingtip accents, small black warning decals near the "
    "rotors, clean industrial product finish, slightly worn edges"
)


def req(url: str, data: dict | None = None) -> dict:
    key = os.environ.get("MESHY_API_KEY")
    if not key:
        sys.exit("MESHY_API_KEY not set. Get one at meshy.ai → account → API keys.")
    r = urllib.request.Request(
        url,
        data=json.dumps(data).encode() if data else None,
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        },
        method="POST" if data else "GET",
    )
    with urllib.request.urlopen(r, timeout=120) as resp:
        return json.loads(resp.read())


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--prompt", default=DEFAULT_PROMPT)
    args = ap.parse_args()

    with open(SRC, "rb") as f:
        data_uri = "data:model/gltf-binary;base64," + base64.b64encode(f.read()).decode()
    print(f"Uploading {os.path.basename(SRC)} ({os.path.getsize(SRC) // 1024} KiB)…")

    task = req(API, {
        "model_url": data_uri,
        "text_style_prompt": args.prompt,
        "enable_pbr": True,
    })
    task_id = task.get("result") or task.get("id")
    print(f"Task {task_id} submitted. Polling…")

    while True:
        time.sleep(15)
        st = req(f"{API}/{task_id}")
        status = st.get("status")
        print(f"  {status} {st.get('progress', '')}")
        if status == "SUCCEEDED":
            url = st["model_urls"]["glb"]
            print(f"Downloading textured GLB…")
            urllib.request.urlretrieve(url, DST)
            print(f"Saved → {DST}")
            print("Next: update Hero3D to load hornet_textured.glb and rebuild site-v3.")
            return
        if status in ("FAILED", "CANCELED"):
            sys.exit(f"Meshy task {status}: {st.get('task_error')}")


if __name__ == "__main__":
    main()
