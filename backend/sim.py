"""Build and run the SWMM model for one event."""
import argparse
import hashlib
import json
import time
from pathlib import Path
from string import Template

import pandas as pd
from pyswmm import Nodes, Simulation

from . import data
from .config import DT_S, PARAMS_JSON, RUNS, SITE_JSON, TEMPLATE

NODES = ("s3", "s6", "m2", "m3", "s4")
BASEMENT_PATHS = ("sewer", "door", "both")
SURFACE_NODE = "s4"      # surface storage in front of the house (nearest the building)
SURFACE_INVERT_M = 419.76

# Fixed defaults. Values from cq-analysis settings.py bounds are midpoints; the rest are assumptions.
FIXED_DEFAULTS = {
    "r_px": (0.005 + 0.02) / 2,
    "r_p3": (0.009 + 0.03) / 2,
    "cd_m1": (0.48 + 0.72) / 2,
    "cd_m3": (0.42 + 0.78) / 2,        # orifice r5 (basement manhole), used when orifice_cd is null
    "cd_r4": (0.1 + 0.72) / 2,
    "cd_w1": (1.1 + 2.1) / 2,          # weir w1, used when weir_cd is null
    "cd_r6": 0.84,                     # from the simple template
    "cd_m2": 0.6,                      # assumed, not defined in the repos
    "cd_v2": 0.6,                      # assumed
    "seepage": 0,                      # assumed
    "sim_report_step": "0:00:05",
    "door_width_m": 1.0,               # assumed
    "door_cd": 1.8,                    # assumed sharp-crested weir coefficient (SI)
    "door_max_head_m": 1.0,            # assumed
    "r5_closed_offset_m": 99.0,        # orifice r5 raised out of reach when the sewer path is off
}

# Knobs in params.json that map onto template placeholders (null or absent keeps the FIXED_DEFAULTS value).
# outlet_cd: orifice r4, the outflow from shaft s5 through valve v4 (cd_r4). Range 0.1-1.0; the upper end
#   follows from the v4 flow factor at notch 8 (Kv 2100 m3/h) on the 0.234 m pipe p6.
# p3_roughness: Manning n of pipe p3, m1 -> m2 (r_p3). Range 0.009-0.03 (cq-analysis bounds).
# orifice_cd and weir_cd are kept for older params files; neither changes the basement depth.
KNOB_PLACEHOLDERS = {"outlet_cd": "cd_r4", "p3_roughness": "r_p3", "orifice_cd": "cd_m3", "weir_cd": "cd_w1"}
# p7_diameter_m: effective diameter of pipe p7, sewer -> basement manhole m3. Range 0.05-0.15 m;
#   null keeps site.json pipe_p7_diameter_m (0.1472 m, the measured inner diameter).


def sha(obj):
    if isinstance(obj, (str, Path)) and Path(obj).exists():
        raw = Path(obj).read_bytes()
    else:
        raw = json.dumps(obj, sort_keys=True).encode()
    return hashlib.sha1(raw).hexdigest()[:12]


def load_json(path):
    return json.loads(Path(path).read_text())


