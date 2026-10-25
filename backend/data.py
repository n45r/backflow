"""Event inputs: inflow series, event window on the reference clock, initial conditions."""
import pandas as pd

from .config import CQ_DATA, EXPERIMENTS, INFLOW_SOURCE, INFLOW_USE_ALL, RAW


def read_series(path):
    df = pd.read_csv(path, sep=";")
    df["datetime"] = pd.to_datetime(df["datetime"], format="%d/%m/%Y %H:%M:%S")
    return df.groupby("datetime")["value"].mean().sort_index()


def event_window(event):
    row = pd.read_csv(EXPERIMENTS, sep=";").set_index("id").loc[int(event)]
    fmt = "%d.%m.%y %H:%M"
    return (pd.to_datetime(row.start_datetime, format=fmt),
            pd.to_datetime(row.end_datetime, format=fmt))


def raw_series(event, source, force_all=False):
    """Series for one datasource in native units, from the processed zips or the all_ file."""
    start, end = event_window(event)
    if not force_all:
        for sub in ("calib", "monitor"):
            p = RAW / sub / str(event) / f"{event}_{source}.txt"
            if p.exists():
                return read_series(p).loc[start:end]
    return read_series(CQ_DATA / f"all_{source}.txt").loc[start:end]


def inflow(event):
    """Inflow in m3/s on a 1 s grid indexed by seconds from event start."""
    start, end = event_window(event)
    q = raw_series(event, INFLOW_SOURCE, force_all=int(event) in INFLOW_USE_ALL)
    q = q.resample("1s").mean().interpolate()
    grid = pd.date_range(start, end, freq="1s")
    q = q.reindex(grid).fillna(0.0).clip(lower=0) / 1000.0
    q.index = (q.index - start).total_seconds().astype(int)
    return q


def initial_conditions(event):
    """Initial depths (m), following cq-analysis helpers.py rules."""
    tab = pd.read_csv(CQ_DATA / "initial_conditions.csv", index_col=0)
    row = tab.loc[int(event)] if int(event) in tab.index else tab.loc[25]
    m1, m2, s5 = float(row.id_m1), float(row.id_m2), float(row.id_s5)
    return {"id_m1": m1, "id_m2": m2, "id_s5": s5,
            "id_v9": s5, "id_4": s5 + 0.68, "id_9": s5 + 0.68,
            "id_v8": s5, "id_v7": s5, "id_v4": s5,
            "id_m3": s5 + 0.5, "id_1": m2 + 0.21}
