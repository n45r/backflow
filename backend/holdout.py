"""Evaluator side: predict the held-out flood with the untuned and the frozen model, then score both on the gauges.

This is the only place where predictions meet gauge data. Nothing in the loop imports it.
"""
import argparse
import json
from pathlib import Path

import numpy as np

from backend import evaluator, sim
from backend.config import RUNS, SPLIT
from backend.loop import KNOBS, clamp, numeric_knobs

ROOT = Path(__file__).resolve().parent.parent


def untuned_params():
    """The template defaults: the model before it saw any flood video."""
    p = clamp(json.loads((ROOT / "site" / "params.json").read_text()))
    for k in numeric_knobs():
        if k not in p:
            lo, hi = KNOBS[k]
            p[k] = (lo + hi) / 2
    p.setdefault("basement_path", "sewer")
    return p


def _series(a):
    return [None if (x is None or (isinstance(x, float) and np.isnan(x))) else round(float(x), 4) for x in a]


def make(name, event=None):
    d = RUNS / "loop" / name
    frozen = json.loads((d / "frozen.json").read_text())
    event = event or SPLIT["holdout"]
    site = frozen.get("site") or json.loads((ROOT / "site" / "site.json").read_text())
    models = {"blind": untuned_params(), "informed": frozen["params"]}
    bp = RUNS / "baseline" / "params.json"
    if bp.exists():
        models["baseline"] = clamp(json.loads(bp.read_text()))
    depths, scores = {}, {}
    for label, params in models.items():
        depths[label] = sim.run(site, params, event, f"holdout_{name}_{label}")
        scores[label] = evaluator.score(event, depths[label])
    (d / "holdout.json").write_text(json.dumps({
        "event": event, "frozen_sha": frozen.get("sha"),
        "blind_scene": frozen["scene"], "blind_depths": str(depths["blind"]),
        "informed_scene": frozen["scene"], "informed_depths": str(depths["informed"]),
        "params": {k: models[k] for k in models},
    }, indent=1))
    t = json.loads(Path(depths["informed"]).read_text())["t"]
    out = {"name": name, "event": event, "fixture": False, "frozen_sha": frozen.get("sha"), "t": t, "gauges": {}}
    labels = {"s6": "Basement (s6)", "s3": "Pond (s3)"}
    for g in ("s6", "s3"):
        measured = evaluator.load_gauge(event, g, np.array(t, dtype=float))
        entry = {"label": labels[g], "measured_m": _series(measured)}
        for label in ("blind", "informed"):
            entry[f"{label}_m"] = _series(json.loads(Path(depths[label]).read_text())["depth_m"][g])
            entry[label] = scores[label][g]
        out["gauges"][g] = entry
    if "baseline" in scores:
        out["baseline"] = {"label": "Numeric optimiser on video timeline", "s6": scores["baseline"]["s6"],
                           "params": models["baseline"]}
    path = RUNS / "reveal" / f"{name}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(out, indent=1))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--name", required=True)
    ap.add_argument("--event", type=int, default=None)
    a = ap.parse_args()
    out = make(a.name, a.event)
    for label in ("blind", "informed", "baseline"):
        s = out["gauges"]["s6"].get(label) or (out.get("baseline") or {}).get("s6")
        if s:
            print(label, "basement mae mm", round(s["mae_m"] * 1000, 1), "peak err mm", round(s["peak_err_m"] * 1000, 1),
                  "onset err s", s.get("onset_err_s"), "wet", s.get("model_wet"))


if __name__ == "__main__":
    main()
