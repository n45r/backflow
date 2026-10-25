"""The calibration loop.

Round 0 aligns the scene with the real dry frame (structural fixes, as small patches).
Round 1 lets Argon judge which way water enters the basement (sewer, door, both).
Later rounds are a visual search: three candidate parameter sets are simulated and rendered,
Argon judges which render matches the real frames, and the search narrows around the winner.
Argon never sees simulation numbers or gauges; it only sees renders beside real frames.
"""
import argparse
import copy
import hashlib
import json
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

from backend import argon, contact, data, progress, sim
from backend.config import RUNS, SPLIT
from backend.render import Renderer

ROOT = Path(__file__).resolve().parent.parent
KNOBS_FILE = ROOT / "site" / "knobs.json"
DEFAULT_KNOBS = {"basement_path": ["sewer", "door", "both"], "weir_cd": [1.1, 2.1], "orifice_cd": [0.2, 0.8]}
KNOBS = json.loads(KNOBS_FILE.read_text()) if KNOBS_FILE.exists() else DEFAULT_KNOBS
CAM = "cam5"
LABELS = "ABCDEF"


def key_times(event, n=5):
    """Moments around the basement wetting onset that Argon read from the video; even spacing if no timeline yet.
    Chosen without looking at any gauge."""
    tl = RUNS / "timeline" / f"{event}.json"
    if tl.exists():
        onset = json.loads(tl.read_text()).get("basement_wet_onset_s")
        if onset is not None:
            return [max(0, round(onset + d)) for d in (-120, -60, 0, 60, 180)][:n]
    start, end = data.event_window(event)
    span = (end - start).total_seconds()
    return [round(span * (i + 1) / (n + 1)) for i in range(n)]


def clamp(knobs):
    out = {}
    for name, value in knobs.items():
        if name not in KNOBS:
            continue
        allowed = KNOBS[name]
        if isinstance(allowed[0], str):
            if value in allowed:
                out[name] = value
        else:
            try:
                v = float(value)
            except (TypeError, ValueError):
                continue
            if v != v:
                continue
            out[name] = min(max(v, allowed[0]), allowed[1])
    return out


def numeric_knobs():
    return [k for k, v in KNOBS.items() if not isinstance(v[0], str)]


def file_sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()[:12]


def _valid_module(path):
    import subprocess
    r = subprocess.run(["node", "--input-type=module", "--check"], stdin=open(path), capture_output=True)
    return r.returncode == 0


def merge(a, b):
    for k, v in b.items():
        if isinstance(v, dict) and isinstance(a.get(k), dict):
            merge(a[k], v)
        else:
            a[k] = v
    return a


