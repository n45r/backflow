import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

ROOT = Path(__file__).resolve().parent.parent
PORT = int(os.environ.get("BACKFLOW_PORT", "8770"))
WEB = ROOT / "web"
RUNS = ROOT / "runs"
CLIPS = ROOT / "data" / "clips"
CAMS = ("cam1", "cam5")

app = FastAPI()
(ROOT / "runs").mkdir(exist_ok=True)


def _safe_name(name):
    if not name or "/" in name or "\\" in name or name.startswith("."):
        raise HTTPException(400, "bad name")
    return name


def _url(path):
    """Map a file path written by the backend to the URL the browser loads it from."""
    if not path:
        return None
    p = Path(str(path))
    if not p.is_absolute():
        p = (ROOT / p).resolve()
    for base, prefix in ((WEB, "/"), (RUNS, "/runs/"), (CLIPS, "/clips/")):
        try:
            return prefix + p.resolve().relative_to(base.resolve()).as_posix()
        except ValueError:
            pass
    return None


def _read_json(path):
    try:
        return json.loads(Path(path).read_text())
    except (OSError, ValueError):
        return None


def _clips(event, loop_dir):
    """Real clips in data/clips win; a run may carry its own fixture_clips/ for development."""
    out = {}
    for cam in CAMS:
        name = f"{event}_{cam}.mp4"
        if (CLIPS / name).exists():
            out[cam] = f"/clips/{name}"
        elif (loop_dir / "fixture_clips" / name).exists():
            out[cam] = _url(loop_dir / "fixture_clips" / name)
        else:
            out[cam] = None
    return out


@app.get("/api/loop/{name}")
def loop_summary(name: str):
    loop_dir = RUNS / "loop" / _safe_name(name)
    if not loop_dir.is_dir():
        raise HTTPException(404, f"no loop run named {name}")
    frozen = _read_json(loop_dir / "frozen.json")
    site = (frozen or {}).get("site") or _read_json(ROOT / "site" / "site.json") or {}
    rounds = []
    for rj in sorted(loop_dir.glob("round_*/round.json")):
        rec = _read_json(rj)
        if not rec:
            continue
        crit = rec.get("critique") or {}
        patch = rec.get("scene_patch") or {}
        rounds.append({
            "round": rec.get("round"),
            "kind": rec.get("kind") or "critique",
            "event": rec.get("event"),
            "patch": rec.get("patch") or {},
            "winner": rec.get("winner"),
            "candidates": rec.get("candidates") or {},
            "scene_changed": bool(rec.get("scene_changed")),
            "direction": crit.get("direction"),
            "remaining_error": crit.get("remaining_error") or "",
            "scene_url": _url(rec.get("scene")),
            "depths_url": _url(rec.get("depths")),
            "contact_url": _url(rec.get("contact")),
            "judge_video_url": _url(rj.parent / "judge.mp4") if (rj.parent / "judge.mp4").exists() else None,
            "params": rec.get("params") or {},
            "applied_knobs": rec.get("applied_knobs") or {},
            "rows": crit.get("rows") or [],
            "evidence": crit.get("evidence") or crit.get("raw") or "",
            "scene_issues": crit.get("scene_issues") or [],
            "flood_issues": crit.get("flood_issues") or [],
            "scene_patch": patch.get("instruction") or crit.get("scene_patch") or "",
            "next_scene_url": _url(patch.get("new_scene")),
            "confidence": crit.get("confidence"),
            "closer_than_before": crit.get("closer_than_before"),
            "seconds": rec.get("seconds") or {},
            "live": bool(rec.get("live")),
            "mtime": rj.stat().st_mtime,
            "clips": _clips(rec.get("event"), loop_dir),
        })
    holdout = _read_json(loop_dir / "holdout.json")
    if holdout:
        ev = holdout.get("event")
        holdout = {
            "event": ev,
            "blind_scene_url": _url(holdout.get("blind_scene")),
            "blind_depths_url": _url(holdout.get("blind_depths")),
            "informed_scene_url": _url(holdout.get("informed_scene")),
            "informed_depths_url": _url(holdout.get("informed_depths")),
            "blind_patch": holdout.get("blind_patch"),
            "informed_patch": holdout.get("informed_patch"),
            "clips": _clips(ev, loop_dir),
        }
    return {
        "name": name,
        "fixture": name.startswith("demo_fixture") or bool((frozen or {}).get("fixture")),
        "site": site,
        "frozen": {"sha": frozen.get("sha"), "params": frozen.get("params"), "scene_url": _url(frozen.get("scene")), "patch": frozen.get("patch") or {}} if frozen else None,
        "rounds": rounds,
        "holdout": holdout,
    }


@app.get("/api/reveal/{name}")
def reveal(name: str):
    data = _read_json(RUNS / "reveal" / f"{_safe_name(name)}.json")
    if data is None:
        raise HTTPException(404, f"no reveal saved for {name}")
    return data


