"""Control experiment: replay the loop's candidate search with fixed choosers instead of Argon.

Same candidates, same step rule (halve the step when the current set wins), same number of rounds.
Each final parameter set is scored on the held-out event. The oracle picks with event 32's gauges (an upper bound,
it uses data the loop must not see). Nothing here calls the model.
"""
import json
import random
from pathlib import Path

from backend import evaluator, sim
from backend.config import SPLIT
from backend.holdout import untuned_params
from backend.loop import KNOBS, numeric_knobs

ROOT = Path(__file__).resolve().parent.parent
EFFECTS = json.loads((ROOT / "site" / "knob_effects.json").read_text())["less_water"]
SITE = json.loads((ROOT / "runs" / "loop" / "calib_video" / "frozen.json").read_text())["site"]
CAL, HOLD = SPLIT["calibrate"], SPLIT["holdout"]


def candidates(params, step):
    less, more = dict(params), dict(params)
    for k in numeric_knobs():
        lo, hi = KNOBS[k]
        v = params[k]
        up, down = v + step * (hi - v), v - step * (v - lo)
        less[k], more[k] = (up, down) if EFFECTS.get(k, 1) > 0 else (down, up)
    return {"A": dict(params), "B": less, "C": more}


def cal_mae(params, tag):
    return evaluator.score(CAL, sim.run(SITE, params, CAL, tag))["s6"]["mae_m"]


def search(chooser, rounds, tag):
    params, step = dict(untuned_params(), basement_path="sewer"), 0.4
    picks = []
    for n in range(rounds):
        c = candidates(params, step)
        w = chooser(c, n, tag)
        picks.append(w)
        if w == "A":
            step *= 0.5
        params = c[w]
    s = evaluator.score(HOLD, sim.run(SITE, params, HOLD, f"ctl_{tag}"))["s6"]
    return {"policy": tag, "picks": "".join(picks), "mae_mm": round(s["mae_m"] * 1000, 1),
            "peak_err_mm": round(s["peak_err_m"] * 1000, 1), "wet": s["model_wet"]}


def oracle(c, n, tag):
    return min(c, key=lambda L: cal_mae(c[L], f"orc_{tag}_{n}_{L}"))


def oracle_peak(c, n, tag):
    def err(L):
        s = evaluator.score(CAL, sim.run(SITE, c[L], CAL, f"orp_{tag}_{n}_{L}"))["s6"]
        return abs(s["peak_err_m"])
    return min(c, key=err)


def main():
    rounds = 4
    rows = [search(lambda c, n, t: "B", rounds, "always_less"),
            search(lambda c, n, t: "C", rounds, "always_more"),
            search(lambda c, n, t: "A", rounds, "never_move"),
            search(oracle, rounds, "oracle_gauges_mean"),
            search(oracle_peak, rounds, "oracle_gauges_peak")]
    for seed in range(8):
        rng = random.Random(seed)
        rows.append(search(lambda c, n, t, r=rng: r.choice("ABC"), rounds, f"random_{seed}"))
    argon = json.loads((ROOT / "runs" / "reveal" / "calib_video.json").read_text())["gauges"]["s6"]["informed"]
    rows.append({"policy": "argon_video (calib_video)", "picks": "BACB", "mae_mm": round(argon["mae_m"] * 1000, 1),
                 "peak_err_mm": round(argon["peak_err_m"] * 1000, 1), "wet": argon["model_wet"]})
    out = ROOT / "docs" / "gates" / "control_policies.json"
    out.write_text(json.dumps(rows, indent=1))
    for r in rows:
        print(f"{r['policy']:<28} {r['picks']:<6} mae {r['mae_mm']:>6} mm  peak {r['peak_err_mm']:>7} mm  wet {r['wet']}")


if __name__ == "__main__":
    main()
