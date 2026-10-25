"""Trial of the structural round: align the blind scene's camera 5 with the real dry frame, a few rounds."""
import json
import os
import sys
from pathlib import Path

from backend import argon, contact
from backend.render import Renderer

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "runs" / "scene_align"
REAL = ROOT / "data" / "raw" / "video" / "frames" / "ev32_cam5_dry_ref211500.jpg"
SCENE = "/scene/r0_blind.js"
DRY = {"t": [0], "depth_m": {}}


def merge(a, b):
    for k, v in b.items():
        if isinstance(v, dict) and isinstance(a.get(k), dict):
            merge(a[k], v)
        else:
            a[k] = v
    return a


def main(rounds=3):
    OUT.mkdir(parents=True, exist_ok=True)
    site = json.loads((ROOT / "site" / "site.json").read_text())
    r = Renderer()
    r.site = site
    patch, log = {}, []
    try:
        for n in range(rounds + 1):
            r.patch = patch
            render = r.render(SCENE, DRY, "cam5", [0], OUT / f"r{n}")[0]
            sheet = contact.contact_sheet([str(REAL)], [render], [f"cam5 round {n}"], OUT / f"sheet_r{n}.png")
            if n == rounds:
                break
            desc = r.describe(SCENE)
            fix = argon.scene_fix(sheet, desc)
            res = fix["result"]
            log.append({"round": n, "result": res, "seconds": fix["seconds"]})
            print(n, fix["seconds"], json.dumps(res)[:600], flush=True)
            if not res.get("patch"):
                break
            patch = merge(patch, res["patch"])
            (OUT / "patch.json").write_text(json.dumps(patch, indent=1))
    finally:
        r.close()
    (OUT / "log.json").write_text(json.dumps(log, indent=1))


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 3)