def build_inp(site, params, event, out_dir=None):
    """Write the forcing file and filled .inp for an event; return the .inp path."""
    path_mode = params.get("basement_path", "sewer")
    if path_mode not in BASEMENT_PATHS:
        raise ValueError(f"basement_path must be one of {BASEMENT_PATHS}")
    out_dir = Path(out_dir or RUNS / f"event{event}_{path_mode}")
    out_dir.mkdir(parents=True, exist_ok=True)
    start, end = data.event_window(event)

    q = data.inflow(event) * 1000.0  # L/s for the LPS template
    forcing = out_dir / "forcing.txt"
    with open(forcing, "w") as fh:
        for sec, v in q.items():
            t = start + pd.Timedelta(seconds=int(sec))
            fh.write(f"{t:%m/%d/%Y} {t:%H:%M:%S} {v:.3f}\n")

    fill = dict(FIXED_DEFAULTS)
    for knob, placeholder in KNOB_PLACEHOLDERS.items():
        if params.get(knob) is not None:
            fill[placeholder] = params[knob]
    p7_d = params.get("p7_diameter_m")
    p7_d = site["pipe_p7_diameter_m"] if p7_d is None else p7_d
    fill.update(data.initial_conditions(event))
    fill.update({
        "forcing_data_file": str(forcing.resolve()),
        "sim_start_date": f"{start:%m/%d/%Y}", "sim_start_time": f"{start:%H:%M:%S}",
        "sim_end_date": f"{end:%m/%d/%Y}", "sim_end_time": f"{end:%H:%M:%S}",
    })

    text = TEMPLATE.read_text()
    text = _swap(text, "w1               s3               virt2            TRANSVERSE   0.51 ",
                 f"w1               s3               virt2            TRANSVERSE   {site['weir_crest_m']} ")
    text = _swap(text, "p7               CIRCULAR     0.1472", f"p7               CIRCULAR     {p7_d}")
    text = _swap(text, "s6               418.44 ", f"s6               {site['basement_floor_m']} ")
    # The s6 curve ends at 0.03 m and SWMM extrapolates the last segment, so the basement area kept growing
    # (about 170 m2 at 0.12 m). The FloodX technical notes give a constant 43 m2; hold it flat above 0.03 m.
    text = _swap(text, "storage_s6                  0.03       43.26\n",
                 "storage_s6                  0.03       43.26\nstorage_s6                  1.0        43.26\n")

    if path_mode == "door":
        text = _swap(text, "r5               s6               m3               BOTTOM       0 ",
                     f"r5               s6               m3               BOTTOM       {fill['r5_closed_offset_m']} ")
    if path_mode in ("door", "both"):
        crest = max(0.0, site["door_threshold_m"] - SURFACE_INVERT_M)
        text = _swap(text, "w3               v6               s5",
                     f"door             {SURFACE_NODE}               s6               TRANSVERSE   {crest:.3f}      {fill['door_cd']}        NO       0        0          YES\n"
                     "w3               v6               s5")
        text = _swap(text, "w3               RECT_OPEN",
                     f"door             RECT_OPEN    {fill['door_max_head_m']}                {fill['door_width_m']}            0          0          1\n"
                     "w3               RECT_OPEN")

    inp = out_dir / "model.inp"
    inp.write_text(Template(text).substitute(fill))
    return inp


def _swap(text, old, new):
    if text.count(old) != 1:
        raise ValueError(f"template anchor not found exactly once: {old!r}")
    return text.replace(old, new)


def continuity_error(rpt_path):
    body = Path(rpt_path).read_text().split("Flow Routing Continuity", 1)[1]
    line = [l for l in body.splitlines() if "Continuity Error" in l][0]
    return float(line.split()[-1])


def run(site, params, event, run_id):
    """Run SWMM; write runs/<run_id>/depths.json and return its path."""
    out_dir = RUNS / str(run_id)
    inp = build_inp(site, params, event, out_dir)
    start, end = data.event_window(event)
    t, depth = [], {n: [] for n in NODES}
    t0 = time.time()
    with Simulation(str(inp)) as sim:
        nodes = Nodes(sim)
        sim.step_advance(DT_S)
        for _ in sim:
            t.append(int(round((sim.current_time - start).total_seconds())))
            for n in NODES:
                depth[n].append(round(nodes[n].depth, 5))
    runtime = time.time() - t0
    result = {
        "event": int(event), "dt_s": DT_S, "t": t,
        "depth_m": depth,
        "continuity_error_pct": continuity_error(inp.with_suffix(".rpt")),
        "inputs": {"site_sha": sha(site), "params_sha": sha(params), "template_sha": sha(TEMPLATE)},
        "basement_path": params.get("basement_path", "sewer"),
        "runtime_s": round(runtime, 2),
    }
    path = out_dir / "depths.json"
    path.write_text(json.dumps(result))
    return path


def summary(path):
    d = load_json(path)
    peaks = {n: max(v) * 1000 for n, v in d["depth_m"].items()}
    return (f"event {d['event']} path {d['basement_path']} runtime {d['runtime_s']} s "
            f"continuity {d['continuity_error_pct']}% steps {len(d['t'])}\n  peaks mm: "
            + ", ".join(f"{n} {v:.0f}" for n, v in peaks.items()))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--event", type=int, required=True)
    ap.add_argument("--params", default=str(PARAMS_JSON))
    ap.add_argument("--site", default=str(SITE_JSON))
    ap.add_argument("--run-id")
    a = ap.parse_args()
    params = load_json(a.params)
    run_id = a.run_id or f"event{a.event}_{params.get('basement_path', 'sewer')}"
    print(summary(run(load_json(a.site), params, a.event, run_id)))
    print(f"run dir: {RUNS / run_id}")


if __name__ == "__main__":
    main()
