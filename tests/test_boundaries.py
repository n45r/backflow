"""Honesty audit: the loop side never touches gauges, and the scene cannot place water."""
import ast
import re
import sys
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
LOOP_SIDE = ["backend/loop.py", "backend/argon.py", "backend/render.py", "backend/contact.py",
             "backend/frames.py", "backend/timeline.py", "backend/baseline.py"]
LOOP_SIDE += [str(p.relative_to(ROOT)) for p in sorted((ROOT / "workers").glob("*.py"))]
LOOP_SIDE = [p for p in LOOP_SIDE if (ROOT / p).exists()]
# Text that only appears when code reaches for gauge data.
FORBIDDEN_TEXT = ["evaluator", "evaluation", "EVALUATION", "GAUGE_SOURCES", "gauge_path", "load_gauge",
                  "s3_h_us_maxbotix", "s6_h_us_maxbotix", "maxbotix"]


def backend_imports(path):
    """Backend module names imported by a file (handles `from . import x`, `from .x import`, `backend.x`)."""
    tree = ast.parse((ROOT / path).read_text())
    in_backend = Path(path).parts[0] == "backend"
    out = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                if a.name.startswith("backend."):
                    out.add(a.name.split(".")[1])
        elif isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            if node.level and in_backend:
                if mod:
                    out.add(mod.split(".")[0])
                else:
                    out.update(a.name for a in node.names)
            elif mod == "backend":
                out.update(a.name for a in node.names)
            elif mod.startswith("backend."):
                out.add(mod.split(".")[1])
    return {m for m in out if (ROOT / "backend" / f"{m}.py").exists()}


def import_closure(path):
    seen, todo = set(), [path]
    while todo:
        for m in backend_imports(todo.pop()):
            if m not in seen:
                seen.add(m)
                todo.append(f"backend/{m}.py")
    return seen


def test_audit_covers_the_loop():
    assert "backend/loop.py" in LOOP_SIDE and "backend/argon.py" in LOOP_SIDE
    assert len(LOOP_SIDE) >= 6


@pytest.mark.parametrize("path", LOOP_SIDE)
def test_loop_side_never_reaches_the_evaluator(path):
    closure = import_closure(path)
    assert "evaluator" not in closure, f"{path} imports backend.evaluator (directly or through {sorted(closure)})"
    assert "reveal" not in closure, f"{path} imports backend.reveal, which reads gauges"


@pytest.mark.parametrize("path", LOOP_SIDE)
def test_loop_side_source_has_no_gauge_references(path):
    text = (ROOT / path).read_text()
    hits = [w for w in FORBIDDEN_TEXT if w in text]
    assert not hits, f"{path} mentions {hits}"


def test_closure_detector_is_not_vacuous():
    # reveal.py legitimately reads gauges; the detector must see that.
    assert "evaluator" in import_closure("backend/reveal.py")
    assert "sim" in import_closure("backend/loop.py")


def test_simulation_inputs_do_not_mention_gauges():
    # sim and data feed the loop; they must not hold gauge names either.
    for path in ("backend/sim.py", "backend/data.py"):
        text = (ROOT / path).read_text()
        assert not [w for w in FORBIDDEN_TEXT if w in text], path


def test_server_does_not_serve_the_evaluation_folder():
    text = (ROOT / "backend/server.py").read_text()
    mounts = re.findall(r"app\.mount\(([^\n]+)\)", text)
    assert mounts
    assert not any("evaluation" in m.lower() for m in mounts)


# loop.clamp ------------------------------------------------------------------

@pytest.fixture(scope="module")
def loop_mod():
    """Import backend.loop with argon replaced, so no model client can be built."""
    stub = types.ModuleType("backend.argon")

    def refuse(*a, **k):
        raise AssertionError("tests must not call the model")

    stub.critique = stub.patch_scene = stub.generate_scene = refuse
    saved = {k: sys.modules.get(k) for k in ("backend.argon", "backend.loop")}
    sys.modules["backend.argon"] = stub
    sys.modules.pop("backend.loop", None)
    import backend
    had = getattr(backend, "argon", None)
    backend.argon = stub
    import backend.loop as loop
    yield loop
    for k, v in saved.items():
        if v is None:
            sys.modules.pop(k, None)
        else:
            sys.modules[k] = v
    if had is not None:
        backend.argon = had


