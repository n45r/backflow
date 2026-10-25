"""Final 60 s submission video: night clip, Argon's scene fix, then the recorded app take, with voice-over.

The voice-over uses the macOS voice as a placeholder; replace runs/submission/final_voice.wav with a recorded one and
run again with --keep-voice to remux.
"""
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from scripts.make_submission_video import FF, H, OUT, W, card, clip, ff, triptych, voice  # noqa: E402

LINES = [
    (8, "This is a real flood test site, filmed from many cameras: the pond, the channels, the basement, by day and by night."),
    (10, "Argon reads the site plan and the footage, and builds one 3D model of the whole site. It even caught a drain missing "
         "from its own scene and fixed its code."),
    (16, "The water in that model comes from a drainage simulation. Argon watches the real flood beside three versions of it, "
         "and picks the best match. No sensors. Only video."),
    (16, "Then the real test: a flood it never saw. Off by 34 millimetres before. Off by 6 after watching one flood, within "
         "the range of the researchers' sensor-based tuning."),
    (6, "Flood video in. A flood model you can trust out."),
]


def still(img, secs, out):
    """A card with a slow push-in, so the frame is never frozen."""
    n = int(secs * 30)
    ff("-loop", "1", "-i", str(img), "-vf",
       f"scale=3840:2160,zoompan=z='1+0.06*on/{n}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={n}:s={W}x{H}:fps=30,format=yuv420p",
       "-frames:v", str(n), "-c:v", "libx264", str(out))
    return out


def mosaic(out, secs, views=None):
    """Real cameras at once, in a clean grid: columns are places on the site, rows are day and night.
    views: list of rows, each a list of (source video, start seconds, label)."""
    from PIL import Image, ImageDraw
    from backend.contact import _font
    if views is None:
        views = [[(ROOT / "data/clips/20_cam1.mp4", 180, "Pond"), (ROOT / "data/clips/20_cam5.mp4", 200, "Basement")],
                 [(ROOT / "data/clips/32_cam1.mp4", 240, "Pond"), (ROOT / "data/clips/32_cam5.mp4", 250, "Basement")]]
    rows, cols = len(views), len(views[0])
    top = 96
    cw, ch = 1920 // cols, (1080 - top) // rows
    args, chains, labels = [], [], []
    k = 0
    for r, row in enumerate(views):
        for c, (src, start, label) in enumerate(row):
            args += ["-ss", str(start), "-t", str(secs * 12), "-i", str(src)]
            chains.append(f"[{k}:v]setpts=PTS/12,scale={cw}:{ch}:force_original_aspect_ratio=increase,crop={cw}:{ch},setsar=1[v{k}]")
            labels.append((c * cw, top + r * ch, label + (", day" if r == 0 else ", night") if rows > 1 else label))
            k += 1
    overlay = Image.new("RGBA", (1920, 1080), (0, 0, 0, 0))
    d = ImageDraw.Draw(overlay)
    d.rectangle([0, 0, 1920, top], fill=(11, 11, 12, 255))
    title = "One site, many cameras"
    f = _font(40)
    d.text(((1920 - d.textlength(title, font=f)) / 2, 26), title, fill=(236, 236, 236, 255), font=f)
    fade = 90
    for x, y, label in labels:
        for i in range(fade):
            a = int(150 * i / fade)
            d.line([(x, y + ch - fade + i), (x + cw, y + ch - fade + i)], fill=(0, 0, 0, a))
        d.text((x + 24, y + ch - 52), label, fill=(240, 240, 240, 255), font=_font(30))
    overlay.save(OUT / "mosaic_overlay.png")
    layout = "|".join(f"{(i % cols) * cw}_{top + (i // cols) * ch}" for i in range(k))
    filt = ";".join(chains) + f";color=c=0x0b0b0c:s=1920x1080:d={secs}[bg];" + "".join(f"[v{i}]" for i in range(k)) + \
        f"xstack=inputs={k}:layout={'|'.join(f'{(i % cols) * cw}_{(i // cols) * ch}' for i in range(k))}[m];" + \
        f"[bg][m]overlay=0:{top}[b];[b][{k}:v]overlay=0:0,format=yuv420p[out]"
    ff(*args, "-i", str(OUT / "mosaic_overlay.png"), "-filter_complex", filt, "-map", "[out]", "-t", str(secs), "-r", "30",
       "-c:v", "libx264", str(out))
    return out

