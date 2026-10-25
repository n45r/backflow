"""Run one SWMM model and summarise it.

Usage: python3 run_swmm.py <model.inp> [label]
Prints a JSON summary and appends it to runs_log.jsonl next to this script.
"""
import json
import os
import sys
import time
from pathlib import Path

from pyswmm import Nodes, Simulation

NODES = ("s3", "s6", "m2", "m3")
DT_S = 10
WET_M = 0.005
WET_SUSTAIN_S = 30


def field(inp_text, section, name, idx):
    inside = False
    for line in inp_text.splitlines():
        s = line.strip()
        if s.startswith("["):
            inside = s.upper() == f"[{section}]"
            continue
        if inside and s and not s.startswith(";"):
            parts = s.split()
            if parts[0] == name:
                return float(parts[idx])
    return None


def continuity_error(rpt):
    body = rpt.read_text().split("Flow Routing Continuity", 1)[1]
    line = [l for l in body.splitlines() if "Continuity Error" in l][0]
    return float(line.split()[-1])


def onset(t, series, level, sustain_s):
    n = max(1, sustain_s // DT_S + 1)
    for i in range(len(t)):
        win = series[i:i + n]
        if len(win) == n and all(v > level for v in win):
            return t[i]
    return None


def main():
    inp = Path(sys.argv[1]).resolve()
    label = sys.argv[2] if len(sys.argv) > 2 else inp.parent.name
    text = inp.read_text()
    os.chdir(inp.parent)
    t, depth = [], {n: [] for n in NODES}
    t0 = time.time()
    with Simulation(str(inp)) as sim:
        nodes = Nodes(sim)
        sim.step_advance(DT_S)
        start = sim.start_time
        for _ in sim:
            t.append(int(round((sim.current_time - start).total_seconds())))
            for n in NODES:
                depth[n].append(round(nodes[n].depth, 5))
    crest = field(text, "WEIRS", "w1", 4)
    out = {
        "label": label,
        "inp": inp.name,
        "orifice_r5_cd": field(text, "ORIFICES", "r5", 5),
        "weir_w1_cd": field(text, "WEIRS", "w1", 5),
        "runtime_s": round(time.time() - t0, 2),
        "continuity_error_pct": continuity_error(inp.with_suffix(".rpt")),
        "peak_mm": {n: round(max(v) * 1000, 1) for n, v in depth.items()},
        "basement_wet_onset_s": onset(t, depth["s6"], WET_M, WET_SUSTAIN_S),
        "pond_overflow_onset_s": onset(t, depth["s3"], crest, 0),
        "t": t,
        "depth_m": depth,
    }
    (inp.parent / "depths.json").write_text(json.dumps(out))
    brief = {k: v for k, v in out.items() if k not in ("t", "depth_m")}
    with open(Path(__file__).resolve().parent / "runs_log.jsonl", "a") as fh:
        fh.write(json.dumps(brief) + "\n")
    print(json.dumps(brief, indent=1))


if __name__ == "__main__":
    main()
