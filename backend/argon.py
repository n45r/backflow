"""Calls to Gemini 4 Argon: scene generation, scene patches and visual critique."""
import fcntl
import json
import os
import pathlib
import re
import time

import certifi

os.environ.setdefault("SSL_CERT_FILE", certifi.where())

from google import genai
from google.genai import types

MODEL = "gemini-4-argon"
ROOT = pathlib.Path(__file__).resolve().parent.parent
CONTRACTS = ROOT / "docs" / "CONTRACTS.md"


KEY_NAMES = ("workshop", "default")
MAX_CONCURRENT_PER_KEY = int(os.environ.get("ARGON_MAX_CONCURRENT", "3"))
LOCK_DIR = ROOT / "runs" / ".argon_slots"
CALL_LOG = ROOT / "runs" / "argon_calls.jsonl"


def _keys():
    keys = {}
    for line in pathlib.Path.home().joinpath("gemini-key.txt").read_text().splitlines():
        name, _, value = line.partition("=")
        if name.strip() in KEY_NAMES and value.strip():
            keys[name.strip()] = value.strip()
    if not keys:
        raise RuntimeError("no keys in ~/gemini-key.txt")
    return keys


_clients = {}


def client(name=None):
    keys = _keys()
    name = name or next(iter(keys))
    if name not in _clients:
        _clients[name] = genai.Client(api_key=keys[name], http_options=types.HttpOptions(timeout=600_000))
    return _clients[name]


class _Slot:
    """Cross-process cap on concurrent calls per key, using file locks."""

    def __init__(self):
        self.fh = None
        self.key = None

    def __enter__(self):
        LOCK_DIR.mkdir(parents=True, exist_ok=True)
        names = list(_keys())
        while True:
            for i in range(MAX_CONCURRENT_PER_KEY):
                for name in names:
                    fh = open(LOCK_DIR / f"{name}.{i}", "w")
                    try:
                        fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
                        self.fh, self.key = fh, name
                        return self
                    except BlockingIOError:
                        fh.close()
            time.sleep(0.5)

    def __exit__(self, *exc):
        fcntl.flock(self.fh, fcntl.LOCK_UN)
        self.fh.close()


def _log(entry):
    CALL_LOG.parent.mkdir(parents=True, exist_ok=True)
    with open(CALL_LOG, "a") as fh:
        fh.write(json.dumps(entry) + "\n")


