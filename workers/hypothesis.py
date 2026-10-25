"""Hypothesis workers: one Managed Agents sandbox per basement-entry hypothesis.

Each sandbox gets the calibration and dry-check SWMM models for its hypothesis,
a runner script and the landmark targets from the video timeline. It tunes the
two allowed coefficients and writes work/results.json, which we download.

    .venv/bin/python -m workers.hypothesis --event 20 --dry 21 \
        --targets '{"basement_wet_onset_s": 300}' --name test
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import certifi

os.environ.setdefault("SSL_CERT_FILE", certifi.where())

from backend import sim  # noqa: E402
from backend.config import RUNS, SITE_JSON, SPLIT  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import managed_agent_probe as ma  # noqa: E402

HYPOTHESES = {
    "sewer": "The basement wets through its floor drain: sewer water backs up from manhole m3 "
             "through orifice r5 into the basement (node s6). The door path is absent.",
    "door": "The basement wets over the door threshold: surface water at s4 spills over the "
            "door weir into the basement (node s6). The sewer path r5 is closed (raised out of reach).",
    "both": "The basement wets by both paths: sewer backflow through orifice r5 and surface "
            "water over the door threshold from s4.",
}
KNOBS = {"orifice_cd": (0.2, 0.8), "weir_cd": (1.1, 2.1)}
MAX_RUNS = 6
DRY_LIMIT_MM = 5.0
CONTINUITY_LIMIT_PCT = 5.0
ARGON = {"type": "antigravity", "model": "gemini-4-argon"}
RUNNER = Path(__file__).resolve().parent / "sandbox_runner.py"
WORKERS_DIR = RUNS / "workers"


def _model_files(site, path_mode, event, tag, tmp):
    inp = sim.build_inp(site, {"basement_path": path_mode}, event, Path(tmp) / tag)
    text = re.sub(r'FILE\s+"[^"]*"', 'FILE "forcing.txt"', inp.read_text())
    if 'FILE "forcing.txt"' not in text:
        raise RuntimeError("forcing file reference not found in the .inp")
    return {f"work/{tag}/model.inp": text,
            f"work/{tag}/forcing.txt": (inp.parent / "forcing.txt").read_text()}


def _instruction(hyp, targets, event, dry):
    tgt = "\n".join(f"  - {k}: {v}" for k, v in targets.items())
    lo_o, hi_o = KNOBS["orifice_cd"]
    lo_w, hi_w = KNOBS["weir_cd"]
    door_note = ("\nNote: in this hypothesis r5 is closed (its offset is 99 m), so orifice_cd has "
                 "little or no effect. Say so in the report if you see that.\n") if hyp == "door" else ""
    return f"""You are testing one hypothesis about how a basement floods in a field experiment.

Hypothesis "{hyp}": {HYPOTHESES[hyp]}
This basement path is fixed. Do not change it.

Files in the sandbox:
- work/cal/model.inp and work/cal/forcing.txt: SWMM model of calibration event {event}.
- work/dry/model.inp and work/dry/forcing.txt: SWMM model of dry-check event {dry}. In the real dry event the basement stayed dry.
- work/run_swmm.py: runner. Use `python3 work/run_swmm.py work/cal/model.inp cal` (or `work/dry/model.inp dry`).
  It prints a JSON summary: continuity_error_pct, peak_mm per node (s3 pond, s6 basement, m2 and m3 manholes),
  basement_wet_onset_s (first time s6 depth stays above 5 mm for 30 s), pond_overflow_onset_s (first time s3 rises
  above the weir w1 crest), and the knob values it read. It also writes depths.json next to the .inp (node depths
  every 10 s) and appends to work/runs_log.jsonl. If pyswmm is missing, run `pip install pyswmm` first.
- work/targets.json: landmark times in seconds from event start, read from the real video of event {event}:
{tgt}

Allowed knobs (nothing else may change):
1. orifice_cd in [{lo_o}, {hi_o}]: the discharge coefficient of orifice r5. In the [ORIFICES] section, the line starting
   with `r5` has fields: Name FromNode ToNode Type Offset Qcoeff Gated CloseTime. Edit field 6 (Qcoeff, now 0.6).
