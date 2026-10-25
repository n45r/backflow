"""Real camera clips and frames on the dataset reference clock (t=0 is the event start)."""
import json
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import fetch_clips as fc  # noqa: E402
import ocr_clock as oc  # noqa: E402

FFMPEG = "/opt/homebrew/bin/ffmpeg"
CLIPS = ROOT / "data/clips"


def _run(args):
    # the cameras' H.264 streams contain a few undecodable access units; ffmpeg then exits non-zero after writing
    # the output, so success is judged by the output file
    out = Path(args[-1])
    out.unlink(missing_ok=True)
    subprocess.run([FFMPEG, "-y", "-v", "error", "-max_error_rate", "1.0", *args], stderr=subprocess.DEVNULL)
    if not out.exists() or out.stat().st_size == 0:
        raise RuntimeError("ffmpeg produced no output: " + " ".join(args))


def _duration(path):
    r = subprocess.run(["/opt/homebrew/bin/ffprobe", "-v", "error", "-select_streams", "v", "-show_entries",
                        "stream=duration", "-of", "csv=p=0", str(path)], capture_output=True, text=True).stdout.split()
    return float(r[0])


def _sod(c):
    return c.hour * 3600 + c.minute * 60 + c.second


def _longest_nondecreasing(pts):
    """Indices of the longest subsequence of (t, v) whose v never decreases (drops OCR misreads)."""
    import bisect
    tails, idx, prev = [], [], [None] * len(pts)
    for i, (_, v) in enumerate(pts):
        k = bisect.bisect_right(tails, v)
        if k == len(tails):
            tails.append(v)
            idx.append(i)
        else:
            tails[k] = v
            idx[k] = i
        prev[i] = idx[k - 1] if k else None
    out, i = [], idx[-1]
    while i is not None:
        out.append(i)
        i = prev[i]
    return [pts[j] for j in reversed(out)]


