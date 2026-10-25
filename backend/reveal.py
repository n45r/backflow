"""Reveal: frozen models predict the held-out event, then meet the gauges.

This is the only module where gauge data and predictions are put side by side.
Writes runs/reveal/<name>.json.
"""
import argparse
import hashlib
import json

import numpy as np

from . import evaluator, sim
from .baseline import OUT as BASELINE_OUT, landmarks
from .config import RUNS, SITE_JSON, SPLIT, WET_M

OUT = RUNS / "reveal"
BLIND = {"basement_path": "sewer", "outlet_cd": None, "p7_diameter_m": None, "p3_roughness": None}  # template defaults


def params_sha(params, site):
    raw = json.dumps({"params": params, "site": site}, sort_keys=True).encode()
    return hashlib.sha256(raw).hexdigest()


def _mm(a):
    return [None if np.isnan(v) else round(float(v) * 1000, 2) for v in np.asarray(a, dtype=float)]


def make(name, blind_params=None, informed_params=None, holdout=None, site=None, baseline_params=None):
    holdout = int(holdout or SPLIT["holdout"])
    site = site or sim.load_json(SITE_JSON)
    models = {"blind": blind_params or BLIND,
              "baseline": baseline_params or sim.load_json(BASELINE_OUT / "params.json"),
              "informed": informed_params}
    out = {"name": name, "event": holdout, "site": site, "models": {}}
    t_ref = None
    for label, params in models.items():
        if params is None:
            continue
        path = sim.run(site, params, holdout, f"reveal/{name}_{label}")
        d = sim.load_json(path)
        t_ref = d["t"]
        s = evaluator.score(holdout, path)
        out["models"][label] = {
            "params": params,
            "sha256": params_sha(params, site),
            "pred_mm": {"s6": _mm(d["depth_m"]["s6"]), "s3": _mm(d["depth_m"]["s3"])},
            "continuity_error_pct": d["continuity_error_pct"],
            "s6": {"mae_mm": s["s6"]["mae_m"] * 1000, "peak_err_mm": s["s6"]["peak_err_m"] * 1000,
                   "model_peak_mm": s["s6"]["model_peak_m"] * 1000, "onset_err_s": s["s6"]["onset_err_s"],
                   "model_onset_s": s["s6"]["model_onset_s"], "wet": s["s6"]["model_wet"]},
            "s3": {"mae_mm": s["s3"]["mae_m"] * 1000, "peak_err_mm": s["s3"]["peak_err_m"] * 1000,
                   "model_peak_mm": s["s3"]["model_peak_m"] * 1000},
            "wet_match": s["basement_wet_match"],
        }
    t = np.array(t_ref, dtype=float)
    obs6, obs3 = evaluator.load_gauge(holdout, "s6", t), evaluator.load_gauge(holdout, "s3", t)
    o6 = evaluator.onset_s(t[~np.isnan(obs6)], obs6[~np.isnan(obs6)])
    out["t"] = t_ref
    out["measured_mm"] = {"s6": _mm(obs6), "s3": _mm(obs3)}
    out["measured"] = {"s6_peak_mm": float(np.nanmax(obs6) * 1000), "s3_peak_mm": float(np.nanmax(obs3) * 1000),
                       "s6_onset_s": o6, "wet": o6 is not None}
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / f"{name}.json").write_text(json.dumps(out))
    return out


def timeline_vs_gauges(event, site=None):
    """Reporting only: the video timeline of an event against landmarks read from its gauges."""
    from . import timeline
    site = site or sim.load_json(SITE_JSON)
    tl = timeline.extract(event)
    start, end = sim.data.event_window(event)
    t = np.arange(0, (end - start).total_seconds() + 1, 10.0)
    g = {"t": t.tolist(), "depth_m": {}}
    for n in ("s3", "s6"):
        g["depth_m"][n] = np.nan_to_num(evaluator.load_gauge(event, n, t)).tolist()
    g["depth_m"]["m3"] = [0.0] * len(t)          # no drain gauge
    lm = landmarks(g, site)
    rows = {}
    for k in timeline.LANDMARKS:
        v, gv = tl.get(k), lm.get(k)
        rows[k] = {"video_s": v, "gauge_s": gv,
                   "err_s": None if v is None or gv is None else round(v - gv, 1)}
    return {"event": int(event), "role": tl.get("role"), "rows": rows,
            "gauge_s6_peak_mm": lm["s6_peak_mm"], "wet_threshold_mm": WET_M * 1000}


def _summary(r):
    lines = [f"reveal {r['name']} event {r['event']}: measured s6 peak {r['measured']['s6_peak_mm']:.1f} mm, "
             f"onset {r['measured']['s6_onset_s']} s"]
    for k, m in r["models"].items():
        lines.append(f"  {k:8s} s6 MAE {m['s6']['mae_mm']:.1f} mm  peak err {m['s6']['peak_err_mm']:+.1f} mm  "
                     f"onset err {m['s6']['onset_err_s']} s  wet {m['s6']['wet']}  | s3 MAE {m['s3']['mae_mm']:.1f} mm "
                     f"peak err {m['s3']['peak_err_mm']:+.1f} mm  | {m['params']}")
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--name", required=True)
    ap.add_argument("--informed", help="path to informed params.json (default: baseline params)")
    ap.add_argument("--baseline", default=str(BASELINE_OUT / "params.json"))
    ap.add_argument("--holdout", type=int)
    a = ap.parse_args()
    base = sim.load_json(a.baseline)
    informed = sim.load_json(a.informed) if a.informed else base
    print(_summary(make(a.name, BLIND, informed, a.holdout, baseline_params=base)))


if __name__ == "__main__":
    main()
