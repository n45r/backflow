"""Gauge scoring. Evaluator only: nothing in the loop may import this module."""
import argparse
import json
import shutil
from pathlib import Path

import numpy as np
import pandas as pd

from . import data
from .config import DT_S, EVALUATION, GAUGE_SOURCES, RAW, RUNS, WET_M, WET_SUSTAIN_S


def gauge_path(event, gauge):
    return EVALUATION / f"{event}_{gauge}.txt"


def stage_gauges(event):
    """Copy the gauge files for an event into evaluation/ (processed zip, else the all_ series)."""
    EVALUATION.mkdir(exist_ok=True)
    for gauge, source in GAUGE_SOURCES.items():
        dst = gauge_path(event, gauge)
        if dst.exists():
            continue
        for sub in ("calib", "monitor"):
            src = RAW / sub / str(event) / f"{event}_{source}.txt"
            if src.exists():
                shutil.copy(src, dst)
                break
        else:
            data.raw_series(event, source).rename("value").reset_index().assign(
                datetime=lambda d: d["datetime"].dt.strftime("%d/%m/%Y %H:%M:%S")
            ).to_csv(dst, sep=";", index=False)


def load_gauge(event, gauge, t):
    """Gauge depth in metres interpolated onto model times t (s from event start)."""
    stage_gauges(event)
    start, _ = data.event_window(event)
    s = data.read_series(gauge_path(event, gauge)) / 1000.0
    s.index = (s.index - start).total_seconds()
    s = s[~s.index.duplicated()].sort_index()
    return np.interp(t, s.index.to_numpy(), s.to_numpy(), left=np.nan, right=np.nan)


def onset_s(t, depth):
    """First time of a sustained (WET_SUSTAIN_S) crossing of WET_M, or None."""
    need = max(1, int(round(WET_SUSTAIN_S / DT_S)))
    above = np.nan_to_num(depth) > WET_M
    for i in range(len(above) - need + 1):
        if above[i:i + need].all():
            return float(t[i])
    return None


def score(event, depths_path):
    d = json.loads(Path(depths_path).read_text())
    t = np.array(d["t"], dtype=float)
    out = {"event": int(event)}
    for g in GAUGE_SOURCES:
        obs, mod = load_gauge(event, g, t), np.array(d["depth_m"][g])
        ok = ~np.isnan(obs)
        res = {
            "mae_m": float(np.mean(np.abs(mod[ok] - obs[ok]))),
            "peak_err_m": float(mod[ok].max() - np.nanmax(obs)),
            "obs_peak_m": float(np.nanmax(obs)), "model_peak_m": float(mod[ok].max()),
        }
        if g == "s6":
            o_obs, o_mod = onset_s(t[ok], obs[ok]), onset_s(t[ok], mod[ok])
            res.update(obs_onset_s=o_obs, model_onset_s=o_mod,
                       onset_err_s=None if o_obs is None or o_mod is None else o_mod - o_obs,
                       obs_wet=o_obs is not None, model_wet=o_mod is not None)
        out[g] = res
    out["basement_wet_match"] = out["s6"]["obs_wet"] == out["s6"]["model_wet"]
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--event", type=int, required=True)
    ap.add_argument("--run", required=True, help="run directory, e.g. runs/<id>")
    a = ap.parse_args()
    run = Path(a.run)
    run = run if run.exists() else RUNS / a.run
    print(json.dumps(score(a.event, run / "depths.json"), indent=2))


if __name__ == "__main__":
    main()
