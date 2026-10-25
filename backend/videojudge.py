"""Video judging: Argon watches the real flood and the candidate simulations as one side-by-side video.

Each video frame is a 2x2 grid at one moment of the flood: the real camera, then candidates A, B and C rendered
from the same viewpoint. One video second is one moment; moments are STEP_S apart, so the video is a time-lapse.
"""
import json
import re
import subprocess
import time
from pathlib import Path

from PIL import Image, ImageDraw
from google.genai import types

from backend import argon, frames
from backend.contact import _font

FFMPEG = "/opt/homebrew/bin/ffmpeg"
STEP_S = 6
CELL = (640, 360)

BRIEF = """You are judging flood simulations of the FloodX test site against real camera footage.

The video is a time-lapse of one flood in the basement (night infrared camera). Every frame is a 2x2 grid at the same moment: top left is the REAL camera; the other three panels (A, B, C) are 3D renders of three candidate simulations from the same viewpoint. Water in each render is placed only by the hydraulic simulation; you never see its numbers. The clock in each frame is the time since the event started. One second of video is {step} seconds of the flood.

Watch the whole video, to the end. Compare how each candidate's flood unfolds with the real one, in this order of importance: (1) how long the floor stays covered and when the water drains back into the drain and the floor is left only wet; deeper water takes longer to drain, so a simulation that stays flooded much longer than the real one has too much water; (2) depth cues: how high the water rises on the sandbag, the cables and the striped rod over the drain; (3) when water first rises out of the floor drain and how fast the wet area spreads. A candidate that matches the start but stays flooded too long is worse than one that drains on time. In infrared, wet concrete is darker and reflective. Ignore differences in colour, texture and lighting; judge only the water.

Reply with JSON only:
{{"moments": [{{"time": "m:ss", "best": "A|B|C|tie", "evidence": "..."}}],
 "winner": "A|B|C", "remaining_error": "what the winner still gets wrong, with times",
 "direction": "less_water|more_water|earlier|later|faster_drain|slower_drain|ok",
 "confidence": 0.0-1.0}}
List 4 to 6 moments that decided your choice."""


def _grid(real, cands, t, out):
    font, small = _font(26), _font(20)
    W, H = CELL
    im = Image.new("RGB", (2 * W + 6, 2 * H + 6), (10, 10, 14))
    panels = [("REAL", real)] + list(cands.items())
    for i, (label, path) in enumerate(panels):
        x, y = (i % 2) * (W + 6), (i // 2) * (H + 6)
        im.paste(Image.open(path).convert("RGB").resize(CELL), (x, y))
        d = ImageDraw.Draw(im)
        d.rectangle([x, y, x + 120, y + 40], fill=(0, 0, 0))
        d.text((x + 10, y + 6), label, fill="yellow" if label == "REAL" else "white", font=font)
        d.rectangle([x + W - 110, y + H - 34, x + W, y + H], fill=(0, 0, 0))
        d.text((x + W - 100, y + H - 30), f"{t // 60}:{t % 60:02d}", fill="white", font=small)
    im.save(out)


def real_series(event, cam, start_s, end_s, out_dir):
    """Real frames every STEP_S seconds, extracted in one ffmpeg pass from the event clip."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    clip = frames.prepare(event, cam)
    subprocess.run([FFMPEG, "-y", "-v", "error", "-ss", str(start_s), "-t", str(end_s - start_s + STEP_S / 2), "-i", str(clip),
                    "-vf", f"fps=1/{STEP_S},scale={CELL[0]}:{CELL[1]}", str(out_dir / "r_%04d.jpg")], check=True)
    return sorted(str(p) for p in out_dir.glob("r_*.jpg"))


def build_video(renderer, scene_url, depths, event, cam, start_s, end_s, out_dir):
    out_dir = Path(out_dir)
    times = list(range(start_s, end_s + 1, STEP_S))
    real = real_series(event, cam, start_s, end_s, out_dir / "real")[:len(times)]
    times = times[:len(real)]
    renders = {L: renderer.render(scene_url, d, cam, times, out_dir / f"render_{L}") for L, d in depths.items()}
    gdir = out_dir / "grid"
    gdir.mkdir(exist_ok=True)
    for i, t in enumerate(times):
        _grid(real[i], {L: renders[L][i] for L in renders}, t, gdir / f"g_{i:04d}.png")
    video = out_dir / "judge.mp4"
    subprocess.run([FFMPEG, "-y", "-v", "error", "-framerate", "1", "-i", str(gdir / "g_%04d.png"),
                    "-pix_fmt", "yuv420p", "-c:v", "libx264", "-crf", "23", str(video)], check=True)
    return video, gdir / f"g_{len(times) // 2:04d}.png"


def _upload(path):
    c = argon.client()
    f = c.files.upload(file=str(path))
    while f.state.name == "PROCESSING":
        time.sleep(2)
        f = c.files.get(name=f.name)
    if f.state.name != "ACTIVE":
        raise RuntimeError(f"upload failed: {f.state.name}")
    return f


def _cache_path(key):
    import hashlib
    return Path(__file__).resolve().parent.parent / "runs" / "argon_cache" / f"video_{hashlib.sha256(key.encode()).hexdigest()[:24]}.json"


def judge(video, key=None):
    """key: a description of what the video shows (candidates, scene, window). Used to record and replay answers
    without uploading, so the demo works offline."""
    import os
    mode = os.environ.get("ARGON_CACHE")
    if key and mode == "replay":
        p = _cache_path(key)
        if not p.exists():
            raise RuntimeError(f"no recorded answer for this video ({p.name}); run once with ARGON_CACHE=record")
        rec = json.loads(p.read_text())
        rec["replay"] = True
        return rec
    t0 = time.time()
    f = _upload(video)
    up = time.time() - t0
    reply, usage, secs = argon.ask([types.Part.from_uri(file_uri=f.uri, mime_type=f.mime_type),
                                    types.Part.from_text(text=BRIEF.format(step=STEP_S))],
                                   thinking="medium", max_output_tokens=65536)
    m = re.search(r"\{.*\}", reply, re.S)
    out = {"result": json.loads(m.group(0)) if m else {"raw": reply}, "usage": usage, "seconds": secs, "upload_s": round(up, 1)}
    if key and mode == "record":
        p = _cache_path(key)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(out))
    return out
