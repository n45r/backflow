"""Read the on-screen clock overlay of a camera frame (top-right) with tesseract."""
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

FFMPEG = "/opt/homebrew/bin/ffmpeg"


def read_clock(video, t, work="/private/tmp/ocr_clock"):
    Path(work).mkdir(exist_ok=True, parents=True)
    png = f"{work}/{Path(video).stem}_{t:.1f}.png"
    subprocess.run([FFMPEG, "-y", "-v", "error", "-ss", f"{t:.2f}", "-i", str(video), "-frames:v", "1",
                    "-vf", "crop=iw*0.27:ih*0.06:iw*0.73:0,scale=iw*4:ih*4,format=gray,lut=y='if(gt(val,200),0,255)'", png],
                   stderr=subprocess.DEVNULL)
    if not Path(png).exists():
        return None
    out = subprocess.run(["tesseract", png, "-", "--psm", "7", "-c", "tessedit_char_whitelist=0123456789-: "],
                         capture_output=True, text=True).stdout
    m = re.search(r"(\d{4})-(\d\d)-(\d\d)\s+(\d\d):(\d\d):(\d\d)", out)
    if not m:
        return None
    try:
        return datetime(*map(int, m.groups()))
    except ValueError:
        return None


if __name__ == "__main__":
    v = sys.argv[1]
    dur = float(sys.argv[2])
    for i in range(int(sys.argv[3])):
        t = dur * i / (int(sys.argv[3]) - 1) if int(sys.argv[3]) > 1 else 0
        t = min(t, dur - 1)
        print(f"{t:8.1f}", read_clock(v, t))
