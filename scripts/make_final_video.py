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
from scripts.make_submission_video import FF, OUT, card, clip, ff, still, voice  # noqa: E402

LINES = [
    (14, "Engineers use a flood model called SWMM to decide how to protect buildings like this one. But some of its settings "
         "are guesses. Untuned, it floods this basement four times too deep."),
    (10, "We check it with video instead. Argon read the site plan and built this 3D scene. It even spotted its own missing "
         "drain and fixed its code."),
    (16, "Now Argon watches the real flood beside three versions of the model, and picks the best match. No sensors. Only video."),
    (16, "Then the real test: a flood it never saw. The error drops from 34 millimetres to 6, within the range of the "
         "researchers' sensor-based tuning."),
    (4, "Flood video in. A model you can trust out."),
]


def take_segment(src, start, dur_src, secs, out):
    return clip(src, start, dur_src, secs, out)


def main(keep_voice=False):
    take = OUT / "app_take.webm"
    marks = {m["step"]: m["t"] for m in json.loads((OUT / "app_take_marks.json").read_text())}
    night = ROOT / "data" / "clips" / "32_cam5.mp4"
    scene_fix = OUT / "scene_fix.png"
    segs = [
        clip(night, 240, 140, 14, OUT / "f0.mp4"),
        still(card(scene_fix, OUT / "f1.png", "Argon built the 3D site, then fixed its own scene"), 10, OUT / "f1.mp4"),
        take_segment(take, marks["run clicked"], marks["verdict"] - marks["run clicked"], 6, OUT / "f2a.mp4"),
        take_segment(take, marks["verdict"], 10, 10, OUT / "f2b.mp4"),
        take_segment(take, marks["reveal view"], 13, 16, OUT / "f3.mp4"),
        still(card(None, OUT / "f4.png", "Backflow    github.com/n45r/backflow"), 4, OUT / "f4.mp4"),
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
