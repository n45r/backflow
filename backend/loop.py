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

from backend import argon, contact, data, sim
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
        self.step = 0.4
        self.history = []
        self.renderer = Renderer()
        self.renderer.site = self.site
        self.times = key_times(event)
        self.labels = [f"t={t} s" for t in self.times]

    def real_frames(self, out, times=None):
        from backend import frames
        return frames.real_frames(self.event, CAM, times or self.times, out / "real")

    def structural_round(self, n, max_iter=3):
        out = self.dir / f"round_{n:02d}"
        out.mkdir(parents=True, exist_ok=True)
        t0 = time.time()
        dry = {"t": [0], "depth_m": {}}
        scene_before = str(self.scene)
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
        return {L: dict(self.params, basement_path=p) for L, p in zip(LABELS, KNOBS["basement_path"])}

    def numeric_candidates(self):
        """A: current. B: less basement water. C: more. Each knob moves in the direction that has that effect."""
        effects = json.loads((ROOT / "site" / "knob_effects.json").read_text())["less_water"] if (ROOT / "site" / "knob_effects.json").exists() else {}
        cands = {"A": dict(self.params)}
        less, more = dict(self.params), dict(self.params)
        for k in numeric_knobs():
            lo, hi = KNOBS[k]
            v = self.params[k]
            sign = effects.get(k, 1)
            toward_hi = v + self.step * (hi - v)
            toward_lo = v - self.step * (v - lo)
            less[k], more[k] = (toward_hi, toward_lo) if sign > 0 else (toward_lo, toward_hi)
        cands["B"], cands["C"] = less, more
        return cands

    def judged_round(self, n, candidates, kind):
        out = self.dir / f"round_{n:02d}"
        out.mkdir(parents=True, exist_ok=True)
        t0 = time.time()
        depths, renders = {}, {}
        self.renderer.patch = self.patch
        # PySWMM allows one simulation per process, so the candidates run in separate processes at once.
        with ProcessPoolExecutor(max_workers=len(candidates)) as ex:
            futs = {L: ex.submit(sim.run, self.site, p, self.event, f"loop_{self.dir.name}_r{n:02d}_{L}")
                    for L, p in candidates.items()}
            for L, f in futs.items():
                depths[L] = f.result()
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
        if kind == "numeric" and winner == "A":
            self.step *= 0.5
        self.params = dict(chosen)
        rows = [{"label": r.get("label"), "verdict": r.get("best"), "evidence": r.get("evidence")} for r in (res.get("rows") or [])]
        record = {"round": n, "kind": kind, "event": self.event, "scene": str(self.scene), "scene_sha": file_sha(self.scene),
                  "patch": self.patch, "params": copy.deepcopy(self.params), "candidates": candidates, "winner": winner,
                  "depths": str(depths[winner]), "contact": str(sheet),
                  "critique": {"rows": rows, "remaining_error": res.get("remaining_error"), "direction": res.get("direction"),
                               "confidence": res.get("confidence"), "raw": res.get("raw")},
                  "applied_knobs": changed, "scene_changed": False, "usage": verdict["usage"],
                  "seconds": {"sim_render": round(t_sim - t0, 1), "judge": round(verdict["seconds"], 1),
                              "total": round(time.time() - t0, 1)}}
        (out / "round.json").write_text(json.dumps(record, indent=1, default=str))
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
                if same >= 2 or (same >= 1 and rec["critique"].get("direction") == "ok" and _ > 0):
                    break
        finally:
            self.renderer.close()
        frozen = {"scene": str(self.scene), "scene_sha": file_sha(self.scene), "patch": self.patch,
                  "params": self.params, "site": self.site, "event": self.event}
        frozen["sha"] = hashlib.sha256(json.dumps(frozen, sort_keys=True).encode()).hexdigest()[:12]
        (self.dir / "frozen.json").write_text(json.dumps(frozen, indent=1))
        return records, frozen


def live_round(name, event=None):
    """One more judged round from the frozen state of an earlier run, for the live demo segment."""
    d = RUNS / "loop" / name
    frozen = json.loads((d / "frozen.json").read_text())
    lp = Loop(event or frozen["event"], ROOT / frozen["scene"], name, site=frozen.get("site"), params=frozen["params"])
    lp.patch = frozen.get("patch") or {}
    n = len(list(d.glob("round_*/round.json")))
    try:
        rec = lp.judged_round(n, lp.numeric_candidates(), "numeric")
    finally:
        lp.renderer.close()
    rec["live"] = True
    (d / f"round_{n:02d}" / "round.json").write_text(json.dumps(rec, indent=1, default=str))
    return rec


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--live", metavar="NAME", help="run one live judged round on top of a frozen run")
    ap.add_argument("--event", type=int, default=SPLIT["calibrate"])
    ap.add_argument("--scene", default="web/scene/r0_blind.js")
    ap.add_argument("--name", default="calib")
    ap.add_argument("--rounds", type=int, default=3, help="numeric rounds after the path round")
    ap.add_argument("--no-structure", action="store_true")
    a = ap.parse_args()
    if a.live:
        rec = live_round(a.live)
        print("live round", rec["round"], rec["winner"], rec["applied_knobs"], rec["seconds"])
        return
    records, frozen = Loop(a.event, ROOT / a.scene, a.name).run(a.rounds, structure=not a.no_structure)
    for r in records:
        print(r["round"], r["kind"], r.get("winner"), r["applied_knobs"], r.get("scene_changed"), r["seconds"])
    print("frozen", frozen["sha"], frozen["params"])


if __name__ == "__main__":
    main()
