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
CUES = {"cameras": 0.0, "problem": 7.0, "plan": 17.8, "orbit": 20.0, "fix": 22.5, "agents": 25.5,
        "loop": 32.4, "test": 50.3, "end": 60.9}
END = 68.0


def main(voice):
    run_dir = ROOT / "runs" / "loop" / "calib_video"
    cam = ROOT / "data" / "raw" / "video"
    dur = lambda a, b: round(CUES[b] - CUES[a], 2)
    for d in (OUT / "seq", OUT / "reveal" / "seq"):
        shutil.rmtree(d, ignore_errors=True)
    make_round_sequence.main(out_name="round_voiced.mp4", durs=(3.4, 5.3, 0.7, 3.7, 4.8))
    make_reveal_sequence.main(out_name="reveal_voiced.mp4", durs=(3.7, 1.8, 5.1))
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
        agents_segment(OUT / "v5.mp4", dur("agents", "loop")),
        OUT / "round_voiced.mp4",
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
