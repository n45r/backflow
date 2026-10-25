"""Sanity check for scene_score: the score must rank closer structure higher.

    python -m backend.scene_score_check [REAL_CAM5_FRAME]
"""
import sys
from pathlib import Path

import cv2

from backend.scene_score import side_by_side, structure_score

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "runs" / "scene_score"
REAL = ROOT / "data/raw/video/frames/ev32_cam5_dry_ref211500.jpg"


def _perturb(src, dst, dx, dy, deg, scale=1.0):
    img = cv2.imread(str(src))
    h, w = img.shape[:2]
    m = cv2.getRotationMatrix2D((w / 2, h / 2), deg, scale)
    m[:, 2] += (dx, dy)
    cv2.imwrite(str(dst), cv2.warpAffine(img, m, (w, h), borderMode=cv2.BORDER_REFLECT))
    return dst


def main():
    real = Path(sys.argv[1]) if len(sys.argv) > 1 else REAL
    OUT.mkdir(parents=True, exist_ok=True)
    small = _perturb(real, OUT / "real_shift_small.png", 12, 6, 1.0)
    big = _perturb(real, OUT / "real_shift_big.png", 60, 30, 5.0, 1.05)
    cases = [
        ("real vs itself", real),
        ("real vs shift 12px + rot 1deg", small),
        ("real vs shift 60px + rot 5deg", big),
        ("real vs r0_blind cam5", OUT / "r0_blind/cam5_t00000.png"),
        ("real vs placeholder cam5", OUT / "placeholder/cam5_t00000.png"),
        ("real vs r0_blind cam1", OUT / "r0_blind/cam1_t00000.png"),
        ("real vs placeholder cam1", OUT / "placeholder/cam1_t00000.png"),
    ]
    rows = []
    print(f"{'case':34s} {'score':>6s} {'chamfer':>8s} {'r->s':>6s} {'s->r':>6s} {'orient':>7s}")
    for name, p in cases:
        s = structure_score(real, p)
        rows.append((name, s))
        print(f"{name:34s} {s['score']:6.1f} {s['chamfer_px']:8.2f} {s['chamfer_real_to_render_px']:6.2f} "
              f"{s['chamfer_render_to_real_px']:6.2f} {s['orientation_sim']:7.3f}")
    for tag, p in [("r0_blind_cam5", cases[3][1]), ("placeholder_cam5", cases[4][1]),
                   ("r0_blind_cam1", cases[5][1]), ("shift_small", small)]:
        side_by_side(real, p, OUT / f"overlay_{tag}.png", label=tag)
    sc = [s["score"] for _, s in rows]
    checks = {
        "self best": sc[0] == max(sc),
        "small shift second": sc[1] == sorted(sc, reverse=True)[1],
        "small shift > big shift": sc[1] > sc[2],
        "shifts > cam5 renders": min(sc[1], sc[2]) > max(sc[3], sc[4]),
        "r0_blind: cam1 < cam5": sc[5] < sc[3],
        "placeholder: cam1 < cam5": sc[6] < sc[4],
        "cam1 renders worst overall": max(sc[5], sc[6]) < min(sc[:5]),
    }
    for k, v in checks.items():
        print(f"{'PASS' if v else 'FAIL'}  {k}")
    return all(checks.values())


if __name__ == "__main__":
    sys.exit(0 if main() else 1)
