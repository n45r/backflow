"""Record the demo app headless at 1920x1080 for the submission video: live round in replay mode, then the reveal.

Usage: python scripts/record_app.py RUN_NAME   (expects ./demo --replay style server on BACKFLOW_PORT, default 8771)
Writes runs/submission/app_take.webm and a timing log of each step.
"""
import json
import os
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "runs" / "submission"


def main(run):
    port = os.environ.get("BACKFLOW_PORT", "8771")
    url = f"http://127.0.0.1:{port}/demo.html?run={run}"
    OUT.mkdir(parents=True, exist_ok=True)
    marks = []
    t0 = time.time()

    def mark(label):
        marks.append({"t": round(time.time() - t0, 1), "step": label})
        print(marks[-1], flush=True)

    with sync_playwright() as p:
        b = p.chromium.launch(headless=True, args=["--use-angle=metal"])
        ctx = b.new_context(viewport={"width": 1920, "height": 1080}, record_video_dir=str(OUT / "raw"),
                            record_video_size={"width": 1920, "height": 1080})
        page = ctx.new_page()
        page.goto(url, wait_until="load", timeout=60000)
        page.wait_for_timeout(4000)
        mark("idle")
        page.get_by_text("Run a live round with Argon").first.click()
        mark("run clicked")
        page.get_by_role("button", name="Show the reveal").wait_for(state="visible", timeout=240000)
        mark("verdict")
        page.wait_for_timeout(9000)
        page.get_by_text("Show the reveal").first.click()
        mark("reveal view")
        page.wait_for_timeout(4000)
        btn = page.get_by_text("Reveal sensors")
        if btn.count():
            btn.first.click()
            mark("sensors revealed")
        page.wait_for_timeout(9000)
        video_path = page.video.path()
        ctx.close()
        b.close()
    final = OUT / "app_take.webm"
    Path(video_path).replace(final)
    (OUT / "app_take_marks.json").write_text(json.dumps(marks, indent=1))
    print(final)


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "calib_video")
