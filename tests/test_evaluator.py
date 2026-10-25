"""Evaluator: a perfect model scores zero; onset detection on toy series."""
import json

import numpy as np
import pytest

from backend import evaluator
from backend.config import DT_S, EVALUATION, WET_M, WET_SUSTAIN_S


@pytest.mark.parametrize("event", [20, 32])
def test_score_of_measured_gauge_is_zero(event, tmp_path):
    if not (EVALUATION / f"{event}_s6.txt").exists():
        pytest.skip("gauge files not staged")
    from backend import data
    start, end = data.event_window(event)
    t = np.arange(0, int((end - start).total_seconds()) + 1, DT_S, dtype=float)
    obs = {g: evaluator.load_gauge(event, g, t) for g in ("s3", "s6")}
    ok = ~np.isnan(obs["s3"]) & ~np.isnan(obs["s6"])
    t = t[ok]
    depths = {"event": event, "dt_s": DT_S, "t": t.astype(int).tolist(),
              "depth_m": {g: obs[g][ok].tolist() for g in obs} | {"m2": [0.0] * len(t), "m3": [0.0] * len(t)}}
    p = tmp_path / "depths.json"
    p.write_text(json.dumps(depths))
    s = evaluator.score(event, p)
    for g in ("s3", "s6"):
        assert s[g]["mae_m"] == pytest.approx(0, abs=1e-9)
        assert s[g]["peak_err_m"] == pytest.approx(0, abs=1e-9)
    assert s["s6"]["obs_wet"] and s["s6"]["model_wet"]
    assert s["s6"]["onset_err_s"] == 0
    assert s["basement_wet_match"]


def test_score_detects_an_offset(tmp_path):
    event = 20
    if not (EVALUATION / f"{event}_s6.txt").exists():
        pytest.skip("gauge files not staged")
    t = np.arange(0, 1200, DT_S, dtype=float)
    obs = {g: np.nan_to_num(evaluator.load_gauge(event, g, t)) for g in ("s3", "s6")}
    depths = {"t": t.astype(int).tolist(), "depth_m": {g: (obs[g] + 0.01).tolist() for g in obs}}
    p = tmp_path / "depths.json"
    p.write_text(json.dumps(depths))
    s = evaluator.score(event, p)
    assert s["s3"]["mae_m"] == pytest.approx(0.01, abs=1e-6)
    assert s["s6"]["peak_err_m"] == pytest.approx(0.01, abs=1e-6)


def test_onset_requires_a_sustained_crossing():
    need = int(round(WET_SUSTAIN_S / DT_S))
    t = np.arange(0, 200, DT_S, dtype=float)
    d = np.zeros_like(t)
    d[2] = 0.05                               # one-sample spike: ignored
    d[8:8 + need] = WET_M * 2                 # sustained: counts
    assert evaluator.onset_s(t, d) == t[8]


def test_onset_none_when_dry_or_at_threshold():
    t = np.arange(0, 200, DT_S, dtype=float)
    assert evaluator.onset_s(t, np.zeros_like(t)) is None
    assert evaluator.onset_s(t, np.full_like(t, WET_M)) is None      # strictly above WET_M


def test_onset_treats_gaps_as_dry():
    need = int(round(WET_SUSTAIN_S / DT_S))
    t = np.arange(0, 200, DT_S, dtype=float)
    d = np.full_like(t, 0.02)
    d[::need] = np.nan                         # a gap inside every window
    if need > 1:
        assert evaluator.onset_s(t, d) is None
