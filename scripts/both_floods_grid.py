"""Can one setting of the three knobs fit both event 32 and event 20? Grid search, for two starting states of event 32."""
import itertools
import json
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np

from backend import data, evaluator, sim

ROOT = Path(__file__).resolve().parent.parent
SITE = json.loads((ROOT / "site" / "site.json").read_text())


def one(args):
    p, s5, tag = args
    if s5 is not None:
        base = data.initial_conditions
        def patched(event, base=base, s5=s5):
            ic = base(event)
            if int(event) == 32:
                ic.update({"id_s5": s5, "id_v9": s5, "id_4": s5 + 0.68, "id_9": s5 + 0.68, "id_v8": s5, "id_v7": s5,
                           "id_v4": s5, "id_m3": s5 + 0.5})
            return ic
        data.initial_conditions = patched
    out = {}
    for ev in (32, 20):
        s = evaluator.score(ev, sim.run(SITE, p, ev, f"grid_{tag}_{ev}"))["s6"]
        out[ev] = (s["model_peak_m"] * 1000, s["obs_peak_m"] * 1000, s["mae_m"] * 1000)
    return p, out


def main(s5):
    grid = [{"basement_path": "sewer", "outlet_cd": a, "p7_diameter_m": b, "p3_roughness": c}
            for a, b, c in itertools.product(np.linspace(0.3, 1.0, 6), np.linspace(0.05, 0.15, 6), np.linspace(0.012, 0.03, 4))]
    jobs = [(p, s5, f"{'fix' if s5 is not None else 'orig'}_{i}") for i, p in enumerate(grid)]
    with ProcessPoolExecutor(8) as ex:
        res = list(ex.map(one, jobs))
    def err(o):
        return abs(o[32][0] - o[32][1]) / o[32][1] + abs(o[20][0] - o[20][1]) / o[20][1]
    res.sort(key=lambda r: err(r[1]))
    for p, o in res[:5]:
        print({k: round(v, 3) for k, v in p.items() if k != "basement_path"},
              f"ev32 peak {o[32][0]:.0f}/{o[32][1]:.0f} mm  ev20 peak {o[20][0]:.0f}/{o[20][1]:.0f} mm  mae {o[32][2]:.1f}/{o[20][2]:.1f}")


if __name__ == "__main__":
    main(None if sys.argv[1] == "orig" else float(sys.argv[1]))
