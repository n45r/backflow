"""Aerial orbit of Argon's 3D site with the calibrated model's water at its peak, for the video opening."""
import json
import math
import subprocess
import sys
from pathlib import Path

from backend.render import Renderer

ROOT = Path(__file__).resolve().parent.parent
FF = "/opt/homebrew/bin/ffmpeg"


def main(run="calib_video", frames=150):
    d = ROOT / "runs" / "loop" / run
    frozen = json.loads((d / "frozen.json").read_text())
    rounds = sorted(d.glob("round_*/round.json"))
    depths = json.loads(Path(json.loads(rounds[-1].read_text())["depths"]).read_text())
    s6 = depths["depth_m"]["s6"]
    t_peak = depths["t"][max(range(len(s6)), key=lambda i: s6[i])]
    out = ROOT / "runs" / "submission" / "orbit"
    out.mkdir(parents=True, exist_ok=True)
    r = Renderer(width=1280, height=720)
    r.site = frozen["site"]
    url = "/" + str(Path(frozen["scene"]).relative_to(ROOT / "web"))
    cx, cz = 12.25, 11.35
    paths = []
    for i in range(frames):
        a = 2 * math.pi * i / frames
        r.patch = dict(frozen.get("patch") or {})
        r.patch["cameras"] = dict(r.patch.get("cameras") or {})
        r.patch["cameras"]["overview"] = {"position": [cx + 22 * math.cos(a), 15, cz + 22 * math.sin(a)],
                                          "lookAt": [cx, -0.5, cz], "fov": 50}
        paths += r.render(url, depths, "overview", [t_peak], out / f"f{i:04d}")
    r.close()
    for i, p in enumerate(paths):
        Path(p).replace(out / f"o_{i:04d}.png")
    subprocess.run([FF, "-y", "-v", "error", "-framerate", "25", "-i", str(out / "o_%04d.png"), "-pix_fmt", "yuv420p",
                    "-vf", "scale=1920:1080", str(out.parent / "orbit.mp4")], check=True)
    print(out.parent / "orbit.mp4", "peak t", t_peak)


if __name__ == "__main__":
    main(*(sys.argv[1:2] or []))
