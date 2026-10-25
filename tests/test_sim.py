"""SWMM runs for the calibration (20) and dry check (21) events.

Numbers measured on 2026-10-25 with the untuned template (site/site.json, default knobs):
  event 20 sewer: s6 peak ~70 mm (gauge ~27 mm), continuity ~1.4 %
  event 20 door:  s6 peak 0 mm; s4 surface peaks ~13 mm, below the 40 mm door crest
  event 21 sewer: s6 peak ~54 mm on the dry check event (the gauge stays dry)
  event 21 door:  s6 peak 0 mm
These record current behaviour. They are not a claim that the model is right.
"""
import json
import math

import pytest
from pyswmm import Links, Simulation

from backend import sim
from backend.config import SITE_JSON

SITE = json.loads(SITE_JSON.read_text())
CASES = [(e, p) for e in (20, 21) for p in ("sewer", "door")]


@pytest.fixture(scope="module")
def runs(tmp_path_factory):
    root = tmp_path_factory.mktemp("runs")
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(sim, "RUNS", root)
        out = {}
        for event, path in CASES:
            p = sim.run(SITE, {"basement_path": path, "weir_cd": None, "orifice_cd": None}, event, f"t{event}_{path}")
            out[(event, path)] = json.loads(p.read_text())
    return out


def link_peaks(event, path, tmp_path, names=("r5", "door")):
    inp = sim.build_inp(SITE, {"basement_path": path}, event, tmp_path / f"{event}_{path}")
    peaks = {}
    with Simulation(str(inp)) as s:
        links = Links(s)
        present = [n for n in names if any(l.linkid == n for l in links)]
        peaks = {n: 0.0 for n in present}
        for _ in s:
            for n in present:
                peaks[n] = max(peaks[n], abs(links[n].flow))
    return peaks


@pytest.mark.parametrize("case", CASES, ids=lambda c: f"{c[0]}-{c[1]}")
def test_depths_are_finite_and_complete(runs, case):
    d = runs[case]
    n = len(d["t"])
    assert n > 50
    assert d["t"] == sorted(d["t"])
    for node in ("s3", "s6", "m2", "m3"):
        v = d["depth_m"][node]
        assert len(v) == n
        assert all(math.isfinite(x) and x >= 0 for x in v), node
    assert set(d["inputs"]) == {"site_sha", "params_sha", "template_sha"}


@pytest.mark.parametrize("case", CASES, ids=lambda c: f"{c[0]}-{c[1]}")
def test_continuity_error_under_5_pct(runs, case):
    assert abs(runs[case]["continuity_error_pct"]) < 5


@pytest.mark.parametrize("event", [20, 21])
def test_door_mode_keeps_sewer_orifice_closed(event, tmp_path):
    door = link_peaks(event, "door", tmp_path)
    sewer = link_peaks(event, "sewer", tmp_path)
    assert "door" in door and "door" not in sewer
    assert door["r5"] < 1e-6
    assert sewer["r5"] > 1e-3            # in sewer mode r5 does carry flow, so the check above means something


def test_door_mode_inp_raises_r5_and_adds_door(tmp_path):
    inp = sim.build_inp(SITE, {"basement_path": "door"}, 20, tmp_path).read_text()
    r5 = [l.split() for l in inp.splitlines() if l.startswith("r5 ") and "BOTTOM" in l][0]
    assert float(r5[4]) >= 10
    assert any(l.startswith("door ") and "TRANSVERSE" in l for l in inp.splitlines())


def test_unknown_basement_path_rejected(tmp_path):
    with pytest.raises(ValueError):
        sim.build_inp(SITE, {"basement_path": "roof"}, 20, tmp_path)


def test_same_inputs_give_same_depths(runs, tmp_path, monkeypatch):
    monkeypatch.setattr(sim, "RUNS", tmp_path)
    p = sim.run(SITE, {"basement_path": "sewer", "weir_cd": None, "orifice_cd": None}, 21, "again")
    assert json.loads(p.read_text())["depth_m"] == runs[(21, "sewer")]["depth_m"]


# Documented behaviour, not correctness ----------------------------------------

def peak_mm(d, node):
    return max(d["depth_m"][node]) * 1000


def test_dry_check_currently_fails_in_sewer_mode(runs):
    """The untuned sewer model wets the basement on dry event 21 (Gate A). Calibration must fix this."""
    assert 30 < peak_mm(runs[(21, "sewer")], "s6") < 80


def test_door_mode_is_dry_on_both_events(runs):
    """With the door crest 40 mm above s4 and s4 peaking near 13 mm, the door path never fills the basement.
    So 'door' passes the dry check trivially but cannot reproduce event 20's wet basement."""
    assert peak_mm(runs[(21, "door")], "s6") == 0
    assert peak_mm(runs[(20, "door")], "s6") == 0
    crest_mm = (SITE["door_threshold_m"] - sim.SURFACE_INVERT_M) * 1000
    assert peak_mm(runs[(20, "door")], "s4") < crest_mm


def test_event20_sewer_overpredicts_basement(runs):
    assert 50 < peak_mm(runs[(20, "sewer")], "s6") < 100
