"""Draft of the 1-minute submission video from real run material, with a synthetic voice-over to re-record."""
import json
import subprocess
from pathlib import Path

from PIL import Image, ImageDraw

from backend.contact import _font

ROOT = Path(__file__).resolve().parent.parent
FF = "/opt/homebrew/bin/ffmpeg"
OUT = ROOT / "runs" / "submission"
W, H = 1920, 1080
RUN = "calib_video"


def ff(*args):
    subprocess.run([FF, "-y", "-v", "error", *args], check=True)


def card(img_path, out, title=None, fit=True):
    canvas = Image.new("RGB", (W, H), (12, 12, 16))
    if img_path:
        im = Image.open(img_path).convert("RGB")
        top = 120 if title else 0
        scale = min(W / im.width, (H - top) / im.height) if fit else 1
        im = im.resize((int(im.width * scale), int(im.height * scale)))
        canvas.paste(im, ((W - im.width) // 2, top + (H - top - im.height) // 2))
    if title:
        d = ImageDraw.Draw(canvas)
        d.text((60, 36), title, fill="white", font=_font(52))
    canvas.save(out)
    return out


def still(img, secs, out):
    ff("-loop", "1", "-t", str(secs), "-i", str(img), "-vf", f"scale={W}:{H},format=yuv420p", "-r", "30", "-c:v", "libx264", str(out))
    return out


def clip(src, start, dur_src, secs, out, title=None):
    speed = dur_src / secs
    vf = f"setpts=PTS/{speed},scale={W}:{H}:force_original_aspect_ratio=decrease,pad={W}:{H}:(ow-iw)/2:(oh-ih)/2,format=yuv420p"
    ff("-ss", str(start), "-t", str(dur_src), "-i", str(src), "-an", "-vf", vf, "-r", "30", "-t", str(secs), "-c:v", "libx264", str(out))
    return out


def voice(text, secs, out):
    aiff = out.with_suffix(".aiff")
    subprocess.run(["say", "-v", "Samantha", "-r", "175", "-o", str(aiff), text], check=True)
    ff("-i", str(aiff), "-af", f"apad,atrim=0:{secs}", "-ar", "44100", "-ac", "2", str(out))
    return out


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    loop = ROOT / "runs" / "loop" / RUN
    clip32 = ROOT / "data" / "clips" / "32_cam5.mp4"
    judge = sorted(loop.glob("round_*/judge.mp4"))[1]
    struct = loop / "round_00"
    first, last = struct / "contact_0.png", sorted(struct.glob("contact_*.png"))[-1]
    s3 = Image.open(first); s4 = Image.open(last)
    both = Image.new("RGB", (max(s3.width, s4.width), s3.height + s4.height + 20), (12, 12, 16))
    both.paste(s3, (0, 0)); both.paste(s4, (0, s3.height + 20)); both.save(OUT / "scene_fix.png")
    reveal = ROOT / "runs" / "ui_smoke" / "video_reveal.png"
    cmp = ROOT / "runs" / "ui_smoke" / "video_reveal2.png"
    shots = [
        (6, lambda o: clip(clip32, 230, 120, 6, o), "This basement is flooding from below. The water is coming up the drain."),
        (6, lambda o: still(card(None, OUT / "t2.png", "Backflow:  flood video in, a corrected flood model out"), 6, o),
         "Flood models are often never checked against real floods. Sensors are expensive. Video is not."),
        (7, lambda o: still(card(OUT / "scene_fix.png", OUT / "t3.png", "Argon wrote the 3D site, then fixed its own scene"), 7, o),
         "Argon wrote this 3D scene from the site plan. It saw the drain was missing, and rewrote its own code."),
        (7, lambda o: still(card(sorted(loop.glob("round_01/grid/g_*.png"))[45], OUT / "t4.png", "Water comes only from the drainage simulation"), 7, o),
         "The water comes only from a drainage simulation. Untuned, it floods the basement far too deep."),
        (10, lambda o: clip(judge, 0, 100, 10, o), "Each round, Argon watches three simulated floods beside the real one, and picks the best match. Video only. No sensors."),
        (12, lambda o: still(card(reveal, OUT / "t6.png"), 12, o),
         "Then we lock the model and test it on a flood it never saw. The error drops from 34 millimetres to 6. The researchers' own sensor-based calibrations reach about 5."),
        (7, lambda o: still(card(cmp, OUT / "t7.png", "Same hidden flood"), 7, o),
         "A plain optimiser has a low average error, but it predicts a dry basement. The real one flooded."),
        (5, lambda o: still(card(None, OUT / "t8.png", "github.com/n45r/backflow"), 5, o),
         "Using only video, a flood model corrected about as well as with sensors."),
    ]
    vids, auds = [], []
    for i, (secs, make, text) in enumerate(shots):
        vids.append(make(OUT / f"s{i}.mp4"))
        auds.append(voice(text, secs, OUT / f"a{i}.wav"))
    (OUT / "v.txt").write_text("".join(f"file '{v}'\n" for v in vids))
    (OUT / "a.txt").write_text("".join(f"file '{a}'\n" for a in auds))
    ff("-f", "concat", "-safe", "0", "-i", str(OUT / "v.txt"), "-c", "copy", str(OUT / "video_only.mp4"))
    ff("-f", "concat", "-safe", "0", "-i", str(OUT / "a.txt"), "-c", "pcm_s16le", str(OUT / "voice.wav"))
    ff("-i", str(OUT / "video_only.mp4"), "-i", str(OUT / "voice.wav"), "-c:v", "copy", "-c:a", "aac", "-shortest",
       str(OUT / "backflow_draft.mp4"))
    print(OUT / "backflow_draft.mp4")


if __name__ == "__main__":
    main()
