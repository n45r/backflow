"""16 s sequence of one recorded round, every step shown: simulate, draw in 3D, send, Argon watching, verdict."""
import json
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageEnhance

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from backend.contact import _font  # noqa: E402

FF = "/opt/homebrew/bin/ffmpeg"
W, H, FPS = 1920, 1080, 30
BG, INK, QUIET, ACCENT = (11, 11, 12), (236, 236, 236), (120, 120, 125), (90, 160, 255)
STEPS = ["Simulate", "Draw in 3D", "Send video", "Argon watching", "Verdict"]
COLORS = {"A": (170, 170, 175), "B": (90, 160, 255), "C": (230, 140, 90)}


def step_line(d, cur):
    f = _font(26)
    x = 80
    for i, s in enumerate(STEPS):
        d.text((x, 48), s, fill=INK if i == cur else QUIET, font=f)
        x += d.textlength(s, font=f) + 26
        if i < len(STEPS) - 1:
            d.text((x - 18, 48), "·", fill=QUIET, font=f)


def caption(d, text):
    f = _font(30)
    d.text((80, H - 90), text, fill=INK, font=f)


def frame_curves(depths, t, frac):
    im = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(im)
    step_line(d, 0)
    x0, y0, x1, y1 = 160, 220, W - 160, H - 200
    peak = max(max(v["s6"]) for v in depths.values()) or 1
    n = len(t)
    upto = max(2, int(n * frac))
    for L, v in depths.items():
        pts = [(x0 + (x1 - x0) * i / (n - 1), y1 - (y1 - y0) * v["s6"][i] / peak) for i in range(upto)]
        d.line(pts, fill=COLORS[L], width=4)
        d.text((pts[-1][0] + 10, pts[-1][1] - 18), L, fill=COLORS[L], font=_font(30))
    d.line([(x0, y1), (x1, y1)], fill=(40, 40, 44), width=1)
    caption(d, "SWMM simulates three versions of the model: water depth in the basement over time")
    return im


def fit(img, box_w, box_h):
    s = min(box_w / img.width, box_h / img.height)
    return img.resize((int(img.width * s), int(img.height * s)))


def frame_grid(g, cur, text, playhead=None, pulse=False):
    im = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(im)
    step_line(d, cur)
    gi = fit(Image.open(g).convert("RGB"), W - 160, H - 260)
    x, y = (W - gi.width) // 2, 120
    im.paste(gi, (x, y))
    if playhead is not None:
        by = y + gi.height + 18
        d.line([(x, by), (x + gi.width, by)], fill=(40, 40, 44), width=3)
        d.line([(x, by), (x + int(gi.width * playhead), by)], fill=ACCENT, width=3)
    if pulse:
        d.rectangle([x - 3, y - 3, x + gi.width + 3, y + gi.height + 3], outline=ACCENT, width=2)
    caption(d, text)
    return im


def frame_verdict(g, winner, line):
    base = Image.open(g).convert("RGB")
    w2, h2 = base.width // 2, base.height // 2
    tiles = {"REAL": (0, 0), "A": (1, 0), "B": (0, 1), "C": (1, 1)}
    for name, (cx, cy) in tiles.items():
        if name in ("REAL", winner):
            continue
        box = (cx * w2, cy * h2, (cx + 1) * w2, (cy + 1) * h2)
        base.paste(ImageEnhance.Brightness(base.crop(box)).enhance(0.35), box[:2])
    d0 = ImageDraw.Draw(base)
    cx, cy = tiles[winner]
    d0.rectangle([cx * w2 + 2, cy * h2 + 2, (cx + 1) * w2 - 3, (cy + 1) * h2 - 3], outline=ACCENT, width=6)
    tmp = ROOT / "runs" / "submission" / "_verdict_grid.png"
    base.save(tmp)
    return frame_grid(tmp, 4, line)


def main(run="calib_video", rnd=2, out_name="round_seq.mp4"):
    rd = ROOT / "runs" / "loop" / run / f"round_{rnd:02d}"
    rec = json.loads((rd / "round.json").read_text())
    depths = {}
    for L in ("A", "B", "C"):
        p = ROOT / "runs" / f"loop_{run}_r{rnd:02d}_{L}" / "depths.json"
        dj = json.loads(p.read_text())
        depths[L] = dj["depth_m"]
        t = dj["t"]
    grids = sorted((rd / "grid").glob("g_*.png"))
    out = ROOT / "runs" / "submission" / "seq"
    out.mkdir(parents=True, exist_ok=True)
    frames = []
    for i in range(3 * FPS):
        frames.append(frame_curves(depths, t, (i + 1) / (3 * FPS)))
    for i in range(5 * FPS):
        g = grids[min(len(grids) - 1, int(len(grids) * i / (5 * FPS)))]
        frames.append(frame_grid(g, 1, "Each version is drawn in Argon's 3D scene, from the real camera's angle, beside the real flood"))
    for i in range(1 * FPS):
        frames.append(frame_grid(grids[len(grids) // 2], 2, "Stitched into one time-lapse and sent to Argon"))
    for i in range(4 * FPS):
        g = grids[min(len(grids) - 1, int(len(grids) * i / (4 * FPS)))]
        frames.append(frame_grid(g, 3, "Argon is watching the whole flood: real camera top left, versions A, B and C",
                                 playhead=i / (4 * FPS), pulse=(i // 10) % 2 == 0))
    w = rec["winner"]
    gi = grids[min(len(grids) - 1, int(len(grids) * 0.45))]
    line = f"Argon picks {w}: less water. The real floor floods later and less than the untuned model."
    v = frame_verdict(gi, w, line)
    frames += [v] * (3 * FPS)
    for i, f in enumerate(frames):
        f.save(out / f"s_{i:04d}.png")
    dst = ROOT / "runs" / "submission" / out_name
    subprocess.run([FF, "-y", "-v", "error", "-framerate", str(FPS), "-i", str(out / "s_%04d.png"), "-pix_fmt", "yuv420p",
                    "-c:v", "libx264", str(dst)], check=True)
    print(dst, len(frames) / FPS, "s")


if __name__ == "__main__":
    main()
