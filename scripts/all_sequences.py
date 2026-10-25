"""Every possible 4-round pick sequence (3^4 = 81), each scored on the held-out flood. Where does Argon's rank?"""
import itertools
import json
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

from backend import evaluator, sim
from scripts.control_policies import candidates, SITE, HOLD
from backend.holdout import untuned_params

ROOT = Path(__file__).resolve().parent.parent


def final_params(seq):
    params, step = dict(untuned_params(), basement_path="sewer"), 0.4
    for w in seq:
        c = candidates(params, step)
        if w == "A":
            step *= 0.5
        params = c[w]
    return params


def score(seq):
    s = evaluator.score(HOLD, sim.run(SITE, final_params(seq), HOLD, f"seq_{seq}"))["s6"]
    return {"seq": seq, "mae_mm": round(s["mae_m"] * 1000, 1), "peak_err_mm": round(s["peak_err_m"] * 1000, 1), "wet": s["model_wet"]}


def main():
    seqs = ["".join(p) for p in itertools.product("ABC", repeat=4)]
    with ProcessPoolExecutor(6) as ex:
        rows = list(ex.map(score, seqs))
    rows.sort(key=lambda r: (not r["wet"], r["mae_mm"]))
    (ROOT / "docs" / "gates" / "all_sequences.json").write_text(json.dumps(rows, indent=1))
    wet = [r for r in rows if r["wet"]]
    rank = next(i for i, r in enumerate(wet) if r["seq"] == "BACB") + 1
    print(f"{len(wet)} of 81 sequences predict the flood; Argon's BACB ranks {rank} among them by mean error")
    for r in rows[:8]:
        print(r)


if __name__ == "__main__":
    main()
