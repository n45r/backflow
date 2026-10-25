"""Numeric baseline: tune hydraulic knobs so SWMM landmark times match the video timeline.

Uses only the calibration event's video timeline and SWMM output (no gauges), plus the
dry check event. Writes runs/baseline/params.json.
"""
import argparse
import json
import time
from pathlib import Path

import numpy as np
from scipy.optimize import minimize

from . import sim, timeline
from .config import DT_S, ROOT, RUNS, SITE_JSON, SPLIT, WET_M, WET_SUSTAIN_S

OUT = RUNS / "baseline"
BOUNDS = {"orifice_cd": (0.2, 0.8), "weir_cd": (1.1, 2.1),
          "outlet_cd": (0.1, 1.0), "p7_diameter_m": (0.05, 0.15), "p3_roughness": (0.009, 0.03)}
LEGACY_KNOBS = ("orifice_cd", "weir_cd")                          # neither moves the basement depth
LOOP_KNOBS = ("outlet_cd", "p7_diameter_m", "p3_roughness")      # the knobs the loop tunes (site/knobs.json)
X0 = {"orifice_cd": sim.FIXED_DEFAULTS["cd_m3"], "weir_cd": sim.FIXED_DEFAULTS["cd_w1"],
      "outlet_cd": sim.FIXED_DEFAULTS["cd_r4"], "p7_diameter_m": 0.1472, "p3_roughness": sim.FIXED_DEFAULTS["r_p3"]}
FIT = ("pond_overflow_onset_s", "basement_wet_onset_s", "basement_peak_s", "basement_recede_s")
MISSING_MIN = 20.0           # squared-error stand-in (minutes) when a landmark is seen but not simulated
DRY_WEIGHT = 2.0             # cost per mm above WET_M on the dry event (1 mm ~ 1.4 min of timing error)
M3_INVERT_M = 417.44         # template junction m3 (basement drain shaft)
DRAIN_VISIBLE_BELOW_FLOOR_M = 0.10


def _sustained_first(t, mask, start=0):
    need = max(1, int(round(WET_SUSTAIN_S / DT_S)))
    for i in range(start, len(mask) - need + 1):
        if mask[i:i + need].all():
            return i
    return None


def landmarks(depths, site):
    """Landmark times (s from event start) from a depths.json dict, same definitions as the video."""
    t = np.array(depths["t"], dtype=float)
    s3 = np.array(depths["depth_m"]["s3"])
    s6 = np.array(depths["depth_m"]["s6"])
    m3 = np.array(depths["depth_m"]["m3"])
    out = dict.fromkeys(timeline.LANDMARKS)
    over = np.nonzero(s3 > site["weir_crest_m"])[0]   # weir crest is a depth above the s3 invert
    if len(over):
        out["pond_overflow_onset_s"] = float(t[over[0]])
    drain = np.nonzero(m3 >= site["basement_floor_m"] - M3_INVERT_M - DRAIN_VISIBLE_BELOW_FLOOR_M)[0]
    if len(drain):
        out["basement_drain_water_s"] = float(t[drain[0]])
    i = _sustained_first(t, s6 > WET_M)
    if i is not None:
        out["basement_wet_onset_s"] = float(t[i])
        k = int(np.argmax(s6))
        out["basement_peak_s"] = float(t[k])
        j = _sustained_first(t, s6 <= WET_M, start=k)
        out["basement_recede_s"] = float(t[j]) if j is not None else None
    out["s6_peak_mm"] = float(s6.max() * 1000)
    return out


def _params(u, knobs):
    """Unit-cube point u -> params dict."""
    p = {"basement_path": "sewer"}
    for k, v in zip(knobs, np.clip(u, 0, 1)):
        lo, hi = BOUNDS[k]
        p[k] = round(float(lo + v * (hi - lo)), 5)
    return p


