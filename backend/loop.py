"""The calibration loop: simulate, render, compare with real frames, critique, fix, repeat."""
import argparse
import copy
import hashlib
import json
import time
from pathlib import Path

from backend import argon, contact, data, sim
from backend.config import RUNS, SPLIT
from backend.render import Renderer

ROOT = Path(__file__).resolve().parent.parent
KNOBS = {"basement_path": ["sewer", "door", "both"], "weir_cd": [1.1, 2.1], "orifice_cd": [0.2, 0.8]}
CAMS = ["cam5"]


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


def file_sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()[:12]


class Loop:
    def __init__(self, event, scene, name, site=None, params=None):
        self.event = event
        self.scene = Path(scene)
        self.dir = RUNS / "loop" / name
        self.dir.mkdir(parents=True, exist_ok=True)
        self.site = site or json.loads((ROOT / "site" / "site.json").read_text())
        self.params = params or json.loads((ROOT / "site" / "params.json").read_text())
        for k, v in {"weir_cd": 1.6, "orifice_cd": 0.6}.items():
            if self.params.get(k) is None:
                self.params[k] = v
        self.history = []
        self.renderer = Renderer()
        self.renderer.site = self.site
        self.times = key_times(event)

    def real_frames(self, out):
        from backend import frames
        paths = []
        for cam in CAMS:
            paths += frames.real_frames(self.event, cam, self.times, out / "real")
        return paths

    def round(self, n):
        out = self.dir / f"round_{n:02d}"
        out.mkdir(parents=True, exist_ok=True)
        t0 = time.time()
        depths = sim.run(self.site, self.params, self.event, f"loop_{self.dir.name}_r{n:02d}")
        t_sim = time.time()
        scene_url = "/" + str(self.scene.relative_to(ROOT / "web"))
        renders = []
        for cam in CAMS:
            renders += self.renderer.render(scene_url, depths, cam, self.times, out / "render")
        t_render = time.time()
        real = self.real_frames(out)
        labels = [f"{cam} t={t}s" for cam in CAMS for t in self.times]
        sheet = contact.contact_sheet(real, renders, labels, out / "contact.png")
        crit = argon.critique(sheet, KNOBS, self.params, self.history)
        t_crit = time.time()
        res = crit["result"]
        changes = clamp(res.get("knob_changes") or {})
        record = {
            "round": n, "event": self.event, "scene": str(self.scene), "scene_sha": file_sha(self.scene),
            "params": copy.deepcopy(self.params), "depths": str(depths), "contact": str(sheet),
            "critique": res, "applied_knobs": changes, "usage": crit["usage"],
            "seconds": {"sim": round(t_sim - t0, 1), "render": round(t_render - t_sim, 1), "critique": round(t_crit - t_render, 1)},
        }
        self.params.update(changes)
        patch = (res.get("scene_patch") or "").strip()
        if patch:
            new_scene = self.scene.with_name(f"{self.dir.name}_r{n + 1:02d}.js")
            p = argon.patch_scene(self.scene.read_text(), patch, sheet, new_scene)
            record["scene_patch"] = {"instruction": patch, "new_scene": str(new_scene), "seconds": p["seconds"]}
            self.scene = new_scene
        record["seconds"]["total"] = round(time.time() - t0, 1)
        self.history.append({"round": n, "knobs": changes, "scene_patch": patch, "evidence": res.get("evidence")})
        (out / "round.json").write_text(json.dumps(record, indent=1, default=str))
        return record

    def run(self, rounds=4):
        records = []
        try:
            for n in range(rounds):
                rec = self.round(n)
                records.append(rec)
                res = rec["critique"]
                if n > 0 and not rec["applied_knobs"] and not rec.get("scene_patch"):
                    break
        finally:
            self.renderer.close()
        frozen = {"scene": str(self.scene), "scene_sha": file_sha(self.scene), "params": self.params, "site": self.site}
        frozen["sha"] = hashlib.sha256(json.dumps(frozen, sort_keys=True).encode()).hexdigest()[:12]
        (self.dir / "frozen.json").write_text(json.dumps(frozen, indent=1))
        return records, frozen


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--event", type=int, default=SPLIT["calibrate"])
    ap.add_argument("--scene", default="web/scene/r0_blind.js")
    ap.add_argument("--name", default="calib")
    ap.add_argument("--rounds", type=int, default=4)
    a = ap.parse_args()
    records, frozen = Loop(a.event, ROOT / a.scene, a.name).run(a.rounds)
    for r in records:
        print(r["round"], r["applied_knobs"], bool(r.get("scene_patch")), r["seconds"])
    print("frozen", frozen["sha"], frozen["params"])


if __name__ == "__main__":
    main()
