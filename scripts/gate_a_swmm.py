"""Gate A: fill cq-analysis swmm_model_template.inp and run it with PySWMM.

Usage: python -I scripts/gate_a_swmm.py <data/raw dir> <out dir> <event> <start> <end> <forcing file> <obs dir|all>
  start/end as 'YYYY-mm-dd HH:MM:SS'. Forcing file: floodX 'datetime;value' L/s.
Fills placeholders the way swmm_calibration.SwmmModel.apply_parameters does
(string.Template + helpers.get_events initial-condition rules).
"""
import sys
import time
from pathlib import Path
from string import Template

import pandas as pd
from pyswmm import Simulation, Nodes, Links

RAW, OUT, EVENT, START, END, FORCING, OBS = sys.argv[1:8]
RAW, OUT = Path(RAW), Path(OUT)
OUT.mkdir(parents=True, exist_ok=True)
start, end = pd.Timestamp(START), pd.Timestamp(END)

# Parameters: midpoints of cq-analysis settings.py bounds where defined there.
# cd_r6 from the simple template's hard-coded value; cd_m2, cd_v2, seepage are
# NOT defined anywhere in the repos (assumed values).
params = {
    "r_px": (0.005 + 0.02) / 2,
    "r_p3": (0.009 + 0.03) / 2,
    "cd_m1": (0.48 + 0.72) / 2,
    "cd_m3": (0.42 + 0.78) / 2,
    "cd_r4": (0.1 + 0.72) / 2,
    "cd_w1": (1.1 + 2.1) / 2,
    "cd_r6": 0.84,
    "cd_m2": 0.6,   # assumed
    "cd_v2": 0.6,   # assumed
    "seepage": 0,   # assumed
}

# Initial conditions: cq-analysis data/initial_conditions.csv + helpers.py rules.
ic_tab = pd.read_csv(RAW / "cq-analysis" / "data" / "initial_conditions.csv", index_col=0)
ev = int(EVENT)
row = ic_tab.loc[ev] if ev in ic_tab.index else ic_tab.loc[25]  # fallback: event 25 (assumed)
ic = {"id_m1": row.id_m1, "id_m2": row.id_m2, "id_s5": row.id_s5}
ic.update({
    "id_v9": ic["id_s5"], "id_4": ic["id_s5"] + 0.68, "id_9": ic["id_s5"] + 0.68,
    "id_v8": ic["id_s5"], "id_v7": ic["id_s5"], "id_v4": ic["id_s5"],
    "id_m3": ic["id_s5"] + 0.5,
    "id_1": ic["id_m2"] + 0.21,  # commented-out rule in helpers.py (assumed)
})

# Forcing: resample to 1 s, interpolate, clip, write 'm/d/Y H:M:S value'.
f = pd.read_csv(FORCING, sep=";")
f["datetime"] = pd.to_datetime(f["datetime"], format="%d/%m/%Y %H:%M:%S")
q = f.groupby("datetime")["value"].mean().resample("1s").mean().interpolate()
q = q.reindex(pd.date_range(start, end, freq="1s")).fillna(0.0).clip(lower=0)
forcing_path = OUT / f"forcing_{EVENT}.txt"
with open(forcing_path, "w") as fh:
    for t, v in q.items():
        fh.write(f"{t:%m/%d/%Y} {t:%H:%M:%S} {v:.3f}\n")

fill = {
    "forcing_data_file": str(forcing_path.resolve()),
    "sim_start_date": f"{start:%m/%d/%Y}", "sim_start_time": f"{start:%H:%M:%S}",
    "sim_end_date": f"{end:%m/%d/%Y}", "sim_end_time": f"{end:%H:%M:%S}",
    "sim_report_step": "0:00:05",
}
fill.update(params)
fill.update(ic)
tmpl = Template((RAW / "cq-analysis" / "swmm_model_template.inp").read_text())
inp = OUT / f"model_{EVENT}.inp"
inp.write_text(tmpl.substitute(fill))

watch = ["s6", "s3", "m3", "s5", "m1", "m2"]
peaks = {n: 0.0 for n in watch}
t_peak = {}
s6_wet = None
t0 = time.time()
with Simulation(str(inp)) as sim:
    nodes = Nodes(sim)
    r5 = Links(sim)["r5"]
    r5_min = r5_max = 0.0
    for _ in sim:
        for n in watch:
            d = nodes[n].depth
            if d > peaks[n]:
                peaks[n], t_peak[n] = d, sim.current_time
        if s6_wet is None and nodes["s6"].depth > 0.005:
            s6_wet = sim.current_time
        r5_min, r5_max = min(r5_min, r5.flow), max(r5_max, r5.flow)
runtime = time.time() - t0
# pyswmm's sim.flow_routing_error read inside the loop context returned 0.0;
# take the value SWMM writes to the report file instead.
rpt = inp.with_suffix(".rpt").read_text().split("Flow Routing Continuity", 1)[1]
flow_err = [l for l in rpt.splitlines() if "Continuity Error" in l][0].split()[-1]

print(f"event {EVENT}  sim {start} -> {end}  runtime {runtime:.1f} s")
print(f"flow routing continuity error (from .rpt) {flow_err} %")
print(f"inflow volume forced: {q.sum() / 1000:.2f} m3")
print(f"r5 (s6<->m3 orifice) flow range: {r5_min:.2f} .. {r5_max:.2f} L/s (+ = s6->m3)")
print(f"model first s6 > 5 mm: {s6_wet}")
for n in watch:
    print(f"  model peak depth {n}: {peaks[n] * 1000:.0f} mm at {t_peak.get(n)}")

# Measured peaks
def rd(p):
    d = pd.read_csv(p, sep=";")
    d["datetime"] = pd.to_datetime(d["datetime"], format="%d/%m/%Y %H:%M:%S")
    return d.groupby("datetime")["value"].mean().loc[start:end]

for ds in ("s6_h_us_maxbotix", "s3_h_us_maxbotix", "s5_h_us_maxbotix_2"):
    p = (RAW / "cq-analysis" / "data" / f"all_{ds}.txt") if OBS == "all" else Path(OBS) / f"{EVENT}_{ds}.txt"
    if p.exists():
        s = rd(p)
        print(f"  measured peak {ds}: {s.max():.0f} mm at {s.idxmax()}")
