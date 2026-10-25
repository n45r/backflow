"""Record the demo app headless at 1920x1080 in two takes, for the submission video.

take A: Calibrate live, the Managed Agents cards and the first round, step by step
take B: Test on a flood it has never seen, then Reveal sensors
Usage: BACKFLOW_PORT=8772 python scripts/record_app2.py   (server started with ./demo --replay)
Writes runs/submission/app_a.mp4, app_b.mp4 and app_marks.json (seconds into each take).
"""
import json
import os
import subprocess
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "runs" / "submission"
FF = "/opt/homebrew/bin/ffmpeg"


def take(p, url, name, script):
    marks = []
    t0 = time.time()

    def mark(label):
        marks.append({"t": round(time.time() - t0, 1), "step": label})
        print(name, marks[-1], flush=True)

    b = p.chromium.launch(channel="chrome", headless=True, args=["--autoplay-policy=no-user-gesture-required"])
    ctx = b.new_context(viewport={"width": 1920, "height": 1080}, record_video_dir=str(OUT / "raw"),
                        record_video_size={"width": 1920, "height": 1080})
    page = ctx.new_page()
    page.goto(url, wait_until="load", timeout=60000)
    page.wait_for_timeout(2500)
    t0 = time.time()
    script(page, mark)
    path = page.video.path()
    ctx.close()
    b.close()
    dst = OUT / f"app_{name}.mp4"
    subprocess.run([FF, "-y", "-v", "error", "-i", str(path), "-c:v", "libx264", "-pix_fmt", "yuv420p", "-r", "30", str(dst)],
                   check=True)
    return marks


def script_a(page, mark):
    mark("idle")
    page.wait_for_timeout(1500)
    page.click("#runBtn")
    mark("calibrate clicked")
    page.wait_for_timeout(60000)
    mark("end")


def script_b(page, mark):
    page.click("#recLink")
    page.wait_for_timeout(1500)
    page.click("#testRecBtn")
    mark("test clicked")
    page.wait_for_timeout(16000)
    page.click("#revealBtn")
    mark("sensors revealed")
    page.wait_for_timeout(9000)
    mark("end")


def main():
    port = os.environ.get("BACKFLOW_PORT", "8772")
    url = f"http://127.0.0.1:{port}/demo.html?run=calib_video"
    OUT.mkdir(parents=True, exist_ok=True)
    marks = {}
    with sync_playwright() as p:
        which = os.environ.get("TAKES", "ab")
        if "a" in which:
            marks["a"] = take(p, url, "a", script_a)
        if "b" in which:
            marks["b"] = take(p, url, "b", script_b)
    (OUT / f"app_marks_{os.environ.get('TAKES', 'ab')}.json").write_text(json.dumps(marks, indent=1))
    print("done")


if __name__ == "__main__":
    main()
