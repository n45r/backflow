"""Burn subtitles into a video as image overlays (this ffmpeg build has no subtitle filter)."""
import json
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from backend.contact import _font  # noqa: E402

FF = "/opt/homebrew/bin/ffmpeg"
W, H = 1920, 1080


def wrap(d, text, f, maxw):
    lines, cur = [], ""
    for w in text.split():
        t = (cur + " " + w).strip()
        if d.textlength(t, font=f) > maxw and cur:
            lines.append(cur); cur = w
        else:
            cur = t
    return lines + [cur]


def sub_png(text, out):
    im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    f = _font(40)
    lines = wrap(d, text, f, 1500)
    lh = 52
    top = H - 40 - lh * len(lines) - 24
    d.rectangle([0, top, W, H], fill=(11, 11, 12, 225))
    for i, s in enumerate(lines):
        d.text(((W - d.textlength(s, font=f)) / 2, top + 16 + i * lh), s, fill=(245, 245, 245, 255), font=f)
    im.save(out)


def main(video, subs_json, out):
    subs = json.loads(Path(subs_json).read_text())
    work = Path(out).with_suffix("")
    work.mkdir(parents=True, exist_ok=True)
    args, chain, last = ["-i", str(video)], [], "0:v"
    for i, s in enumerate(subs):
        png = work / f"sub_{i:02d}.png"
        sub_png(s["text"], png)
        args += ["-i", str(png)]
        tag = f"v{i}"
        chain.append(f"[{last}][{i + 1}:v]overlay=0:0:enable='between(t,{s['start']:.2f},{s['end']:.2f})'[{tag}]")
        last = tag
    subprocess.run([FF, "-y", "-v", "error", *args, "-filter_complex", ";".join(chain), "-map", f"[{last}]", "-map", "0:a?",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "copy", str(out)], check=True)
    print(out)


if __name__ == "__main__":
    main(*sys.argv[1:4])
