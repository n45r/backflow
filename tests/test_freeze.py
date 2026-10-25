import json

import pytest

from backend import freeze


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setattr(freeze, "FROZEN", tmp_path / "frozen")
    tpl = tmp_path / "template.inp"
    tpl.write_text("[TITLE]\nx\n")
    monkeypatch.setattr(freeze, "TEMPLATE", tpl)
    scene = tmp_path / "scene.js"
    scene.write_text("export default function build(THREE, root, site) { return {}; }\n")
    site = {"weir_crest_m": 0.51, "basement_floor_m": 418.44}
    params = {"basement_path": "sewer", "weir_cd": 1.6, "orifice_cd": 0.6}
    return tmp_path, tpl, scene, site, params


def test_freeze_writes_record_and_verifies(env):
    root, tpl, scene, site, params = env
    rec = freeze.freeze(scene, site, params, "informed")
    path = root / "frozen" / "informed.json"
    assert path.exists() and json.loads(path.read_text())["commitment"] == rec["commitment"]
    assert len(rec["commitment"]) == 12
    for k in ("scene_sha256", "site_sha256", "params_sha256", "template_sha256"):
        assert len(rec[k]) == 64
    assert freeze.verify("informed")


def test_commitment_is_independent_of_key_order(env):
    _, _, scene, site, params = env
    a = freeze.freeze(scene, site, params, "a")
    b = freeze.freeze(scene, dict(reversed(list(site.items()))), dict(reversed(list(params.items()))), "b")
    assert a["commitment"] == b["commitment"]


@pytest.mark.parametrize("tamper", ["scene", "template", "params", "site", "commitment"])
def test_verify_fails_after_any_change(env, tamper):
    root, tpl, scene, site, params = env
    freeze.freeze(scene, site, params, "x")
    path = root / "frozen" / "x.json"
    if tamper == "scene":
        scene.write_text(scene.read_text() + "// moved the door\n")
    elif tamper == "template":
        tpl.write_text(tpl.read_text() + "; edit\n")
    else:
        rec = json.loads(path.read_text())
        if tamper == "params":
            rec["params"]["weir_cd"] = 1.7
        elif tamper == "site":
            rec["site"]["weir_crest_m"] = 0.52
        else:
            rec["commitment"] = "000000000000"
        path.write_text(json.dumps(rec))
    assert not freeze.verify("x")


def test_cannot_refreeze_a_name_with_different_inputs(env):
    _, _, scene, site, params = env
    first = freeze.freeze(scene, site, params, "blind")
    assert freeze.freeze(scene, site, params, "blind")["commitment"] == first["commitment"]
    with pytest.raises(FileExistsError):
        freeze.freeze(scene, site, {**params, "weir_cd": 2.0}, "blind")


def test_verify_missing_and_bad_names(env):
    assert not freeze.verify("never_frozen")
    with pytest.raises(ValueError):
        freeze.freeze(env[2], env[3], env[4], "../escape")


def test_verify_fails_when_scene_file_is_gone(env):
    _, _, scene, site, params = env
    freeze.freeze(scene, site, params, "gone")
    scene.unlink()
    assert not freeze.verify("gone")