def test_clamp_drops_unknown_knobs(loop_mod):
    out = loop_mod.clamp({"weir_cd": 1.5, "basement_floor_m": 417.0, "door_threshold_m": 0.0, "pipe_cd": 9})
    assert out == {"weir_cd": 1.5}


def test_clamp_limits_numeric_knobs_to_bounds(loop_mod):
    lo_w, hi_w = loop_mod.KNOBS["weir_cd"]
    lo_o, hi_o = loop_mod.KNOBS["orifice_cd"]
    assert loop_mod.clamp({"weir_cd": 50})["weir_cd"] == hi_w
    assert loop_mod.clamp({"weir_cd": -3})["weir_cd"] == lo_w
    assert loop_mod.clamp({"orifice_cd": 2.0})["orifice_cd"] == hi_o
    assert loop_mod.clamp({"orifice_cd": 0.0})["orifice_cd"] == lo_o
    assert loop_mod.clamp({"orifice_cd": "0.5"})["orifice_cd"] == 0.5


def test_clamp_rejects_unknown_basement_path(loop_mod):
    assert loop_mod.clamp({"basement_path": "roof"}) == {}
    assert loop_mod.clamp({"basement_path": "door"}) == {"basement_path": "door"}


def test_at_most_three_knobs(loop_mod):
    assert set(loop_mod.KNOBS) == {"basement_path", "weir_cd", "orifice_cd"}


def test_clamp_rejects_nan(loop_mod):
    out = loop_mod.clamp({"weir_cd": float("nan")})
    assert "weir_cd" not in out or out["weir_cd"] == out["weir_cd"]


def test_clamp_drops_non_numeric_values(loop_mod):
    assert loop_mod.clamp({"weir_cd": "high", "orifice_cd": None}) == {}


# scene contract --------------------------------------------------------------

HARNESS = (ROOT / "web/harness.js").read_text()


def test_harness_calls_build_with_site_only():
    calls = re.findall(r"mod\.default\(([^)]*)\)", HARNESS)
    assert calls == ["THREE, sceneRoot, site"], calls


def test_load_scene_takes_url_and_site_only():
    sig = re.search(r"window\.loadScene\s*=\s*async\s+function\s*\(([^)]*)\)", HARNESS)
    assert sig and [a.split("=")[0].strip() for a in sig.group(1).split(",")] == ["url", "site"]


def test_depths_never_reach_the_scene_module():
    body = HARNESS.split("window.loadScene", 1)[1].split("window.loadDepths", 1)[0]
    assert "depths" not in body
    # depths are only read by the harness's own water code
    assert "spec.depth" not in HARNESS and "spec.setDepth" not in HARNESS


def test_renderer_passes_site_not_depths_to_load_scene():
    text = (ROOT / "backend/render.py").read_text()
    calls = re.findall(r'evaluate\("async \(\[u, s\]\) => \{ await window\.loadScene\(u, s\); \}", \[([^\]]*)\]\)', text)
    assert calls == ["url, self.site"], calls


@pytest.mark.parametrize("scene", sorted((ROOT / "web/scene").glob("*.js")), ids=lambda p: p.name)
def test_scene_modules_cannot_fetch_or_reach_globals(scene):
    text = scene.read_text()
    code = re.sub(r"//[^\n]*|/\*.*?\*/", "", text, flags=re.S)
    banned = [r"\bfetch\s*\(", r"XMLHttpRequest", r"\bimport\s*\(", r"^\s*import\s", r"\bwindow\b",
              r"\bdocument\b", r"globalThis", r"WebSocket", r"\beval\s*\(", r"new\s+Function"]
    hits = [b for b in banned if re.search(b, code, flags=re.M)]
    assert not hits, f"{scene.name}: {hits}"
