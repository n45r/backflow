"""Argon as the engineer: it watches the real flood beside a video of the simulation, reads the plan and the
model file, diagnoses what is wrong, and writes new physical settings. Then the held-out flood is scored.

Argon sees: real camera video, rendered simulation video (water placed by SWMM), the site plan PDF and the
model input file (structure, settings and the known inflow). It never sees simulation output numbers or gauges.
"""
import argparse
import json
import re
import time
from pathlib import Path

from google.genai import types

from backend import argon, evaluator, sim
from backend.config import RUNS, SPLIT
from backend.holdout import untuned_params

ROOT = Path(__file__).resolve().parent.parent
PLAN = ROOT / "data" / "raw" / "docs_scene" / "plan_setup.pdf"

BRIEF = """You are a drainage engineer calibrating an EPA SWMM model of the FloodX test site (a staged flood at a Swiss training facility).

You get:
1. A side-by-side video of flood event {event}: left is the real basement camera (camera 5, night infrared), right is our 3D render of the SWMM simulation from the same viewpoint and the same clock. Water in the render is placed only by SWMM's computed depths. Watch the whole video.
2. The 1:50 site plan (PDF).
3. The SWMM input file used for that simulation (network, settings, and the measured inflow, which is a known input).

You never see simulation output numbers or any water-level sensor.

Task: diagnose why the simulated flood differs from the real one (timing, how much water, where it comes from, how fast it drains), using the network and the plan to reason about the mechanism. Then choose new values for these settings, each within its bounds:
{bounds}
and choose "basement_path": one of "sewer" (water rises through the floor drain from the sewer), "door" (surface water over the door threshold), "both".
Also you may set "p7_diameter_m" in [0.05, 0.15] (effective diameter of pipe p7, sewer to the basement drain manhole m3).

Reply with JSON only:
{{"diagnosis": ["what differs and when, with video times"], "mechanism": "one or two sentences",
 "changes": {{"setting": value}}, "basement_path": "...", "p7_diameter_m": value,
 "expected_effect": "what the new settings should change in the video", "confidence": 0.0-1.0}}"""


def _upload(path):
    c = argon.client()
    f = c.files.upload(file=str(path))
    while f.state.name == "PROCESSING":
        time.sleep(3)
        f = c.files.get(name=f.name)
    if f.state.name != "ACTIVE":
        raise RuntimeError(f"upload failed: {f.state.name}")
    return f


def side_by_side_video(name, params, event, out_name):
    from scripts.side_by_side import make
    depths = sim.run(json.loads((RUNS / "loop" / name / "frozen.json").read_text())["site"], params, event, f"eng_{out_name}")
    return make(name, "simulation", event, 120, 720, 6, out_name, depths=str(depths), fps=1)


def engineer(name, params, event):
    vid = side_by_side_video(name, params, event, f"eng_{event}_{abs(hash(json.dumps(params, sort_keys=True))) % 10**8}.mp4")
    site = json.loads((RUNS / "loop" / name / "frozen.json").read_text())["site"]
    inp = sim.build_inp(site, params, event, RUNS / "engineer" / "inp")
    bounds = "\n".join(f"- {k}: [{lo}, {hi}]" for k, (lo, hi) in sim.OVERRIDE_BOUNDS.items())
    f = _upload(vid)
    parts = [types.Part.from_uri(file_uri=f.uri, mime_type=f.mime_type), argon._file_part(PLAN),
             types.Part.from_text(text="SWMM input file:\n" + Path(inp).read_text()[:200000]),
             types.Part.from_text(text=BRIEF.format(event=event, bounds=bounds))]
    reply, usage, secs = argon.ask(parts, thinking="high", timeout_s=900)
    m = re.search(r"\{.*\}", reply, re.S)
    res = json.loads(m.group(0)) if m else {"raw": reply}
    new = {"basement_path": res.get("basement_path") if res.get("basement_path") in sim.BASEMENT_PATHS else params.get("basement_path", "sewer"),
           "overrides": {k: v for k, v in (res.get("changes") or {}).items() if k in sim.OVERRIDE_BOUNDS}}
    if res.get("p7_diameter_m") is not None:
        new["p7_diameter_m"] = min(max(float(res["p7_diameter_m"]), 0.05), 0.15)
    return {"video": str(vid), "reply": res, "params": new, "usage": usage, "seconds": secs}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--name", default="calib_v3", help="loop run whose scene and patch are used for renders")
    ap.add_argument("--rounds", type=int, default=2)
    a = ap.parse_args()
    out = RUNS / "engineer"
    out.mkdir(parents=True, exist_ok=True)
    cal, hold = SPLIT["calibrate"], SPLIT["holdout"]
    params = untuned_params()
    log = []
    for n in range(a.rounds):
        r = engineer(a.name, params, cal)
        params = r["params"]
        log.append(r)
        (out / "log.json").write_text(json.dumps(log, indent=1, default=str))
        print("round", n, r["seconds"], "s", json.dumps(r["reply"].get("mechanism")), json.dumps(params), flush=True)
    site = json.loads((RUNS / "loop" / a.name / "frozen.json").read_text())["site"]
    for label, p in (("blind", untuned_params()), ("engineer", params)):
        d = sim.run(site, p, hold, f"eng_hold_{label}")
        s = evaluator.score(hold, d)["s6"]
        print(label, "held-out basement mae mm", round(s["mae_m"] * 1000, 1), "peak err mm", round(s["peak_err_m"] * 1000, 1),
              "onset err s", s.get("onset_err_s"), flush=True)
    (out / "final.json").write_text(json.dumps({"params": params}, indent=1))


if __name__ == "__main__":
    main()