def fit(max_runs=40, event=None, dry=None, holdout=None, out=None, knobs=LOOP_KNOBS):
    event = int(event or SPLIT["calibrate"])
    dry = int(dry or SPLIT["dry"])
    holdout = int(holdout or SPLIT["holdout"])
    out = Path(out) if out else OUT
    out = out if out.is_absolute() else ROOT / out
    if event == holdout:
        raise ValueError("the held-out event cannot be used for calibration")
    target = timeline.extract(event)
    if target.get("role") == "check":
        raise ValueError(f"timeline {event} is labelled check; it cannot be a calibration target")
    site = sim.load_json(SITE_JSON)
    use = [k for k in FIT if target.get(k) is not None]
    weight = {k: float(target["landmark_confidence"].get(k) or 1.0) for k in use}
    history, runs = [], [0]

    knobs = tuple(knobs)

    def cost(u):
        p = _params(u, knobs)
        lm = landmarks(sim.load_json(sim.run(site, p, event, str(out.relative_to(RUNS) / f"ev{event}_{runs[0]:02d}"))), site)
        dlm = landmarks(sim.load_json(sim.run(site, p, dry, str(out.relative_to(RUNS) / f"ev{dry}_{runs[0]:02d}"))), site)
        runs[0] += 1
        err = {}
        c = 0.0
        for k in use:
            if lm[k] is None:
                c += weight[k] * MISSING_MIN ** 2
                err[k] = None
            else:
                err[k] = lm[k] - target[k]
                c += weight[k] * (err[k] / 60.0) ** 2
        dry_pen = DRY_WEIGHT * max(0.0, dlm["s6_peak_mm"] - WET_M * 1000)
        c += dry_pen
        history.append({"params": p, "cost": round(c, 4), "err_s": err, "sim": lm,
                        "dry_s6_peak_mm": round(dlm["s6_peak_mm"], 2), "dry_penalty": round(dry_pen, 3)})
        print(f"eval {runs[0]:2d} {[p[k] for k in knobs]} cost {c:8.3f} "
              f"err {err} dry {dlm['s6_peak_mm']:.1f} mm", flush=True)
        return c

    u0 = np.array([(X0[k] - BOUNDS[k][0]) / (BOUNDS[k][1] - BOUNDS[k][0]) for k in knobs])
    simplex = [u0] + [u0 + np.eye(len(knobs))[i] * (0.3 if u0[i] < 0.6 else -0.3) for i in range(len(knobs))]
    t0 = time.time()
    res = minimize(cost, u0, method="Nelder-Mead", bounds=[(0, 1)] * len(knobs),
                   options={"maxfev": max_runs // 2, "initial_simplex": np.array(simplex), "xatol": 0.01, "fatol": 0.01})
    best = min(history, key=lambda h: h["cost"])
    out.mkdir(parents=True, exist_ok=True)
    result = {"params": best["params"], "cost": best["cost"], "err_s": best["err_s"], "sim": best["sim"],
              "dry_s6_peak_mm": best["dry_s6_peak_mm"], "target": {k: target[k] for k in use},
              "weights": weight, "knobs": {k: BOUNDS[k] for k in knobs}, "calibrate_event": event, "dry_event": dry, "holdout_event": holdout,
              "timeline_clips": target.get("clips"),
              "swmm_runs": 2 * len(history), "seconds": round(time.time() - t0, 1),
              "optimiser": f"scipy Nelder-Mead, {res.message}", "history": history}
    (out / "fit.json").write_text(json.dumps(result, indent=2))
    (out / "params.json").write_text(json.dumps(best["params"], indent=2))
    return result


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-runs", type=int, default=40)
    ap.add_argument("--event", type=int)
    ap.add_argument("--dry", type=int)
    ap.add_argument("--holdout", type=int)
    ap.add_argument("--out")
    ap.add_argument("--knobs", default=",".join(LOOP_KNOBS), help="comma list, e.g. orifice_cd,weir_cd")
    a = ap.parse_args()
    r = fit(a.max_runs, a.event, a.dry, a.holdout, a.out, a.knobs.split(","))
    print(json.dumps({k: v for k, v in r.items() if k != "history"}, indent=2))


if __name__ == "__main__":
    main()