LOOP = RUNS / "loop"
LOG_DIR = RUNS / "live_logs"
LIVE = {"proc": None, "name": None, "started": None, "finished": None, "log": None}


def _live_dir(name):
    return LOOP / f"{_safe_name(name)}_live"


def _running():
    p = LIVE["proc"]
    if p is None:
        return False
    if p.poll() is None:
        return True
    if LIVE["finished"] is None:
        LIVE["finished"] = time.time()
    return False


def _log_tail(n=12):
    try:
        lines = [l for l in Path(LIVE["log"]).read_text(errors="replace").splitlines() if l.strip()]
    except (OSError, TypeError):
        return []
    return lines[-n:]


@app.get("/api/default_run")
def default_run():
    """The run the demo opens on: the full calibration if it finished, else the video one."""
    for name in ("calib_full", "calib_video"):
        if (LOOP / name / "frozen.json").exists():
            return {"name": name, "live_ready": True, "replay": os.environ.get("ARGON_CACHE", "").strip().lower() == "replay"}
    return {"name": "calib_video", "live_ready": False, "replay": False}


@app.post("/api/live/{name}")
def start_live(name: str):
    """Start one live judged round on top of a finished run. One at a time; returns at once."""
    _safe_name(name)
    if not (LOOP / name / "frozen.json").exists():
        raise HTTPException(404, f"run {name} has no frozen model to build on")
    if _running():
        if LIVE["name"] == name:
            return {"started": False, "running": True, "started_at": LIVE["started"], "note": "a round is already running"}
        raise HTTPException(409, f"a round for {LIVE['name']} is already running")
    live = _live_dir(name)
    if live.exists():
        shutil.rmtree(live)
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log = LOG_DIR / f"{name}.log"
    with open(log, "wb") as fh:
        proc = subprocess.Popen([sys.executable, "-m", "backend.loop", "--live", name], cwd=ROOT,
                                stdout=fh, stderr=subprocess.STDOUT, env=os.environ.copy())
    LIVE.update(proc=proc, name=name, started=time.time(), finished=None, log=str(log))
    return {"started": True, "running": True, "started_at": LIVE["started"]}


def _proc_running(slot):
    p = slot["proc"]
    if p is None:
        return False
    if p.poll() is None:
        return True
    if slot["finished"] is None:
        slot["finished"] = time.time()
    return False


def _launch(slot, name, cmd, log_name):
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log = LOG_DIR / log_name
    with open(log, "wb") as fh:
        proc = subprocess.Popen(cmd, cwd=ROOT, stdout=fh, stderr=subprocess.STDOUT, env=os.environ.copy())
    slot.update(proc=proc, name=name, started=time.time(), finished=None, log=str(log))


CAL = {"proc": None, "name": None, "started": None, "finished": None, "log": None}
TEST = {"proc": None, "name": None, "started": None, "finished": None, "log": None}


@app.post("/api/calibrate/{name}")
def start_calibrate(name: str):
    """Start a short live calibration from the untuned model, on top of a finished run's scene. Writes runs/loop/<name>_cal."""
    _safe_name(name)
    if not (LOOP / name / "frozen.json").exists():
        raise HTTPException(404, f"run {name} has no frozen scene to start from")
    if _proc_running(CAL) or _running() or _proc_running(TEST):
        if CAL["name"] == name and _proc_running(CAL):
            return {"started": False, "running": True, "started_at": CAL["started"], "note": "a calibration is already running"}
        raise HTTPException(409, "another round is already running")
    cal = LOOP / f"{name}_cal"
    if cal.exists():
        shutil.rmtree(cal)
    TEST.update(proc=None, finished=None)
    cmd = [sys.executable, "-m", "backend.loop", "--live-calibrate", name, "--rounds", "4"]
    _launch(CAL, name, cmd, f"{name}_cal.log")
    return {"started": True, "running": True, "started_at": CAL["started"]}


@app.post("/api/test/{name}")
def start_test(name: str):
    """The test uses the model frozen by the full run, whose blind and informed predictions for the held-out flood are already computed."""
    _safe_name(name)
    if not (LOOP / name / "holdout.json").exists():
        raise HTTPException(404, f"run {name} has no held-out prediction saved")
    return {"started": False, "running": False, "done": True, "run": name}


