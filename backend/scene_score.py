"""Scene-alignment score: how well a render's structure lines up with a real camera frame.

Compares edges, not texture or colour, so a night infrared frame and a flat-shaded
render can be compared. Higher score is better (0 to 100).

    python -m backend.scene_score REAL RENDER [--overlay out.png]
"""
import argparse
import json
from pathlib import Path

import cv2
import numpy as np

W, H = 640, 360
TRUNC_PX = 40.0          # chamfer distances are capped here so one missing wall cannot dominate
ORI_BINS = 12            # orientation bins over 0..180 degrees
GRID = (3, 3)            # orientation histograms per cell, so they are position-aware
MIN_EDGE_LEN = 25        # drop short edge fragments (floor texture, noise)
HI_PCT = 90              # Canny high threshold = this percentile of gradient magnitude
MIN_HI = 15.0            # floor for flat images

# Overlay regions as fractions of the frame (x0, y0, x1, y1): camera label top left, clock top right.
OVERLAY_MASKS = [(0.0, 0.0, 0.07, 0.07), (0.74, 0.0, 1.0, 0.07)]
BORDER_PX = 4


def _load_gray(img):
    if isinstance(img, (str, Path)):
        a = cv2.imread(str(img), cv2.IMREAD_GRAYSCALE)
        if a is None:
            raise FileNotFoundError(img)
    else:
        a = img if img.ndim == 2 else cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    return cv2.resize(a, (W, H), interpolation=cv2.INTER_AREA)


def _valid_mask():
    m = np.ones((H, W), np.uint8)
    for x0, y0, x1, y1 in OVERLAY_MASKS:
        m[int(y0 * H):int(np.ceil(y1 * H)), int(x0 * W):int(np.ceil(x1 * W))] = 0
    m[:BORDER_PX], m[-BORDER_PX:], m[:, :BORDER_PX], m[:, -BORDER_PX:] = 0, 0, 0, 0
    return m


def _edges(gray):
    """Structural edges: equalise lighting, blur out texture, auto-threshold Canny, drop short bits."""
    g = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(gray)
    g = cv2.bilateralFilter(g, 9, 40, 9)
    g = cv2.GaussianBlur(g, (0, 0), 2.0)
    # Auto thresholds from this image's own gradient distribution, so a dim IR frame
    # and a bright flat render each keep their strongest edges.
    gx = cv2.Sobel(g, cv2.CV_32F, 1, 0, ksize=3)
    gy = cv2.Sobel(g, cv2.CV_32F, 0, 1, ksize=3)
    mag = np.hypot(gx, gy)
    hi = max(float(np.percentile(mag, HI_PCT)), MIN_HI)
    lo = 0.4 * hi
    e = cv2.Canny(g, lo, hi, L2gradient=True)
    e[_valid_mask() == 0] = 0
    n, lab, stats, _ = cv2.connectedComponentsWithStats((e > 0).astype(np.uint8), connectivity=8)
    keep = np.zeros(n, bool)
    keep[1:] = np.maximum(stats[1:, cv2.CC_STAT_WIDTH], stats[1:, cv2.CC_STAT_HEIGHT]) >= MIN_EDGE_LEN
    e = (keep[lab] * 255).astype(np.uint8)
    return e, gx, gy


def _chamfer(src, dst):
    """Mean distance (px) from each edge pixel of src to the nearest edge pixel of dst."""
    if not src.any():
        return TRUNC_PX
    if not dst.any():
        return TRUNC_PX
    dt = cv2.distanceTransform((dst == 0).astype(np.uint8), cv2.DIST_L2, 5)
    d = np.minimum(dt[src > 0], TRUNC_PX)
    return float(d.mean())


