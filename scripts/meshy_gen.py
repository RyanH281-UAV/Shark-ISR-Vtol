#!/usr/bin/env python3
"""Generate GLB assets via the Meshy API (image-to-3D and text-to-3D).

Usage:
    source ~/.meshy_key
    python3 scripts/meshy_gen.py image <input_image> <output.glb>
    python3 scripts/meshy_gen.py text "<prompt>" <output.glb>

Polls until the job finishes and downloads the GLB. Text-to-3D runs the
two-stage preview → refine pipeline (refine adds textures).
"""

import base64
import json
import mimetypes
import os
import sys
import time
import urllib.request

BASE = "https://api.meshy.ai/openapi"


def req(url: str, data: dict | None = None) -> dict:
    key = os.environ.get("MESHY_API_KEY")
    if not key:
        sys.exit("MESHY_API_KEY not set (source ~/.meshy_key).")
    r = urllib.request.Request(
        url,
        data=json.dumps(data).encode() if data else None,
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        method="POST" if data else "GET",
    )
    with urllib.request.urlopen(r, timeout=180) as resp:
        return json.loads(resp.read())


def poll(url: str, label: str) -> dict:
    while True:
        time.sleep(20)
        st = req(url)
        print(f"[{label}] {st.get('status')} {st.get('progress', '')}", flush=True)
        if st.get("status") == "SUCCEEDED":
            return st
        if st.get("status") in ("FAILED", "CANCELED"):
            sys.exit(f"[{label}] {st.get('status')}: {st.get('task_error')}")


def download(st: dict, out: str) -> None:
    urllib.request.urlretrieve(st["model_urls"]["glb"], out)
    print(f"Saved → {out} ({os.path.getsize(out) // 1024} KiB)", flush=True)


def image_to_3d(img: str, out: str) -> None:
    mime = mimetypes.guess_type(img)[0] or "image/png"
    with open(img, "rb") as f:
        uri = f"data:{mime};base64," + base64.b64encode(f.read()).decode()
    t = req(f"{BASE}/v1/image-to-3d", {
        "image_url": uri,
        "should_texture": True,
        "enable_pbr": True,
        "topology": "triangle",
        "target_polycount": 60000,
    })
    tid = t.get("result") or t.get("id")
    print(f"image-to-3d task {tid}", flush=True)
    download(poll(f"{BASE}/v1/image-to-3d/{tid}", "img3d"), out)


def text_to_3d(prompt: str, out: str) -> None:
    t = req(f"{BASE}/v2/text-to-3d", {
        "mode": "preview",
        "prompt": prompt,
        "art_style": "realistic",
        "topology": "triangle",
        "target_polycount": 40000,
    })
    tid = t.get("result") or t.get("id")
    print(f"text-to-3d preview task {tid}", flush=True)
    poll(f"{BASE}/v2/text-to-3d/{tid}", "preview")

    r = req(f"{BASE}/v2/text-to-3d", {"mode": "refine", "preview_task_id": tid, "enable_pbr": True})
    rid = r.get("result") or r.get("id")
    print(f"text-to-3d refine task {rid}", flush=True)
    download(poll(f"{BASE}/v2/text-to-3d/{rid}", "refine"), out)


if __name__ == "__main__":
    if len(sys.argv) != 4 or sys.argv[1] not in ("image", "text"):
        sys.exit(__doc__)
    if sys.argv[1] == "image":
        image_to_3d(sys.argv[2], sys.argv[3])
    else:
        text_to_3d(sys.argv[2], sys.argv[3])