2. weir_cd in [{lo_w}, {hi_w}]: the discharge coefficient of weir w1. In the [WEIRS] section, the line starting with `w1`
   has fields: Name FromNode ToNode Type CrestHt Qcoeff Gated EndCon EndCoeff Surcharge. Edit field 6 (Qcoeff, now 1.6).
Use the same knob values in both work/cal/model.inp and work/dry/model.inp. Do not edit any other line,
the forcing files, or the runner. Do not use any data other than these files.
{door_note}
Task:
- First run both models with the current values. Then adjust the knobs so the calibration run matches the target
  landmark times as closely as possible, while the dry-check run keeps the basement (s6) peak below {DRY_LIMIT_MM:g} mm,
  and both runs keep |continuity_error_pct| below {CONTINUITY_LIMIT_PCT:g}%.
- You may make at most {MAX_RUNS} calibration runs in total (count each `cal` run; dry-check runs do not count toward
  the limit but run one for every candidate you consider best). Stop early if the fit is good or the hypothesis cannot fit.
- If no allowed values can satisfy the targets and the dry check together, say so; that is a valid result.

Finally write work/results.json with exactly these keys:
{{
  "hypothesis": "{hyp}",
  "best_knobs": {{"orifice_cd": <float>, "weir_cd": <float>}},
  "landmarks_achieved": {{<same keys as targets.json>: <seconds or null>}},
  "landmark_errors_s": {{<key>: <achieved minus target, or null>}},
  "dry_check_peak_mm": <float, s6 peak in the dry run at best knobs>,
  "dry_check_pass": <bool>,
  "continuity_error_pct": {{"cal": <float>, "dry": <float>}},
  "n_cal_runs": <int>,
  "n_dry_runs": <int>,
  "trials": [{{"orifice_cd": .., "weir_cd": .., "landmarks": {{..}}, "dry_peak_mm": <float or null>}}],
  "fits": <bool, true only if every landmark is within 30 s and the dry check passes>,
  "report": "<exactly 3 sentences: what you tried, what fit or failed, and how strong the hypothesis looks>"
}}
Leave the model files at the best knob values when you finish.
"""


def _sources(site, hyp, event, dry, targets, tmp):
    files = {}
    files.update(_model_files(site, hyp, event, "cal", tmp))
    files.update(_model_files(site, hyp, dry, "dry", tmp))
    files["work/run_swmm.py"] = RUNNER.read_text()
    files["work/targets.json"] = json.dumps(targets, indent=1)
    return files


def _new_client():
    with ma._lock:
        return ma.genai.Client(api_key=ma._key())


def _retry(fn, tries=8, wait=5.0):
    for i in range(tries):
        try:
            return fn()
        except Exception:
            if i == tries - 1:
                raise
            time.sleep(wait * (i + 1))


def _attempt(c, prompt, files, agent_config, timeout):
    kw = dict(agent=ma.BASE_AGENT, input=prompt, background=True,
              environment={"type": "remote", "sources": ma.inline(files)})
    if agent_config:
        kw["agent_config"] = agent_config
    t0 = time.time()
    ia = c.interactions.create(**kw)
    while ia.status in ("in_progress", None) and time.time() - t0 < timeout:
        time.sleep(10)
        ia = _retry(lambda: c.interactions.get(id=ia.id))
    r = {"id": ia.id, "status": ia.status, "seconds": round(time.time() - t0, 1),
         "environment_id": getattr(ia, "environment_id", None),
         "output_text": ia.output_text, "usage": ma._usage(ia.usage),
         "errors": [str(e) for e in (ia.errors or [])]}
    if r["status"] != "completed":
        raise RuntimeError(f"status {r['status']}: {r['errors'] or r['output_text']}")
    return r


def _download_json(c, env_id, path):
    raw = _retry(lambda: c.environments.files.download(environment=env_id, path=path), tries=4)
    if hasattr(raw, "read"):
        raw = raw.read()
    if isinstance(raw, str):
        raw = raw.encode()
    return raw.decode()


def run_worker(hyp, site, event, dry, targets, name, timeout=1500):
    t0 = time.time()
    out_dir = WORKERS_DIR / name
    out_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        files = _sources(site, hyp, event, dry, targets, tmp)
    prompt = _instruction(hyp, targets, event, dry)
    attempts = []
    r = None
    c = _new_client()
    for label, cfg in (("gemini-4-argon", ARGON), ("default", None)):
        ta = time.time()
        try:
            r = _attempt(c, prompt, files, cfg, timeout)
            attempts.append({"model": label, "ok": True, "seconds": round(time.time() - ta, 1)})
            break
        except Exception as e:  # fall back to the default model on any failure
            attempts.append({"model": label, "ok": False, "seconds": round(time.time() - ta, 1),
                             "error": str(e)[:500]})
            r = None
    record = {"hypothesis": hyp, "event": event, "dry_event": dry, "targets": targets,
              "attempts": attempts, "model": attempts[-1]["model"] if r else None}
    if r:
        record.update({"interaction_id": r["id"], "environment_id": r["environment_id"],
                       "agent_seconds": r["seconds"], "usage": r["usage"],
                       "output_text": (r["output_text"] or "")[-2000:]})
        try:
            record["results"] = json.loads(_download_json(c, r["environment_id"], "work/results.json"))
        except Exception as e:
            record["results"] = None
            record["results_error"] = str(e)[:500]
        try:
            log = _download_json(c, r["environment_id"], "work/runs_log.jsonl")
            record["runs_log"] = [json.loads(l) for l in log.splitlines() if l.strip()]
        except Exception as e:
            record["runs_log_error"] = str(e)[:300]
    record["wall_seconds"] = round(time.time() - t0, 1)
    (out_dir / f"{hyp}.json").write_text(json.dumps(record, indent=1, default=str))
    return record


def _brief(rec):
    res = rec.get("results") or {}
    log = rec.get("runs_log") or []
    return {
        "model": rec.get("model"),
        "wall_seconds": rec.get("wall_seconds"),
        "tokens": (rec.get("usage") or {}).get("total_tokens"),
        "best_knobs": res.get("best_knobs"),
        "landmarks_achieved": res.get("landmarks_achieved"),
        "dry_check_peak_mm": res.get("dry_check_peak_mm"),
        "continuity_error_pct": res.get("continuity_error_pct"),
        "fits": res.get("fits"),
        "n_cal_runs_reported": res.get("n_cal_runs"),
        "n_cal_runs_logged": sum(1 for x in log if x.get("label") == "cal"),
        "report": res.get("report"),
        "error": rec.get("results_error") or (None if rec.get("model") else rec["attempts"]),
    }


def run_all(event, dry, targets, name, hypotheses=tuple(HYPOTHESES), site=None):
    site = site or json.loads(Path(SITE_JSON).read_text())
    t0 = time.time()
    with ThreadPoolExecutor(max_workers=len(hypotheses)) as pool:
        futs = {h: pool.submit(run_worker, h, site, event, dry, targets, name) for h in hypotheses}
        records = {h: f.result() for h, f in futs.items()}
    summary = {"name": name, "event": event, "dry_event": dry, "targets": targets,
               "wall_seconds": round(time.time() - t0, 1),
               "total_tokens": sum((r.get("usage") or {}).get("total_tokens") or 0 for r in records.values()),
               "workers": {h: _brief(r) for h, r in records.items()}}
    (WORKERS_DIR / name / "summary.json").write_text(json.dumps(summary, indent=1, default=str))
    return summary


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--event", type=int, default=SPLIT["calibrate"])
    ap.add_argument("--dry", type=int, default=SPLIT["dry"])
    ap.add_argument("--targets", required=True, help="JSON dict of landmark times in seconds")
    ap.add_argument("--name", required=True)
    ap.add_argument("--hypotheses", default=",".join(HYPOTHESES))
    a = ap.parse_args()
    summary = run_all(a.event, a.dry, json.loads(a.targets), a.name,
                      tuple(h for h in a.hypotheses.split(",") if h))
    print(json.dumps(summary, indent=1, default=str))


if __name__ == "__main__":
    main()