class Loop:
    def __init__(self, event, scene, name, site=None, params=None):
        self.event = event
        self.scene = Path(scene)
        self.scene_url = "/" + str(self.scene.relative_to(ROOT / "web"))
        self.dir = RUNS / "loop" / name
        self.dir.mkdir(parents=True, exist_ok=True)
        self.site = site or json.loads((ROOT / "site" / "site.json").read_text())
        self.params = clamp(params or json.loads((ROOT / "site" / "params.json").read_text()))
        for k in numeric_knobs():
            if k not in self.params:
                lo, hi = KNOBS[k]
                self.params[k] = (lo + hi) / 2
        self.params.setdefault("basement_path", "sewer")
        self.patch = {}
        self.video = False
        self.workers = False
        self.worker_info = None
        self.step = 0.4
        self.steps = {}
        self.knob_turn = 0
        self.current_knob = None
        self.history = []
        self.renderer = Renderer()
        self.renderer.site = self.site
        self.times = key_times(event)
        self.labels = [f"t={t} s" for t in self.times]

    def video_window(self):
        """From just before water shows in the drain to well after the floor drains, read from Argon's video
        timeline (never from gauges). Deeper water drains later, so the draining phase must be in view."""
        tl = RUNS / "timeline" / f"{self.event}.json"
        d = json.loads(tl.read_text()) if tl.exists() else {}
        first = d.get("basement_drain_water_s") or d.get("basement_wet_onset_s") or 240
        last = d.get("basement_recede_s") or first + 600
        start, end = max(0, round(first) - 90), round(last) + 300
        span = (data.event_window(self.event)[1] - data.event_window(self.event)[0]).total_seconds()
        return start, int(min(end, span - 10))

    def real_frames(self, out, times=None):
        from backend import frames
        return frames.real_frames(self.event, CAM, times or self.times, out / "real")

    def structural_round(self, n, max_iter=3):
        out = self.dir / f"round_{n:02d}"
        out.mkdir(parents=True, exist_ok=True)
        t0 = time.time()
        dry = {"t": [0], "depth_m": {}}
        scene_before = str(self.scene)
        progress.report(self.dir, "render", "Checking Argon's 3D scene against the real dry camera frame", round=n)
        real = self.real_frames(out, [0])
        log = []
        sheet = None
        for i in range(max_iter + 1):
            self.renderer.patch = self.patch
            render = self.renderer.render(self.scene_url, dry, CAM, [0], out / f"render_{i}")[0]
            sheet = contact.contact_sheet(real, [render], [f"{CAM} dry, pass {i}"], out / f"contact_{i}.png")
            if i == max_iter:
                break
            fix = argon.scene_fix(sheet, self.renderer.describe(self.scene_url))
            res = fix["result"]
            log.append({"pass": i, "differences": res.get("differences"), "patch": res.get("patch"),
                        "confidence": res.get("confidence"), "seconds": fix["seconds"], "usage": fix["usage"]})
            rewrite = (res.get("rewrite") or "").strip()
            if rewrite:
                new_scene = self.scene.with_name(f"{self.dir.name}_s{i + 1}.js")
                rw = argon.patch_scene(self.scene.read_text(), rewrite, sheet, new_scene)
                log[-1]["rewrite"] = {"instruction": rewrite, "new_scene": str(new_scene), "seconds": rw["seconds"]}
                if _valid_module(new_scene):
                    self.scene = new_scene
                    self.scene_url = "/" + str(self.scene.relative_to(ROOT / "web"))
                else:
                    log[-1]["rewrite"]["rejected"] = "syntax check failed"
            if res.get("patch"):
                self.patch = merge(self.patch, res["patch"])
            if not res.get("patch") and not rewrite:
                break
        (self.dir / "patch.json").write_text(json.dumps(self.patch, indent=1))
        evidence = "; ".join(d for l in log for d in (l.get("differences") or []))
        record = {"round": n, "kind": "structure", "event": self.event, "scene": str(self.scene), "scene_before": scene_before,
                  "scene_sha": file_sha(self.scene), "patch": self.patch, "params": copy.deepcopy(self.params),
                  "contact": str(sheet),
                  "critique": {"rows": [{"label": "dry frame", "verdict": "patched" if self.patch else "same", "evidence": evidence}],
                               "passes": log},
                  "applied_knobs": {}, "scene_changed": bool(self.patch) or any(l.get("rewrite") for l in log), "seconds": {"total": round(time.time() - t0, 1)}}
        (out / "round.json").write_text(json.dumps(record, indent=1, default=str))
        self.history.append({"round": n, "scene_patch": bool(self.patch)})
        return record

    def path_candidates(self):
        cands = {L: dict(self.params, basement_path=p) for L, p in zip(LABELS, KNOBS["basement_path"])}
        if self.workers:
            cands = self.worker_candidates(cands)
        return cands

    def worker_candidates(self, cands):
        """Run one hypothesis worker per path in parallel; each candidate takes its worker's best knob values.
        A candidate whose worker fails keeps the current parameters."""
        from workers import hypothesis
        t0 = time.time()
        name = f"{self.dir.name}_r{len(self.history):02d}"
        info = {"name": name, "event": self.event, "dry_event": SPLIT["dry"], "per_hypothesis": {}}
        try:
            targets = hypothesis.targets_from_timeline(self.event)
            summary = hypothesis.run_all(self.event, SPLIT["dry"], targets, name, site=self.site, params=self.params)
        except Exception as e:
            info.update(error=str(e)[:500], seconds=round(time.time() - t0, 1))
            self.worker_info = info
            return cands
        info.update(targets=targets, seconds=summary["wall_seconds"], total_tokens=summary["total_tokens"])
        out = {}
        for L, c in cands.items():
            brief = dict(summary["workers"].get(c["basement_path"]) or {})
            best = clamp(brief.get("best_knobs") or {})
            best = {k: v for k, v in best.items() if k in numeric_knobs()}
            ok = bool(brief.get("best_knobs")) and len(best) == len(numeric_knobs())
            brief.update(candidate=L, used=ok, runs=brief.get("n_cal_runs_logged"))
            if not ok:
                brief["dropped"] = "worker did not finish; candidate left out rather than shown with unfitted settings"
            info["per_hypothesis"][c["basement_path"]] = brief
            if ok:
                out[L] = dict(c, **best)
        if len(out) < 2:
            info["note"] = "fewer than two workers finished; using the plain path candidates"
            out = cands
        self.worker_info = info
        return out

    def diagonal_candidates(self):
        """A: current. B: less basement water. C: more. Every setting moves in the direction that has that effect.
        Used for the short live calibration, where the first big correction matters most."""
        effects = json.loads((ROOT / "site" / "knob_effects.json").read_text())["less_water"]
        less, more = dict(self.params), dict(self.params)
        for k in numeric_knobs():
            lo, hi = KNOBS[k]
            v = self.params[k]
            up, down = v + self.step * (hi - v), v - self.step * (v - lo)
            less[k], more[k] = (up, down) if effects.get(k, 1) > 0 else (down, up)
        self.current_knob = None
        return {"A": dict(self.params), "B": less, "C": more}

    def numeric_candidates(self):
        """Coordinate search: each round moves one setting, cycling through them. A: current, B: that setting lower,
        C: that setting higher. Moving one at a time lets the search go in any direction, not only along one line."""
        knobs = numeric_knobs()
        k = knobs[self.knob_turn % len(knobs)]
        self.knob_turn += 1
        lo, hi = KNOBS[k]
        v, s = self.params[k], self.steps.setdefault(k, 0.4)
        lower, higher = dict(self.params), dict(self.params)
        lower[k] = v - s * (v - lo)
        higher[k] = v + s * (hi - v)
        self.current_knob = k
        return {"A": dict(self.params), "B": lower, "C": higher}

    def judged_round(self, n, candidates, kind):
        out = self.dir / f"round_{n:02d}"
        out.mkdir(parents=True, exist_ok=True)
        t0 = time.time()
        depths, renders = {}, {}
        self.renderer.patch = self.patch
        what = f"which way water enters the basement" if kind == "path" else f"setting {self.current_knob}"
        progress.report(self.dir, "simulate", f"Round {n}: simulating 3 versions of the model ({what})", round=n,
                        candidates=candidates)
        # PySWMM allows one simulation per process, so the candidates run in separate processes at once.
        with ProcessPoolExecutor(max_workers=len(candidates)) as ex:
            futs = {L: ex.submit(sim.run, self.site, p, self.event, f"loop_{self.dir.name}_r{n:02d}_{L}")
                    for L, p in candidates.items()}
            for L, f in futs.items():
                depths[L] = f.result()
        if self.video:
            from backend import videojudge
            start, end = self.video_window()
            progress.report(self.dir, "render", f"Round {n}: drawing each version in Argon's 3D scene, from the real camera's view", round=n,
                            depths={L: str(Path(depths[L]).relative_to(ROOT)) for L in depths}, scene=self.scene_url,
                            patch=self.patch, window=[start, end], event=self.event, candidates=candidates)
            video, sheet = videojudge.build_video(self.renderer, self.scene_url, depths, self.event, CAM, start, end, out)
            progress.report(self.dir, "upload", f"Round {n}: sending Argon a {round((end - start) / 60)}-minute time-lapse, real flood beside the 3 versions",
                            round=n, video=video)
            t_sim = time.time()
            key = json.dumps({"event": self.event, "scene": file_sha(self.scene), "patch": self.patch, "step": videojudge.STEP_S,
                              "window": [start, end], "candidates": candidates}, sort_keys=True, default=str)
            verdict = videojudge.judge(video, key, on_stage=lambda s: progress.report(
                self.dir, "watching", f"Round {n}: Argon is watching the video", round=n, video=video) if s == "watching" else None)
            res = verdict["result"]
            res["rows"] = [{"label": m.get("time"), "best": m.get("best"), "evidence": m.get("evidence")} for m in (res.get("moments") or [])]
        else:
            for L in candidates:
                renders[L] = self.renderer.render(self.scene_url, depths[L], CAM, self.times, out / f"render_{L}")
            t_sim = time.time()
            real = self.real_frames(out)
            sheet = contact.judge_sheet(real, renders, self.labels, out / "contact.png")
            verdict = argon.judge(sheet)
            res = verdict["result"]
        winner = res.get("winner") if res.get("winner") in candidates else "A"
        chosen = candidates[winner]
        changed = {k: v for k, v in chosen.items() if self.params.get(k) != v}
        if kind == "numeric" and winner == "A" and self.current_knob:
            self.steps[self.current_knob] = self.steps.get(self.current_knob, 0.4) * 0.5
        if kind == "numeric" and winner == "A" and self.current_knob is None:
            self.step *= 0.5
        self.params = dict(chosen)
        rows = [{"label": r.get("label"), "verdict": r.get("best"), "evidence": r.get("evidence")} for r in (res.get("rows") or [])]
        record = {"round": n, "kind": kind, "event": self.event, "scene": str(self.scene), "scene_sha": file_sha(self.scene),
                  "patch": self.patch, "params": copy.deepcopy(self.params), "candidates": candidates, "winner": winner,
                  "depths": str(depths[winner]), "contact": str(sheet),
                  "critique": {"rows": rows, "remaining_error": res.get("remaining_error"), "direction": res.get("direction"),
                               "confidence": res.get("confidence"), "raw": res.get("raw")},
                  "applied_knobs": changed, "scene_changed": False, "usage": verdict["usage"],
                  **({"workers": self.worker_info} if kind == "path" and self.worker_info else {}),
                  "seconds": {"sim_render": round(t_sim - t0, 1), "judge": round(verdict["seconds"], 1),
                              "total": round(time.time() - t0, 1)}}
        (out / "round.json").write_text(json.dumps(record, indent=1, default=str))
        progress.report(self.dir, "verdict", f"Round {n}: Argon picked {winner}. {res.get('remaining_error') or ''}".strip(),
                        round=n, winner=winner, moments=rows, video=str(out / "judge.mp4") if self.video else None)
        self.history.append({"round": n, "winner": winner, "knobs": changed, "direction": res.get("direction")})
        return record

    def run(self, rounds=3, structure=True):
        records = []
        try:
            n = 0
            if structure:
                records.append(self.structural_round(n))
                n += 1
            records.append(self.judged_round(n, self.path_candidates(), "path"))
            n += 1
            same = 0
            for _ in range(rounds):
                rec = self.judged_round(n, self.numeric_candidates(), "numeric")
                records.append(rec)
                n += 1
                same = same + 1 if rec["winner"] == "A" else 0
                if same >= len(numeric_knobs()):
                    break
        finally:
            self.renderer.close()
        frozen = {"scene": str(self.scene), "scene_sha": file_sha(self.scene), "patch": self.patch,
                  "params": self.params, "site": self.site, "event": self.event}
        frozen["sha"] = hashlib.sha256(json.dumps(frozen, sort_keys=True).encode()).hexdigest()[:12]
        (self.dir / "frozen.json").write_text(json.dumps(frozen, indent=1))
        progress.report(self.dir, "done", f"Model frozen ({frozen['sha']}). Ready for the blind test.", sha=frozen["sha"], params=self.params)
        return records, frozen