def _file_part(path):
    path = pathlib.Path(path)
    mime = {".pdf": "application/pdf", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png"}[path.suffix.lower()]
    return types.Part.from_bytes(data=path.read_bytes(), mime_type=mime)


def ask(parts, thinking="high", max_output_tokens=65536, media_resolution=None, attempts=4):
    """One call with a concurrency slot, retries and a log line. Returns (text, usage dict, seconds)."""
    config = types.GenerateContentConfig(
        max_output_tokens=max_output_tokens,
        thinking_config=types.ThinkingConfig(thinking_level=thinking),
        media_resolution=f"MEDIA_RESOLUTION_{media_resolution.upper()}" if media_resolution else None,
    )
    start = time.time()
    last = None
    for attempt in range(attempts):
        with _Slot() as slot:
            t0 = time.time()
            try:
                resp = client(slot.key).models.generate_content(model=MODEL, contents=parts, config=config)
                usage = resp.usage_metadata.model_dump() if resp.usage_metadata else {}
                _log({"t": round(t0), "key": slot.key, "ok": True, "attempt": attempt, "wait_s": round(t0 - start, 1),
                      "call_s": round(time.time() - t0, 1), "out_tokens": usage.get("candidates_token_count")})
                return resp.text or "", usage, round(time.time() - start, 1)
            except Exception as e:
                last = e
                _log({"t": round(t0), "key": slot.key, "ok": False, "attempt": attempt,
                      "call_s": round(time.time() - t0, 1), "error": f"{type(e).__name__}: {str(e)[:200]}"})
        time.sleep(min(60, 4 * 2 ** attempt))
    raise last


def extract_code(text):
    blocks = re.findall(r"```(?:javascript|js)?\n(.*?)```", text, re.S)
    return max(blocks, key=len) if blocks else text


SCENE_BRIEF = """You are writing the 3D scene of a real flood test site, as an ES module for Three.js.

The site: FloodX, an outdoor flood-response training facility in Switzerland (about 24.5 m by 22.7 m). The attached PDF is the 1:50 plan with dimensions in metres and absolute elevations in brackets (metres above sea level). Key parts: storage s3 (the pond, bottom of the plan) with weir w1; channels c1, c3 and c4; storage s4 and manhole m2; the building at the top right with the basement, storage s6, which contains manhole m3 and orifice r5 (a floor drain connected to the sewer through pipe p7); a staircase; curbs 12 cm high. The attached photos are real camera frames with the site dry: camera 5 looks into the basement s6. Camera 1 looks at the pond s3 and weir w1 (if no camera 1 frame is attached, place it from the plan, where s3_cam1_instar is drawn).

Write `export default function build(THREE, root, site)` exactly following this contract (from our CONTRACTS.md):

CONTRACT_PLACEHOLDER

Rules:
- Coordinates in metres. x to the right on the plan, z downward on the plan (toward the bottom edge), y up. Put the origin at the bottom-left corner of the site outline. Use the plan's dimensions and elevations; convert absolute elevations to y = elevation - 419.0.
- Build static geometry only: ground with the real slopes where the plan shows them, the pond basin, weir walls, channels, curbs, manholes (as rims and dark openings), the building walls with a cutaway roof so the basement is visible, the basement floor sloping slightly toward the drain at m3, the staircase, and anything clearly visible in the camera frames (doors, sandbags, cables are optional).
- `site` holds shared values (weir_crest_m, basement_floor_m, door_threshold_m, basement_floor_slope, basement_drain_xy, pond_area_m2); use them where given, otherwise use the plan. Never hardcode a value that site provides.
- Return cameras cam1 and cam5 placed and aimed to match the real frames as closely as you can (position, lookAt, fov in degrees).
- Return water anchors: pond outline polygon and base_y (pond bottom), basement outline polygon, floor_y, slope and drain_xz, manhole_m2 center, radius and base_y. You do not place water and you never receive depths.
- Use only THREE (passed in). No imports, no fetch, no DOM access, no animation loop. Use MeshStandardMaterial with plain colours resembling concrete, grass and metal. Add one hemisphere light and one directional light to root.
- Give every major object a name (mesh.name) like "weir_w1", "basement_floor", "manhole_m3".

Return only the module code in one ```javascript block."""


CRITIQUE_BRIEF = """You are calibrating a flood simulation of the FloodX test site by comparing pictures.

The attached contact sheet has one row per moment of the same flood event. Left: the real camera frame. Right: our 3D render of the simulation from the virtual camera of the same name, at the same moment. Water in the render is placed by the hydraulic simulation (EPA SWMM); you cannot see its numbers and you cannot paint water. You may change only:
- scene geometry and camera alignment (how the site is drawn; this does not change the physics), and
- these physics knobs, within bounds: KNOBS_PLACEHOLDER

Current values: CURRENT_PLACEHOLDER
History of earlier rounds (what was changed and why): HISTORY_PLACEHOLDER

First, for each row, decide whether left and right differ in a way that matters for the flood or the geometry, and say "same" or "different" with the specific visible evidence. Reporting no differences is a valid and common answer; do not propose changes unless a row clearly shows a difference. If every row is "same", return empty issues, an empty scene_patch and empty knob_changes. Then compare left and right row by row. Look at: camera alignment and missing or misplaced structures; when and where water appears; whether the pond spills over the weir at the right time; whether the basement gets wet, when, and how far the wet area spreads; where water enters the basement (through the floor drain from below, or over the door threshold). In night infrared frames, wet concrete is darker and reflective, and water lines show on walls.

Reply with JSON only:
{"rows": [{"label": "...", "verdict": "same|different", "evidence": "..."}],
 "scene_issues": ["..."], "flood_issues": ["..."],
 "scene_patch": "short instruction for the scene author, or empty string",
 "knob_changes": {"name": value},
 "evidence": "which rows show what, in one or two sentences",
 "closer_than_before": true|false|null,
 "confidence": 0.0-1.0}"""


def critique(sheet_path, knobs, current, history):
    text = (CRITIQUE_BRIEF.replace("KNOBS_PLACEHOLDER", json.dumps(knobs))
            .replace("CURRENT_PLACEHOLDER", json.dumps(current))
            .replace("HISTORY_PLACEHOLDER", json.dumps(history) if history else "none"))
    reply, usage, secs = ask([_file_part(sheet_path), types.Part.from_text(text=text)], thinking="high", max_output_tokens=16384, media_resolution="high")
    m = re.search(r"\{.*\}", reply, re.S)
    return {"result": json.loads(m.group(0)) if m else {"raw": reply}, "usage": usage, "seconds": secs}


PATCH_BRIEF = """Below is the current Three.js scene module of the FloodX site, and an instruction from the reviewer who compared renders with real camera frames. Rewrite the module to apply the instruction. Keep the same contract (export default function build(THREE, root, site) returning cameras, water anchors and materials), keep object names, keep everything that was not criticised. Return only the full module in one ```javascript block.

Instruction: INSTRUCTION_PLACEHOLDER"""


def patch_scene(code, instruction, sheet_path, out_path):
    parts = [_file_part(sheet_path),
             types.Part.from_text(text=PATCH_BRIEF.replace("INSTRUCTION_PLACEHOLDER", instruction)),
             types.Part.from_text(text="```javascript\n" + code + "\n```")]
    text, usage, secs = ask(parts, thinking="low")
    new = extract_code(text)
    pathlib.Path(out_path).write_text(new)
    return {"path": str(out_path), "usage": usage, "seconds": secs, "chars": len(new)}


def generate_scene(plan_pdf, frames, site, out_path):
    """Round 0: the full scene in one pass. frames maps camera name to a dry frame path."""
    contract = CONTRACTS.read_text().split("## 3D scene module")[1].split("## Host harness")[0]
    parts = [_file_part(plan_pdf)]
    for cam, path in frames.items():
        parts += [types.Part.from_text(text=f"Real frame from {cam}, site dry:"), _file_part(path)]
    parts.append(types.Part.from_text(text=SCENE_BRIEF.replace("CONTRACT_PLACEHOLDER", contract) + "\n\nsite = " + json.dumps(site)))
    text, usage, secs = ask(parts)
    code = extract_code(text)
    out_path = pathlib.Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(code)
    return {"path": str(out_path), "usage": usage, "seconds": secs, "chars": len(code)}