@app.get("/api/progress/{name}")
def progress_of(name: str):
    _safe_name(name)
    if name.endswith("_cal"):
        base = name[:-4]
        mine = CAL["name"] == base
        running = mine and _proc_running(CAL)
        prog = _merged_progress(base) if mine else None
        out = {"name": name, "running": running, "started_here": mine, "started": CAL["started"] if mine else None, "progress": prog,
               "replay": os.environ.get("ARGON_CACHE", "").strip().lower() == "replay"}
        if mine:
            end = time.time() if running else (CAL["finished"] or time.time())
            out["elapsed"] = round(end - CAL["started"], 1)
            out["exit_code"] = None if running else CAL["proc"].returncode
            if not running:
                out["log_tail"] = _tail_of(CAL)
        return out
    mine = LIVE["name"] == name
    running = mine and _running()
    prog = _read_json(_live_dir(name) / "progress.json") if mine else None
    if prog is None and not mine:
        prog = _read_json(_live_dir(name) / "progress.json") or _read_json(LOOP / name / "progress.json")
    out = {"name": name, "running": running, "started_here": mine, "started": LIVE["started"] if mine else None, "progress": prog,
           "replay": os.environ.get("ARGON_CACHE", "").strip().lower() == "replay"}
    if mine:
        end = time.time() if running else (LIVE["finished"] or time.time())
        out["elapsed"] = round(end - LIVE["started"], 1)
        out["exit_code"] = None if running else LIVE["proc"].returncode
        if not running:
            out["log_tail"] = _log_tail()
    return out


AGENTS_RECORD = LOOP / "calib_workers" / "round_01" / "round.json"


def agents_entry():
    """The Managed Agents stage always shows this recorded run: one card per theory, no judged round."""
    rec = _read_json(AGENTS_RECORD) or {}
    workers = (rec.get("workers") or {}).get("per_hypothesis")
    if not workers:
        return None
    return {"t": 0, "stage": "agents", "text": "Three Managed Agents test three theories of how water enters the basement.",
            "round": 1, "ma": True, "workers": workers, "at": 0.0}


def _merged_progress(base_name):
    """The Managed Agents cards first (round 1), then the calibration rounds shifted up by one."""
    cal = _read_json(LOOP / f"{base_name}_cal" / "progress.json") or {"log": []}
    ag = agents_entry()
    log = [ag] if ag else []
    shift = 1 if ag else 0
    for e in cal.get("log") or []:
        if e.get("round") == 0:
            continue
        e = dict(e)
        if e.get("round"):
            e["round"] = e["round"] + shift
        log.append(e)
    return {"current": log[-1] if log else None, "log": log}


def _tail_of(slot, n=12):
    try:
        lines = [l for l in Path(slot["log"]).read_text(errors="replace").splitlines() if l.strip()]
    except (OSError, TypeError):
        return []
    return lines[-n:]


@app.get("/api/frames/{name}/{rnd}")
def frames(name: str, rnd: int, since: int = 0):
    """Frames the renderer has written so far for one live round: A, B, C renders and the stitched grid. `since` skips that many from each list."""
    _safe_name(name)
    base = LOOP / name if (name.endswith("_cal") or name == "ma_demo") else _live_dir(name)
    rd = base / f"round_{int(rnd):02d}"
    out = {"round": rnd, "render": {}, "grid": [], "video": None, "total": 0}
    pat = re.compile(r"_t(\d+)\.png$")
    for L in ("A", "B", "C"):
        items = []
        for f in sorted((rd / f"render_{L}").glob("*.png")):
            m = pat.search(f.name)
            if m and f.stat().st_size > 0:
                items.append({"t": int(m.group(1)), "url": _url(f)})
        out["render"][L] = items[since:]
        out["total"] += len(items)
    grid = [{"url": _url(f)} for f in sorted((rd / "grid").glob("g_*.png")) if f.stat().st_size > 0]
    out["grid"] = grid[since:] if since else grid[:1]
    out["grid_count"] = len(grid)
    if (rd / "judge.mp4").exists():
        out["video"] = str((rd / "judge.mp4").resolve())
    return out


@app.get("/api/video")
def video(path: str):
    """Serve the time-lapse Argon watched. Only mp4 files inside runs/loop, never anything else."""
    p = Path(path)
    p = (p if p.is_absolute() else ROOT / p).resolve()
    try:
        p.relative_to(LOOP.resolve())
    except ValueError:
        raise HTTPException(403, "not a run video")
    if p.suffix != ".mp4" or not p.is_file():
        raise HTTPException(404, "no such video")
    return FileResponse(p, media_type="video/mp4", headers={"Cache-Control": "no-store"})


CLIPS.mkdir(parents=True, exist_ok=True)
app.mount("/clips", StaticFiles(directory=CLIPS), name="clips")
app.mount("/runs", StaticFiles(directory=ROOT / "runs"), name="runs")
app.mount("/", StaticFiles(directory=ROOT / "web", html=True), name="web")


def main():
    uvicorn.run(app, host="127.0.0.1", port=PORT, log_level="warning")


# Gauge data must not be reachable by anything the browser loads before the reveal.
@app.middleware("http")
async def block_reveal_files(request, call_next):
    path = request.url.path
    if path.startswith("/runs/reveal") or path.startswith("/evaluation"):
        from fastapi.responses import PlainTextResponse
        return PlainTextResponse("evaluator only", status_code=403)
    return await call_next(request)


if __name__ == "__main__":
    main()
