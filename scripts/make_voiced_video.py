"""Final video timed to the recorded voice-over: each section starts where its words start."""
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from scripts import make_reveal_sequence, make_round_sequence  # noqa: E402
from scripts.make_final_video import agents_segment, end_card, mosaic, still, titled  # noqa: E402
from scripts.make_submission_video import OUT, card, clip, ff, triptych  # noqa: E402

# Section start times in the voice track (seconds), read from its transcript.
CUES = {"cameras": 0.0, "problem": 8.14, "plan": 20.68, "orbit": 23.1, "fix": 24.86, "agents": 29.37,
        "loop": 37.51, "test": 58.41, "end": 70.29}
END = 78.3
ROUND_DURS = (4.07, 6.16, 0.7, 4.25, 5.72)
REVEAL_DURS = (1.0, 1.8, 3.08)  # the app take covers the first 6 s of the test section


def app_clip(src, start, dur_src, secs, out):
    """A stretch of the real app recording, sped up or slowed to fit its place in the voice-over."""
    return clip(src, start, dur_src, secs, out)


def main(voice):
    run_dir = ROOT / "runs" / "loop" / "calib_video"
    cam = ROOT / "data" / "raw" / "video"
    dur = lambda a, b: round(CUES[b] - CUES[a], 2)
    for d in (OUT / "seq", OUT / "reveal" / "seq"):
        shutil.rmtree(d, ignore_errors=True)
    make_reveal_sequence.main(out_name="reveal_voiced.mp4", durs=REVEAL_DURS)
    half = dur("problem", "plan") / 2
    segs = [
        mosaic(OUT / "v0.mp4", dur("cameras", "problem"), views=[
            [(ROOT / "data/clips/20_cam1.mp4", 180, "Pond"),
             (cam / "161006A/cam3/c3_cam3_instar_161006_143254_144255.avi", 330, "Channel"),
             (ROOT / "data/clips/20_cam5.mp4", 200, "Building")],
            [(ROOT / "data/clips/32_cam1.mp4", 240, "Pond"),
             (cam / "161006B/cam3/c3_cam3_instar_161006_211833_212838.avi", 120, "Channel"),
             (ROOT / "data/clips/32_cam5.mp4", 250, "Building")]]),
        titled(clip(ROOT / "data/clips/20_cam1.mp4", 200, half * 4, half, OUT / "v1a_raw.mp4"),
               "Flood simulations have settings nobody can measure", OUT / "v1a.mp4"),
        titled(clip(ROOT / "data/clips/32_cam5.mp4", 250, half * 8, half, OUT / "v1b_raw.mp4"),
               "Sensors to check them are rare. Video is everywhere.", OUT / "v1b.mp4"),
        still(card(OUT / "plan.png", OUT / "v2.png", "Gemini 4 Argon reads the site's engineering drawing"), dur("plan", "orbit"),
              OUT / "v2.mp4"),
        titled(clip(OUT / "orbit.mp4", 0, 6, dur("orbit", "fix"), OUT / "v3_raw.mp4"), "...and builds the whole site in 3D",
               OUT / "v3.mp4"),
        still(card(triptych([run_dir / "round_00/real/32_cam5_t00000.jpg", run_dir / "round_00/render_0/cam5_t00000.png",
                             sorted((run_dir / "round_00").glob("render_*/cam5_t00000.png"))[-1]],
                            ["Real camera", "Argon's first scene", "After Argon fixed it"], OUT / "fix3.png"),
                   OUT / "v4.png", "Argon noticed its scene was missing the drain, and rewrote its code"), dur("fix", "agents"),
              OUT / "v4.mp4"),
        app_clip(OUT / "app_a.mp4", 3.0, 8.0, dur("agents", "loop"), OUT / "v5.mp4"),
        app_clip(OUT / "app_a.mp4", 11.0, 6.0, 4.0, OUT / "L1.mp4"),
        app_clip(OUT / "app_a.mp4", 17.0, 10.5, 3.5, OUT / "L2.mp4"),
        app_clip(OUT / "app_a.mp4", 27.5, 9.5, 6.3, OUT / "L3.mp4"),
        app_clip(OUT / "app_a.mp4", 37.0, 7.1, 7.1, OUT / "L4.mp4"),
        app_clip(OUT / "app_b.mp4", 6.6, 10.6, 6.0, OUT / "T1.mp4"),
        OUT / "reveal_voiced.mp4",
        still(end_card(OUT / "v8.png"), round(END - CUES["end"], 2), OUT / "v8.mp4"),
    ]
    (OUT / "vv.txt").write_text("".join(f"file '{s}'\n" for s in segs))
    ff("-f", "concat", "-safe", "0", "-i", str(OUT / "vv.txt"), "-c", "copy", str(OUT / "voiced_video_only.mp4"))
    dst = OUT / "backflow_final_voiced.mp4"
    ff("-i", str(OUT / "voiced_video_only.mp4"), "-i", str(voice), "-filter_complex", "[1:a]apad[a]", "-map", "0:v", "-map", "[a]",
       "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-shortest", str(dst))
    print(dst)


if __name__ == "__main__":
    main(Path(sys.argv[1]))
