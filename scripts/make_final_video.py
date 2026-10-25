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
from scripts.make_submission_video import FF, OUT, card, clip, ff, still, triptych, voice  # noqa: E402

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

def take_segment(src, start, dur_src, secs, out):
    return clip(src, start, dur_src, secs, out)


def main(keep_voice=False):
    take = OUT / "app_take.webm"
    RUN_DIR = ROOT / "runs" / "loop" / "calib_video"
    marks = {m["step"]: m["t"] for m in json.loads((OUT / "app_take_marks.json").read_text())}
    night = ROOT / "data" / "clips" / "32_cam5.mp4"
    scene_fix = OUT / "scene_fix.png"
    segs = [
        mosaic(OUT / "f0.mp4", 5, views=[
            [(ROOT / "data/clips/20_cam1.mp4", 180, "Pond"),
             (ROOT / "data/raw/video/161006A/cam3/c3_cam3_instar_161006_143254_144255.avi", 330, "Channel"),
             (ROOT / "data/clips/20_cam5.mp4", 200, "Basement")],
            [(ROOT / "data/clips/32_cam1.mp4", 240, "Pond"),
             (ROOT / "data/raw/video/161006B/cam3/c3_cam3_instar_161006_211833_212838.avi", 120, "Channel"),
             (ROOT / "data/clips/32_cam5.mp4", 250, "Basement")]]),
        still(card(OUT / "plan.png", OUT / "f0b.png", "Plus the site plan"), 3, OUT / "f0b.mp4"),
        clip(OUT / "orbit.mp4", 0, 6, 5, OUT / "f1a.mp4"),
        still(card(triptych([RUN_DIR / "round_00/real/32_cam5_t00000.jpg", RUN_DIR / "round_00/render_0/cam5_t00000.png",
                             sorted((RUN_DIR / "round_00").glob("render_*/cam5_t00000.png"))[-1]],
                            ["Real camera", "Argon's first scene", "After Argon fixed it"], OUT / "fix3.png"),
                   OUT / "f1.png", "Argon noticed its scene was missing the drain, and rewrote its code"), 5, OUT / "f1.mp4"),
        OUT / "round_seq.mp4",
        take_segment(take, marks["reveal view"], 13, 16, OUT / "f3.mp4"),
        still(card(None, OUT / "f4.png", "Backflow  ·  github.com/n45r/backflow"), 6, OUT / "f4.mp4"),
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