def _ori_hist(edges, gx, gy):
    ys, xs = np.nonzero(edges)
    ang = (np.degrees(np.arctan2(gy[ys, xs], gx[ys, xs])) % 180.0)
    b = np.minimum((ang / 180.0 * ORI_BINS).astype(int), ORI_BINS - 1)
    cy = np.minimum(ys * GRID[0] // H, GRID[0] - 1)
    cx = np.minimum(xs * GRID[1] // W, GRID[1] - 1)
    h = np.zeros((GRID[0], GRID[1], ORI_BINS))
    np.add.at(h, (cy, cx, b), 1.0)
    # Light circular smoothing so a 1-bin rotation is not a full miss.
    h = 0.5 * h + 0.25 * np.roll(h, 1, axis=2) + 0.25 * np.roll(h, -1, axis=2)
    return h


def _ori_sim(ha, hb):
    """Edge-count weighted cosine similarity of per-cell orientation histograms (0..1)."""
    sims, wts = [], []
    for i in range(GRID[0]):
        for j in range(GRID[1]):
            a, b = ha[i, j], hb[i, j]
            na, nb = np.linalg.norm(a), np.linalg.norm(b)
            w = a.sum() + b.sum()
            if w == 0:
                continue
            sims.append(0.0 if na == 0 or nb == 0 else float(a @ b / (na * nb)))
            wts.append(w)
    return float(np.average(sims, weights=wts)) if sims else 0.0


def structure_score(real_path, render_path):
    ea, gxa, gya = _edges(_load_gray(real_path))
    eb, gxb, gyb = _edges(_load_gray(render_path))
    real_to_render = _chamfer(ea, eb)
    render_to_real = _chamfer(eb, ea)
    chamfer = 0.5 * (real_to_render + render_to_real)
    osim = _ori_sim(_ori_hist(ea, gxa, gya), _ori_hist(eb, gxb, gyb))
    s_ch = max(0.0, 1.0 - chamfer / TRUNC_PX)
    score = 100.0 * (0.6 * s_ch + 0.4 * osim)
    return {
        "chamfer_px": round(chamfer, 2),
        "chamfer_real_to_render_px": round(real_to_render, 2),
        "chamfer_render_to_real_px": round(render_to_real, 2),
        "orientation_sim": round(osim, 3),
        "score": round(score, 1),
    }


def side_by_side(real, render, out, label=None):
    """Three panels: real with its edges, render with its edges, and both edge sets overlaid
    (real = cyan, render = magenta, agreement within 3 px = white)."""
    ga, gb = _load_gray(real), _load_gray(render)
    ea, eb = _edges(ga)[0] > 0, _edges(gb)[0] > 0

    def tint(gray, e, col):
        img = cv2.cvtColor((gray * 0.55).astype(np.uint8), cv2.COLOR_GRAY2BGR)
        img[cv2.dilate(e.astype(np.uint8), np.ones((2, 2), np.uint8)) > 0] = col
        return img

    cyan, magenta = (255, 255, 0), (255, 0, 255)
    p1, p2 = tint(ga, ea, cyan), tint(gb, eb, magenta)
    ov = np.full((H, W, 3), 15, np.uint8)
    k = np.ones((2, 2), np.uint8)
    da, db = cv2.dilate(ea.astype(np.uint8), k) > 0, cv2.dilate(eb.astype(np.uint8), k) > 0
    ov[da], ov[db] = cyan, magenta
    near = cv2.dilate(ea.astype(np.uint8), np.ones((7, 7), np.uint8)) > 0
    ov[db & near] = (255, 255, 255)
    sheet = np.concatenate([p1, p2, ov], axis=1)
    bar = np.full((34, sheet.shape[1], 3), 25, np.uint8)
    s = structure_score(real, render)
    txt = label or ""
    txt = (txt + "   " if txt else "") + (
        f"score {s['score']:.1f}   chamfer {s['chamfer_px']:.1f}px   orientation {s['orientation_sim']:.2f}")
    cv2.putText(bar, "real edges", (10, 23), cv2.FONT_HERSHEY_SIMPLEX, 0.6, cyan, 1, cv2.LINE_AA)
    cv2.putText(bar, "render edges", (W + 10, 23), cv2.FONT_HERSHEY_SIMPLEX, 0.6, magenta, 1, cv2.LINE_AA)
    cv2.putText(bar, txt, (2 * W + 10, 23), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 1, cv2.LINE_AA)
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(out), np.concatenate([bar, sheet], axis=0))
    return str(out)


def _main():
    ap = argparse.ArgumentParser()
    ap.add_argument("real")
    ap.add_argument("render")
    ap.add_argument("--overlay")
    a = ap.parse_args()
    print(json.dumps(structure_score(a.real, a.render)))
    if a.overlay:
        print(side_by_side(a.real, a.render, a.overlay))


if __name__ == "__main__":
    _main()