def titled(src_mp4, title, out):
    """Put a clean title bar over a clip."""
    from PIL import Image, ImageDraw
    from backend.contact import _font
    ov = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(ov)
    d.rectangle([0, 0, W, 110], fill=(11, 11, 12, 235))
    f = _font(44)
    d.text(((W - d.textlength(title, font=f)) / 2, 30), title, fill=(236, 236, 236, 255), font=f)
    png = out.with_suffix(".png")
    ov.save(png)
    ff("-i", str(src_mp4), "-i", str(png), "-filter_complex", "[0:v][1:v]overlay=0:0,format=yuv420p", "-c:v", "libx264", str(out))
    return out


def agents_segment(out, secs=6):
    """Three Managed Agents, one per theory of how the water gets in, from a recorded run."""
    from PIL import Image, ImageDraw
    from backend.contact import _font
    src = ROOT / "runs/loop/ma_demo/round_01/round.json"
    if not src.exists():
        src = ROOT / "runs/loop/calib_workers/round_01/round.json"
    rec = json.loads(src.read_text())
    ph = rec["workers"]["per_hypothesis"]
    theories = [("sewer", "Water comes up the floor drain"), ("door", "Water comes in under the door"), ("both", "Both ways")]
    work = OUT / "agents"
    work.mkdir(exist_ok=True)
    n = int(secs * 30)
    f44, f30, f26 = _font(44), _font(30), _font(26)
    cw, gap = 520, 40
    x0 = (W - 3 * cw - 2 * gap) // 2
    for i in range(n):
        im = Image.new("RGB", (W, H), (11, 11, 12))
        d = ImageDraw.Draw(im)
        title = "Gemini Managed Agents: one agent per theory"
        d.text(((W - d.textlength(title, font=f44)) / 2, 40), title, fill=(236, 236, 236), font=f44)
        sub = "Each agent runs the drainage simulation in its own cloud sandbox and tunes the settings for its theory"
        d.text(((W - d.textlength(sub, font=f26)) / 2, 110), sub, fill=(130, 130, 135), font=f26)
        for k, (key, label) in enumerate(theories):
            x, y = x0 + k * (cw + gap), 220
            d.rounded_rectangle([x, y, x + cw, y + 640], 14, outline=(48, 48, 52), width=2)
            d.text((x + 30, y + 30), f"Agent {k + 1}", fill=(130, 130, 135), font=f26)
            d.text((x + 30, y + 70), label, fill=(236, 236, 236), font=f30)
            v = ph.get(key) or {}
            frac = i / n
            if frac < 0.4:
                dots = "." * (1 + (i // 8) % 3)
                d.text((x + 30, y + 160), f"Running simulations{dots}", fill=(90, 160, 255), font=f30)
                continue
            if v.get("best_knobs"):
                runs = v.get("n_cal_runs_logged") or v.get("n_cal_runs_reported") or 0
                lines = [("Finished", (90, 160, 255)),
                         (f"{runs} simulation runs", (236, 236, 236)),
                         (f"{int(v.get('wall_seconds') or 0) // 60} min {int(v.get('wall_seconds') or 0) % 60} s", (236, 236, 236)),
                         ("Best settings found:", (130, 130, 135))]
                for kk, vv in v["best_knobs"].items():
                    lines.append((f"  {kk.replace('_', ' ')}  {vv:.3g}", (200, 200, 205)))
            else:
                lines = [("Did not finish in time", (130, 130, 135)), ("Left out of the comparison", (130, 130, 135))]
            for j, (s, col) in enumerate(lines):
                d.text((x + 30, y + 160 + j * 52), s, fill=col, font=f30)
        foot = "Then Argon watches each agent's version beside the real flood, and picks"
        d.text(((W - d.textlength(foot, font=f30)) / 2, H - 120), foot, fill=(236, 236, 236), font=f30)
        im.save(work / f"a_{i:04d}.png")
    ff("-framerate", "30", "-i", str(work / "a_%04d.png"), "-pix_fmt", "yuv420p", "-c:v", "libx264", str(out))
    return out



def end_card(out):
    from PIL import Image, ImageDraw
    from backend.contact import _font
    im = Image.new("RGB", (W, H), (11, 11, 12))
    d = ImageDraw.Draw(im)
    for y, s, f, col in ((380, "Backflow", _font(96), (236, 236, 236)),
                         (520, "Flood video in. A checked flood model out.", _font(44), (236, 236, 236)),
                         (640, "Gemini 4 Argon  ·  Managed Agents  ·  github.com/n45r/backflow", _font(30), (130, 130, 135))):
        d.text(((W - d.textlength(s, font=f)) / 2, y), s, fill=col, font=f)
    im.save(out)
    return out


def take_segment(src, start, dur_src, secs, out):
    return clip(src, start, dur_src, secs, out)


def main(keep_voice=False):
    take = OUT / "app_take.webm"
    RUN_DIR = ROOT / "runs" / "loop" / "calib_video"
    marks = {m["step"]: m["t"] for m in json.loads((OUT / "app_take_marks.json").read_text())}
    night = ROOT / "data" / "clips" / "32_cam5.mp4"
    scene_fix = OUT / "scene_fix.png"
    segs = [
        mosaic(OUT / "f0.mp4", 4, views=[
            [(ROOT / "data/clips/20_cam1.mp4", 180, "Pond"),
             (ROOT / "data/raw/video/161006A/cam3/c3_cam3_instar_161006_143254_144255.avi", 330, "Channel"),
             (ROOT / "data/clips/20_cam5.mp4", 200, "Building")],
            [(ROOT / "data/clips/32_cam1.mp4", 240, "Pond"),
             (ROOT / "data/raw/video/161006B/cam3/c3_cam3_instar_161006_211833_212838.avi", 120, "Channel"),
             (ROOT / "data/clips/32_cam5.mp4", 250, "Building")]]),
        still(card(OUT / "plan.png", OUT / "f0b.png", "Gemini 4 Argon reads the site plan"), 2.5, OUT / "f0b.mp4"),
        titled(clip(OUT / "orbit.mp4", 0, 6, 4, OUT / "f1a_raw.mp4"), "...and builds the whole site in 3D, in one pass", OUT / "f1a.mp4"),
        still(card(triptych([RUN_DIR / "round_00/real/32_cam5_t00000.jpg", RUN_DIR / "round_00/render_0/cam5_t00000.png",
                             sorted((RUN_DIR / "round_00").glob("render_*/cam5_t00000.png"))[-1]],
                            ["Real camera", "Argon's first scene", "After Argon fixed it"], OUT / "fix3.png"),
                   OUT / "f1.png", "Argon noticed its scene was missing the drain, and rewrote its code"), 4, OUT / "f1.mp4"),
        agents_segment(OUT / "f_agents.mp4", 6),
        OUT / "round_seq.mp4",
        OUT / "reveal_seq.mp4",
        still(end_card(OUT / "f4.png"), 4.5, OUT / "f4.mp4"),
    ]
    (OUT / "fv.txt").write_text("".join(f"file '{s}'\n" for s in segs))
    ff("-f", "concat", "-safe", "0", "-i", str(OUT / "fv.txt"), "-c", "copy", str(OUT / "final_video_only.mp4"))
    vo = OUT / "final_voice.wav"
    if not keep_voice or not vo.exists():
        parts = [voice(text, secs, OUT / f"fa{i}.wav") for i, (secs, text) in enumerate(LINES)]
        (OUT / "fa.txt").write_text("".join(f"file '{p}'\n" for p in parts))
        ff("-f", "concat", "-safe", "0", "-i", str(OUT / "fa.txt"), "-c", "pcm_s16le", str(vo))
    ff("-i", str(OUT / "final_video_only.mp4"), "-i", str(vo), "-c:v", "copy", "-c:a", "aac", "-shortest",
       str(OUT / "backflow_final.mp4"))
    print(OUT / "backflow_final.mp4")


if __name__ == "__main__":
    main("--keep-voice" in sys.argv)
