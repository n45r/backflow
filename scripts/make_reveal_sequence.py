"""16 s reveal on the hidden flood: real camera, untuned model and corrected model play on one clock, the depth chart
draws in under them, then the sensor line appears."""
import json
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from backend import frames  # noqa: E402
from backend.contact import _font  # noqa: E402
from backend.render import Renderer  # noqa: E402

FF = "/opt/homebrew/bin/ffmpeg"
W, H, FPS = 1920, 1080, 30
BG, INK, QUIET, LINE = (11, 11, 12), (236, 236, 236), (130, 130, 135), (40, 40, 44)
BEFORE, AFTER, SENSOR = (150, 150, 155), (90, 160, 255), (245, 245, 245)


def mae(a, b):
    return sum(abs(x - y) for x, y in zip(a, b)) / len(a)


def main(run="calib_video", out_name="reveal_seq.mp4", durs=(9, 3, 4)):
    d = ROOT / "runs" / "loop" / run
    hold = json.loads((d / "holdout.json").read_text())
    rev = json.loads((ROOT / "runs" / "reveal" / f"{run}.json").read_text())
    event = hold["event"]
    t_rev = rev["t"]
    g = rev["gauges"]["s6"]
    measured, before, after = g["measured_m"], g["blind_m"], g["informed_m"]
    print("check mm: before", round(1000 * mae(before, measured), 1), "after", round(1000 * mae(after, measured), 1))
    times = list(range(60, 901, 10))
    work = ROOT / "runs" / "submission" / "reveal"
    real = frames.real_frames(event, "cam5", times, work / "real")
    r = Renderer()
    r.site = json.loads((d / "frozen.json").read_text())["site"]
    r.patch = hold["informed_patch"]
    url = "/" + str(Path(hold["informed_scene"]).relative_to(ROOT / "web"))
    ren_after = r.render(url, hold["informed_depths"], "cam5", times, work / "after")
    ren_before = r.render(url, hold["blind_depths"], "cam5", times, work / "before")
    r.close()

    pw, ph, gap, top = 600, 338, 30, 120
    x0 = (W - 3 * pw - 2 * gap) // 2
    cx0, cx1, cy0, cy1 = x0, W - x0, 600, 940
    peak = max(max(measured), max(before), max(after)) or 1
    tmax = t_rev[-1]

    def px(t, v):
        return cx0 + (cx1 - cx0) * t / tmax, cy1 - (cy1 - cy0) * v / peak

    def compose(i, t_now, sensor_frac, final):
        im = Image.new("RGB", (W, H), BG)
        dr = ImageDraw.Draw(im)
        f40, f26 = _font(40), _font(26)
        title = "The test: a different flood the model has never seen"
        dr.text(((W - dr.textlength(title, font=f40)) / 2, 40), title, fill=INK, font=f40)
        panels = [(real[i], "Real camera", INK), (ren_before[i], "Before: untuned model", BEFORE),
                  (ren_after[i], "After watching one other flood", AFTER)]
        for k, (p, label, col) in enumerate(panels):
            x = x0 + k * (pw + gap)
            im.paste(Image.open(p).convert("RGB").resize((pw, ph)), (x, top))
            dr.text((x, top + ph + 14), label, fill=col, font=f26)
        dr.text((cx1 - 90, top + ph + 14), f"{int(t_now) // 60}:{int(t_now) % 60:02d}", fill=QUIET, font=f26)
        dr.line([(cx0, cy1), (cx1, cy1)], fill=LINE, width=2)
        dr.text((cx0, cy0 - 50), "Water depth", fill=QUIET, font=f26)
        n = max(2, sum(1 for t in t_rev if t <= t_now))
        for series, col in ((before, BEFORE), (after, AFTER)):
            dr.line([px(t_rev[j], series[j]) for j in range(n)], fill=col, width=4)
        if sensor_frac > 0:
            m = max(2, int(len(t_rev) * sensor_frac))
            dr.line([px(t_rev[j], measured[j]) for j in range(m)], fill=SENSOR, width=3)
            dr.text((cx0, cy1 + 20), "White: the water-level sensor, revealed only now", fill=SENSOR, font=f26)
        if final:
            dr.rectangle([0, cy0 - 70, W, H], fill=BG)
            f60, f30 = _font(64), _font(32)
            l1 = "More than 5 times more accurate"
            l2 = "after watching one flood. In the range researchers get with water sensors."
            dr.text(((W - dr.textlength(l1, font=f60)) / 2, cy0 + 40), l1, fill=INK, font=f60)
            dr.text(((W - dr.textlength(l2, font=f30)) / 2, cy0 + 150), l2, fill=QUIET, font=f30)
        return im

    seq = work / "seq"
    seq.mkdir(parents=True, exist_ok=True)
    n_play, n_sensor, n_hold = (int(x * FPS) for x in durs)
    k = 0
    for j in range(n_play):
        i = min(len(times) - 1, int(len(times) * j / n_play))
        compose(i, times[i], 0, False).save(seq / f"r_{k:04d}.png"); k += 1
    for j in range(n_sensor):
        compose(len(times) - 1, times[-1], (j + 1) / n_sensor, False).save(seq / f"r_{k:04d}.png"); k += 1
    last = compose(len(times) - 1, times[-1], 1, True)
    for j in range(n_hold):
        last.save(seq / f"r_{k:04d}.png"); k += 1
    dst = ROOT / "runs" / "submission" / out_name
    subprocess.run([FF, "-y", "-v", "error", "-framerate", str(FPS), "-i", str(seq / "r_%04d.png"), "-pix_fmt", "yuv420p",
                    "-c:v", "libx264", str(dst)], check=True)
    print(dst, k / FPS, "s")


if __name__ == "__main__":
    main()
