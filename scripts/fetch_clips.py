"""Index remote TARs with HTTP Range requests and download only the AVI chunks needed.

Usage: python -I scripts/fetch_clips.py [event ...]   (default: 20 21 32)
Chunks land in data/raw/video/<session>/<cam>/ ; the TAR index is cached beside them.
"""
import csv
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VIDEO = ROOT / "data/raw/video"
BASE = "https://zenodo.org/api/records/1039631/files/{}/content"
TARS = {
    ("161006A", "cam1"): ("s3_cam1_instar_161006A.tar", 5209491968),
    ("161006A", "cam5"): ("s6_cam5_instar_161006A.tar", 5047662080),
    ("161006B", "cam1"): ("s3_cam1_instar_161006B.tar", 933307904),
    ("161006B", "cam5"): ("s6_cam5_instar_161006B.tar", 574353920),
}
OFFSETS = {  # seconds; reference = camera time minus offset
    ("161006A", "cam1"): 3, ("161006A", "cam5"): -10,
    ("161006B", "cam1"): 2, ("161006B", "cam5"): -11,
}
EVENTS = {20: "161006A", 21: "161006A", 32: "161006B"}
PAD_S = 120


def event_window(event):
    for r in csv.DictReader(open(ROOT / "docs/gates/gate_a_events.csv")):
        if int(r["id"]) == event:
            d = r["date"]
            f = "%Y-%m-%d %H:%M"
            return datetime.strptime(f"{d} {r['start']}", f), datetime.strptime(f"{d} {r['end']}", f)
    raise KeyError(event)


def rng(url, a, b):
    out = subprocess.run(["curl", "-sL", "-r", f"{a}-{b}", "-w", "\n%{http_code}", url],
                         capture_output=True, check=True).stdout
    body, code = out.rsplit(b"\n", 1)
    if code != b"206" or len(body) != b - a + 1:
        raise RuntimeError(f"range {a}-{b}: http {code!r}, {len(body)} bytes")
    return body


def tar_index(session, cam):
    name, total = TARS[(session, cam)]
    cache = VIDEO / session / cam / "tar_index.tsv"
    if cache.exists():
        return [(int(o), int(s), n) for o, s, n in (l.split("\t") for l in cache.read_text().splitlines())]
    url, off, rows = BASE.format(name), 0, []
    while off + 512 <= total:
        h = rng(url, off, off + 511)
        if h == b"\0" * 512:
            break
        n = h[0:100].rstrip(b"\0").decode()
        size = int(h[124:136].rstrip(b"\0 ").decode() or "0", 8)
        if n.endswith(".avi"):
            rows.append((off + 512, size, n.split("/")[-1]))
        off += 512 + ((size + 511) // 512) * 512
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text("".join(f"{o}\t{s}\t{n}\n" for o, s, n in rows))
    return rows


def chunk_span(name, day):
    p = name.rsplit(".", 1)[0].split("_")
    a = datetime.strptime(day + p[-2], "%y%m%d%H%M%S")
    b = datetime.strptime(day + p[-1], "%y%m%d%H%M%S")
    return a, (b if b > a else b + timedelta(days=1))


def needed(event, cam):
    session = EVENTS[event]
    s, e = event_window(event)
    off = timedelta(seconds=OFFSETS[(session, cam)])
    lo, hi = s - timedelta(seconds=PAD_S) + off, e + timedelta(seconds=PAD_S) + off
    out = []
    for o, size, n in tar_index(session, cam):
        a, b = chunk_span(n, "161006")
        if a < hi and b > lo:
            out.append((o, size, n))
    return session, out


def download(url, off, size, dst, parts=16):
    """Parallel Range requests (the server throttles each connection). Each part must come back as 206 and is
    resumed from the bytes already on disk if the connection drops, so the final file has the exact byte count."""
    from concurrent.futures import ThreadPoolExecutor
    step = -(-size // parts)
    spans = [(off + i * step, min(off + size, off + (i + 1) * step) - 1) for i in range(parts) if off + i * step < off + size]

    def part(i):
        a, b = spans[i]
        pf = Path(f"{dst}.{i:02d}")
        for _ in range(40):
            have = pf.stat().st_size if pf.exists() else 0
            if have == b - a + 1:
                return pf
            r = subprocess.run(["curl", "-sL", "--max-time", "600", "-r", f"{a + have}-{b}", "-w", "%{http_code}", "-o", str(pf) + ".tmp", url],
                               capture_output=True)
            tmp = Path(str(pf) + ".tmp")
            if r.stdout == b"206" and tmp.exists():
                with open(pf, "ab") as f:
                    f.write(tmp.read_bytes())
            tmp.unlink(missing_ok=True)
        raise RuntimeError(f"{dst.name} part {i}: gave up")

    with ThreadPoolExecutor(parts) as ex:
        files = list(ex.map(part, range(len(spans))))
    with open(dst, "wb") as out:
        for pf in files:
            out.write(pf.read_bytes())
            pf.unlink()
    if dst.stat().st_size != size:
        raise RuntimeError(f"{dst.name}: {dst.stat().st_size} of {size}")


def fetch(event, cam):
    session, chunks = needed(event, cam)
    url = BASE.format(TARS[(session, cam)][0])
    d = VIDEO / session / cam
    total = 0
    for o, size, n in chunks:
        dst = d / n
        if dst.exists() and dst.stat().st_size == size:
            continue
        tmp = dst.with_suffix(".part")
        download(url, o, size, tmp)
        tmp.rename(dst)
        total += size
        print(f"event {event} {cam} {n} {size} B (206)", flush=True)
    return total


if __name__ == "__main__":
    args = sys.argv[1:]
    cams = tuple(a for a in args if a.startswith("cam")) or ("cam1", "cam5")
    evs = [int(a) for a in args if a.isdigit()] or [20, 21, 32]
    grand = 0
    for ev in evs:
        for cam in cams:
            grand += fetch(ev, cam)
    print("downloaded bytes:", grand)
