"""Gate A: per-event summary of FloodX events.

Usage: python -I scripts/gate_a_events.py <data/raw dir>
Reads processed per-event files (calib/ then monitor/), falls back to the
cq-analysis 'all_' series for events without processed files.
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

RAW = Path(sys.argv[1])
EXP = RAW / "meta_v2" / "experiment_list.csv"
WET_MM = 5.0
SUSTAIN_S = 30  # "sustained" = above WET_MM for at least this many seconds


def read_series(path):
    df = pd.read_csv(path, sep=";")
    df["datetime"] = pd.to_datetime(df["datetime"], format="%d/%m/%Y %H:%M:%S")
    s = df.groupby("datetime")["value"].mean().sort_index()
    return s


_all_cache = {}


def series_for(event, ds, start, end):
    for sub in ("calib", "monitor"):
        p = RAW / sub / str(event) / f"{event}_{ds}.txt"
        if p.exists():
            return read_series(p), sub
    allp = RAW / "cq-analysis" / "data" / f"all_{ds}.txt"
    if allp.exists():
        if ds not in _all_cache:
            _all_cache[ds] = read_series(allp)
        s = _all_cache[ds].loc[start:end]
        if len(s):
            return s, "cq-all"
    return None, None


def first_wet(s):
    if s is None or s.empty:
        return None
    r = s.resample("1s").mean().interpolate(limit=5)
    above = (r > WET_MM).astype(int)
    run = above.groupby((above != above.shift()).cumsum()).transform("size") * above
    hits = r.index[(above == 1) & (run >= SUSTAIN_S)]
    return hits[0] if len(hits) else None


def volume_m3(s):
    if s is None or s.empty:
        return None
    t = (s.index - s.index[0]).total_seconds().to_numpy()
    return float(np.trapezoid(s.clip(lower=0).to_numpy(), t) / 1000.0)


def session(start, lighting):
    d = start.strftime("%y%m%d")
    if d == "161005":
        return "161005A" if start.hour < 13 else "161005B"
    if d == "161006":
        return "161006B" if "Night" in str(lighting) else "161006A"
    if d == "161007":
        return "161007A"
    return "?"


def main():
    exp = pd.read_csv(EXP, sep=";")
    rows = []
    for _, e in exp.iterrows():
        st = pd.to_datetime(e.start_datetime, format="%d.%m.%y %H:%M")
        en = pd.to_datetime(e.end_datetime, format="%d.%m.%y %H:%M")
        s6, src6 = series_for(e.id, "s6_h_us_maxbotix", st, en)
        s3, src3 = series_for(e.id, "s3_h_us_maxbotix", st, en)
        q, srcq = series_for(e.id, "p1_q_mid_endress_logi", st, en)
        fw = first_wet(s6)
        light = str(e.env_lighting)
        rows.append({
            "id": e.id,
            "date": st.strftime("%Y-%m-%d"),
            "start": st.strftime("%H:%M"),
            "end": en.strftime("%H:%M"),
            "light": "night" if "Night" in light else ("dusk" if "dusk" in light else "day"),
            "s6_peak_mm": None if s6 is None else round(float(s6.max()), 1),
            "s6_first_wet": None if fw is None else fw.strftime("%H:%M:%S"),
            "s6_wet_after_min": None if fw is None else round((fw - st).total_seconds() / 60, 1),
            "s3_peak_mm": None if s3 is None else round(float(s3.max()), 1),
            "inflow_m3": None if q is None else round(volume_m3(q), 2),
            "q_peak_Ls": None if q is None else round(float(q.max()), 1),
            "src": f"{src6}/{src3}/{srcq}",
            "session": session(st, light),
            "quality": e.experiment_quality,
        })
    out = pd.DataFrame(rows)
    pd.set_option("display.width", 250, "display.max_columns", 30, "display.max_rows", 100)
    print(out.to_string(index=False))
    out.to_csv(RAW / "gate_a_events.csv", index=False)


if __name__ == "__main__":
    main()