def live_round(name, event=None, video=True):
    """One more judged round from the frozen state of an earlier run, for the live demo segment."""
    src = RUNS / "loop" / name
    live_name = f"{name}_live"
    d = RUNS / "loop" / live_name
    if not d.exists():
        import shutil
        shutil.copytree(src, d)
    frozen = json.loads((d / "frozen.json").read_text())
    lp = Loop(event or frozen["event"], ROOT / frozen["scene"], live_name, site=frozen.get("site"), params=frozen["params"])
    lp.patch = frozen.get("patch") or {}
    lp.video = video
    from backend import videojudge
    videojudge.STEP_S = 10
    n = len(list(d.glob("round_*/round.json")))
    try:
        rec = lp.judged_round(n, lp.numeric_candidates(), "numeric")
    finally:
        lp.renderer.close()
    rec["live"] = True
    (d / f"round_{n:02d}" / "round.json").write_text(json.dumps(rec, indent=1, default=str))
    return rec


def live_calibrate(name, rounds=2):
    """Short live calibration for the demo: start from the untuned model in the scene a finished run already fixed,
    and let Argon judge a few rounds of video. Writes to runs/loop/<name>_cal and freezes there."""
    import shutil
    from backend import videojudge
    src = json.loads((RUNS / "loop" / name / "frozen.json").read_text())
    cal = f"{name}_cal"
    d = RUNS / "loop" / cal
    if d.exists():
        shutil.rmtree(d)
    lp = Loop(src["event"], ROOT / src["scene"], cal, site=src.get("site"), params=None)
    lp.params["basement_path"] = "sewer"
    lp.patch = src.get("patch") or {}
    lp.video = True
    videojudge.STEP_S = 10
    progress.report(d, "simulate", "Starting from the untuned model. Argon will watch the flood and correct it.", round=0)
    records = []
    try:
        for n in range(1, rounds + 1):
            rec = lp.judged_round(n, lp.diagonal_candidates(), "numeric")
            rec["live"] = True
            (d / f"round_{n:02d}" / "round.json").write_text(json.dumps(rec, indent=1, default=str))
            records.append(rec)
    finally:
        lp.renderer.close()
    frozen = {"scene": str(lp.scene), "scene_sha": file_sha(lp.scene), "patch": lp.patch, "params": lp.params,
              "site": lp.site, "event": lp.event, "from_run": name}
    frozen["sha"] = hashlib.sha256(json.dumps(frozen, sort_keys=True).encode()).hexdigest()[:12]
    (d / "frozen.json").write_text(json.dumps(frozen, indent=1))
    progress.report(d, "done", f"Model frozen ({frozen['sha']}). Ready to test on a flood it has never seen.", sha=frozen["sha"],
                    params=lp.params)
    return records, frozen


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--live-calibrate", metavar="NAME", help="short live calibration from the untuned model, in NAME's scene")
    ap.add_argument("--live", metavar="NAME", help="run one live judged round on top of a frozen run")
    ap.add_argument("--event", type=int, default=SPLIT["calibrate"])
    ap.add_argument("--scene", default="web/scene/r0_blind.js")
    ap.add_argument("--name", default="calib")
    ap.add_argument("--rounds", type=int, default=3, help="numeric rounds after the path round")
    ap.add_argument("--no-structure", action="store_true")
    ap.add_argument("--video", action="store_true", help="Argon judges a side-by-side video instead of still frames")
    ap.add_argument("--workers", action="store_true", help="hypothesis workers tune each path candidate before Argon judges")
    a = ap.parse_args()
    if a.live_calibrate:
        records, frozen = live_calibrate(a.live_calibrate, a.rounds)
        print("live calibration", [r["winner"] for r in records], frozen["sha"], frozen["params"])
        return
    if a.live:
        rec = live_round(a.live, video=a.video or True)
        print("live round", rec["round"], rec["winner"], rec["applied_knobs"], rec["seconds"])
        return
    lp = Loop(a.event, ROOT / a.scene, a.name)
    lp.video = a.video
    lp.workers = a.workers
    records, frozen = lp.run(a.rounds, structure=not a.no_structure)
    for r in records:
        print(r["round"], r["kind"], r.get("winner"), r["applied_knobs"], r.get("scene_changed"), r["seconds"])
    print("frozen", frozen["sha"], frozen["params"])


if __name__ == "__main__":
    main()
