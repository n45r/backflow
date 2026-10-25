"""Side-by-side video: real camera frames beside the simulation render, for a run's depths and scene."""
import json
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageDraw

from backend import frames
from backend.contact import _font
from backend.render import Renderer

ROOT = Path(__file__).resolve().parent.parent
FFMPEG = "/opt/homebrew/bin/ffmpeg"


def make(run, label, event, start_s, end_s, step_s, out_name, patch=None, scene=None, depths=None, fps=4):
    d = ROOT / "runs" / "loop" / run
    frozen = json.loads((d / "frozen.json").read_text())
    scene = scene or frozen["scene"]
    if depths is None:
        depths = json.loads((d / "holdout.json").read_text())[f"{label}_depths"]
    out = ROOT / "runs" / "videos" / out_name
    work = out.with_suffix("")
    work.mkdir(parents=True, exist_ok=True)
    times = list(range(start_s, end_s + 1, step_s))
    real = frames.real_frames(event, "cam5", times, work / "real")
    r = Renderer()
    r.site = frozen["site"]
    r.patch = frozen.get("patch") if patch is None else patch
    url = "/" + str(Path(scene).relative_to(ROOT / "web"))
    renders = r.render(url, depths, "cam5", times, work / "render")
    r.close()
    font = _font(22)
    for i, (a, b, t) in enumerate(zip(real, renders, times)):
        A = Image.open(a).convert("RGB").resize((640, 360))
        B = Image.open(b).convert("RGB").resize((640, 360))
        im = Image.new("RGB", (1290, 410), (15, 15, 20))
        im.paste(A, (0, 50)); im.paste(B, (650, 50))
        dr = ImageDraw.Draw(im)
        dr.text((10, 12), "Real camera", fill="white", font=font)
        dr.text((660, 12), f"Simulation ({label})", fill="white", font=font)
        dr.text((1120, 12), f"t = {t // 60}:{t % 60:02d}", fill="white", font=font)
        im.save(work / f"f_{i:04d}.png")
    subprocess.run([FFMPEG, "-y", "-v", "error", "-framerate", str(fps), "-i", str(work / "f_%04d.png"),
                    "-pix_fmt", "yuv420p", "-vf", "scale=1290:-2", str(out)], check=True)
    return out


if __name__ == "__main__":
    run = sys.argv[1] if len(sys.argv) > 1 else "calib_v3"
    d = ROOT / "runs" / "loop" / run
    rounds = sorted(d.glob("round_*/round.json"))
    last = json.loads(rounds[-1].read_text())
    print(make(run, "informed", 32, 120, 600, 6, f"{run}_ev32_informed.mp4", depths=last["depths"]))