def _despike(pts, win=9, tol=2):
    """Drop OCR misreads: points whose clock-minus-container offset jumps away from the local median offset."""
    out = []
    for i, (t, v) in enumerate(pts):
        w = sorted(vv - tt for tt, vv in pts[max(0, i - win // 2): i + win // 2 + 1])
        if abs((v - t) - w[len(w) // 2]) <= tol:
            out.append((t, v))
    return out


def chunk_map(path, n=9, step=3.0):
    """Map container time to the camera clock for one AVI chunk, read from the on-screen overlay.

    Returns {"linear": bool, "points": [[container_s, clock_s_of_day], ...], "dur": s}. Most chunks run at real
    time with a start a few seconds off the file name. A few (camera 1 at night) have a variable frame rate, so
    their container time is not the clock; those get a dense map.
    """
    cache = Path(str(path) + ".map.json")
    if cache.exists():
        return json.loads(cache.read_text())
    dur = _duration(path)
    n0 = _sod(fc.chunk_span(Path(path).name, "161006")[0])

    def read(t):
        # tesseract sometimes misreads a digit of the minutes; the file name bounds the clock to a few minutes
        c = oc.read_clock(path, t)
        return _sod(c) if c is not None and abs(_sod(c) - (n0 + t)) <= 200 else None

    pts = []
    for i in range(n):
        t = 15 + (dur - 30) * i / (n - 1)
        v = read(t)
        if v is not None:
            pts.append((t, v))
    offs = sorted(v - t for t, v in pts)
    med = offs[len(offs) // 2] if offs else 0
    inl = [o for o in offs if abs(o - med) <= 3]
    if offs and len(inl) / n >= 0.6:
        st = sum(inl) / len(inl)
        res = {"linear": True, "points": [[0, st], [dur, st + dur]], "dur": dur}
    else:
        from concurrent.futures import ThreadPoolExecutor
        ts = [i * step for i in range(int(dur / step))]
        with ThreadPoolExecutor(8) as ex:
            cs = list(ex.map(read, ts))
        dense = [(t, v) for t, v in zip(ts, cs) if v is not None]
        keep = _longest_nondecreasing(_despike(dense)) if dense else []
        offs = sorted(v - t for t, v in keep)
        med = offs[len(offs) // 2] if offs else 0
        near = [o for o in offs if abs(o - med) <= 3]
        if len(keep) >= 8 and len(near) >= 0.8 * len(keep) and keep[-1][0] - keep[0][0] >= 0.3 * dur:
            st = sum(near) / len(near)
            res = {"linear": True, "points": [[0, st], [dur, st + dur]], "dur": dur}
        else:
            res = {"linear": False, "points": [list(x) for x in keep], "dur": dur}
    cache.write_text(json.dumps(res))
    return res


def _repair_maps(files, maps):
    """Chunks whose overlay could barely be read (bright scenes) take their start from the few readings that
    agree, or else follow on from the previous chunk (the recorder writes back-to-back files)."""
    out = []
    for k, m in enumerate(maps):
        pts = m["points"]
        if m["linear"] or (len(pts) >= 8 and pts[-1][0] - pts[0][0] >= 0.5 * m["dur"]):
            out.append(m)
            continue
        offs = sorted(v - t for t, v in pts)
        agree = [o for o in offs if offs and abs(o - offs[len(offs) // 2]) <= 3]
        if len(agree) >= 3:
            st = sum(agree) / len(agree)
        elif out and out[-1]["points"] and out[-1]["linear"]:
            st = out[-1]["points"][0][1] + out[-1]["dur"]
        else:
            out.append({**m, "points": []})  # cannot be placed reliably: skipped
            continue
        print(f"note: {files[k].name}: overlay barely readable, start estimated")
        out.append({"linear": True, "points": [[0, st], [m["dur"], st + m["dur"]]], "dur": m["dur"]})
    return out


def _to_container(points, clock):
    """Container time at which the camera clock reads `clock` (first match, linear between map points)."""
    for (t0, c0), (t1, c1) in zip(points, points[1:]):
        if c0 <= clock <= c1:
            return t0 if c1 == c0 else t0 + (t1 - t0) * (clock - c0) / (c1 - c0)
    return None


def clip_path(event, cam):
    return CLIPS / f"{event}_{cam}.mp4"


FPS = 2
ENC = ["-c:v", "libx264", "-preset", "veryfast", "-crf", "26", "-pix_fmt", "yuv420p"]


def _linear_segment(src, a, begin, end, seg):
    """Real-time chunk: cut [begin, end] (seconds of day) at FPS."""
    _run(["-i", str(src), "-ss", f"{begin - a:.3f}", "-t", f"{end - begin:.3f}", "-an",
          "-vf", f"scale=-2:480,fps={FPS},tpad=stop_mode=clone:stop_duration=20", *ENC, str(seg)])


def _mapped_segment(src, points, begin, end, seg):
    """Variable-frame-rate chunk: pick, for every output tick, the frame whose overlay clock matches."""
    from concurrent.futures import ThreadPoolExecutor
    ticks = [begin + i / FPS for i in range(int((end - begin) * FPS))]
    d = Path(str(seg) + ".frames")
    d.mkdir(exist_ok=True)
    last = {}

    def grab(i):
        ct = _to_container(points, ticks[i])
        if ct is None:
            return None
        f = d / f"{i:06d}.jpg"
        for back in (0, 0.3, 0.7, 1.2, 2.0):
            try:
                _run(["-ss", f"{max(ct - back, 0):.3f}", "-i", str(src), "-frames:v", "1", "-vf", "scale=-2:480",
                      "-q:v", "3", str(f)])
                return f
            except RuntimeError:
                continue
        return None

    with ThreadPoolExecutor(8) as ex:
        got = list(ex.map(lambda i: _try(grab, i), range(len(ticks))))
    prev = next((f for f in got if f is not None), None)
    for i, f in enumerate(got):
        if f is None:
            f = prev
        if f is not None:
            link = d / f"s{i:06d}.jpg"
            link.unlink(missing_ok=True)
            link.symlink_to(f)
            prev = f
    _run(["-framerate", str(FPS), "-i", str(d / "s%06d.jpg"), *ENC, str(seg)])


def _try(fn, i):
    try:
        return fn(i)
    except RuntimeError:
        return None


def prepare(event, cam, force=False):
    """One 480p H.264 MP4 at 2 fps per (event, cam); t=0 is the event start on the reference clock.

    Every chunk is placed by its on-screen camera clock (not its file name), overlaps are trimmed, and the
    camera offset is removed: reference time = camera clock minus offset.
    """
    out = clip_path(event, cam)
    if out.exists() and not force:
        return out
    session = fc.EVENTS[event]
    off = fc.OFFSETS[(session, cam)]
    s, e = fc.event_window(event)
    dur = (e - s).total_seconds()
    cam_start = (s.hour * 3600 + s.minute * 60 + s.second) + off
    cam_end = cam_start + dur
    work = CLIPS / f"_work_{event}_{cam}"
    work.mkdir(parents=True, exist_ok=True)
    lines, cursor = [], cam_start
    files = sorted((fc.VIDEO / session / cam).glob("*.avi"))
    maps = [chunk_map(p) for p in files]
    maps = _repair_maps(files, maps)
    for k, (p, m) in enumerate(zip(files, maps)):
        pts = m["points"]
        if len(pts) < 2:
            print(f"warning: {p.name}: overlay clock unreadable, skipped")
            continue
        a, b = pts[0][1], pts[-1][1]
        nxt = next((mm["points"][0][1] for mm in maps[k + 1:] if len(mm["points"]) >= 2), None)
        if nxt is not None and 0 < nxt - b <= 60:
            b = nxt  # gap between chunks (frames unreadable or camera restarting): hold the last frame
        if b <= cursor or a >= cam_end:
            continue
        begin = max(a, cursor)
        end = min(b, cam_end)
        if end - begin < 1:
            continue
        if begin - cursor > 1.5:
            print(f"warning: gap of {begin - cursor:.1f}s before {p.name}")
        seg = work / (p.stem + ".mp4")
        if m["linear"] or len(pts) == 2:
            _linear_segment(p, a, begin, end, seg)
        else:
            print(f"note: {p.name} has a variable frame rate; frames matched to the overlay clock")
            _mapped_segment(p, pts, begin, end, seg)
        lines.append(f"file '{seg}'\n")
        cursor = end
    (work / "list.txt").write_text("".join(lines))
    _run(["-f", "concat", "-safe", "0", "-i", str(work / "list.txt"), "-t", str(dur), "-c", "copy", str(out)])
    return out


def real_frames(event, cam, times_s, out_dir):
    """JPG frames at reference times (seconds from event start)."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    src = prepare(event, cam)
    last = _duration(src) - 1.0 / FPS
    paths = []
    for t in times_s:
        t = min(max(t, 0.0), last)
        p = out_dir / f"{event}_{cam}_t{int(round(t)):05d}.jpg"
        _run(["-ss", f"{t:.3f}", "-i", str(src), "-frames:v", "1", "-q:v", "2", str(p)])
        paths.append(str(p))
    return paths


def clip(event, cam, start_s, end_s, fps, out_path):
    """Short low-fps clip between two reference times."""
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    src = prepare(event, cam)
    _run(["-ss", f"{start_s:.3f}", "-i", str(src), "-t", f"{end_s - start_s:.3f}", "-an", "-vf", f"fps={fps}", *ENC, str(out_path)])
    return str(out_path)


def duration_s(event):
    s, e = fc.event_window(event)
    return (e - s).total_seconds()


if __name__ == "__main__":
    prev = ROOT / "data/frames/preview"
    for ev in [int(a) for a in sys.argv[1:]] or [20, 21, 32]:
        for cam in ("cam1", "cam5"):
            d = duration_s(ev)
            print(real_frames(ev, cam, [0, d / 2, d - 2], prev))
