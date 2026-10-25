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


def mosaic(out, secs):
    """Four real cameras at once: pond and basement, day (event 20) and night (event 32), each sped up."""
    from PIL import Image, ImageDraw
    from backend.contact import _font
    clips = [(ROOT / "data/clips/20_cam1.mp4", 180, "Pond, day"), (ROOT / "data/clips/20_cam5.mp4", 200, "Basement, day"),
             (ROOT / "data/clips/32_cam1.mp4", 240, "Pond, night"), (ROOT / "data/clips/32_cam5.mp4", 250, "Basement, night")]
    args, inputs = [], []
    for i, (src, start, _) in enumerate(clips):
        args += ["-ss", str(start), "-t", str(secs * 12), "-i", str(src)]
        inputs.append(f"[{i}:v]setpts=PTS/12,scale=960:540:force_original_aspect_ratio=decrease,pad=960:540:(ow-iw)/2:(oh-ih)/2,setsar=1[v{i}]")
    overlay = Image.new("RGBA", (1920, 1080), (0, 0, 0, 0))
    d = ImageDraw.Draw(overlay)
    for i, (_, _, label) in enumerate(clips):
        x, y = (i % 2) * 960, (i // 2) * 540
        d.rectangle([x + 16, y + 470, x + 16 + 26 * len(label) // 2 + 40, y + 520], fill=(0, 0, 0, 170))
        d.text((x + 30, y + 476), label, fill="white", font=_font(34))
    d.rectangle([660, 500, 1260, 580], fill=(0, 0, 0, 190))
    d.text((690, 512), "One site, many cameras", fill="white", font=_font(48))
    overlay.save(OUT / "mosaic_overlay.png")
    filt = ";".join(inputs) + ";[v0][v1][v2][v3]xstack=inputs=4:layout=0_0|w0_0|0_h0|w0_h0[m];[m][4:v]overlay=0:0,format=yuv420p[out]"
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
        mosaic(OUT / "f0.mp4", 5),
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
