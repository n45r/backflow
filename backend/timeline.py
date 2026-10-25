"""Landmark timeline of one flood event, read from camera video only.

One Argon call per event with the cam1 (pond and weir) and cam5 (basement) clips.
Times are seconds from the event start (reference clock). Cached in runs/timeline/<event>.json.
"""
import argparse
import json
import re
import time
from pathlib import Path

from google.genai import types

from . import argon, data
from .config import ROOT, RUNS, SPLIT
from .frames import fc

CLIPS = ROOT / "data" / "clips"
OUT = RUNS / "timeline"
LANDMARKS = ("pond_overflow_onset_s", "basement_drain_water_s", "basement_wet_onset_s",
             "basement_peak_s", "basement_recede_s")
CAM_ROLE = {"cam1": "camera 1, looking at the pond and the weir w1 (the pond spills over the weir crest)",
            "cam5": "camera 5, inside the basement, looking at the floor and the circular floor drain"}

# Development fallback clips: (path, video seconds at event start). Used only when
# data/clips/<event>_<cam>.mp4 is missing. Video time 0 of this clip is reference 21:10:00;
# event 32 starts at 21:16:00.
FALLBACK = {(32, "cam5"): (ROOT / "data" / "raw" / "video" / "cam5_ev32_1fps.mp4", 360.0)}

PROMPT = """You are watching fixed CCTV recordings of one staged flood at an outdoor urban drainage test site. LIGHTING_PLACEHOLDER
The clips are listed above, each labelled with its camera. CLIP_TIMING_PLACEHOLDER

The recordings can have gaps where the picture jumps forward, so for every moment give both the video time MM:SS of the named clip and the on-screen clock HH:MM:SS shown in the frame at that moment. Use null if the moment does not happen or you cannot see it. Do not guess times you cannot see.
- pond_overflow_onset (camera 1): water first starts to spill over the weir crest of the pond.
- basement_drain_water (camera 5): water first becomes visible inside the floor drain.
- basement_wet_onset (camera 5): water first leaves the drain and wets the basement floor around it.
- basement_peak (camera 5): water on the basement floor is highest or covers the largest area.
- basement_recede (camera 5): the floor water has mostly drained back into the drain.

Reply with JSON only:
{"pond_overflow_onset": {"camera": "cam1", "video_time": "MM:SS" or null, "onscreen_clock": "HH:MM:SS" or null, "confidence": 0.0-1.0, "evidence": "what you see"},
 "basement_drain_water": {...}, "basement_wet_onset": {...}, "basement_peak": {...}, "basement_recede": {...},
 "confidence": 0.0-1.0, "notes": "what you are unsure about"}"""


def _clip(event, cam):
    p = CLIPS / f"{event}_{cam}.mp4"
    if p.exists():
        return p, 0.0
    if (int(event), cam) in FALLBACK and FALLBACK[(int(event), cam)][0].exists():
        return FALLBACK[(int(event), cam)]
    return None, None


def _upload(path):
    c = argon.client()
    f = c.files.upload(file=str(path), config={"mime_type": "video/mp4"})
    while f.state and f.state.name == "PROCESSING":
        time.sleep(3)
        f = c.files.get(name=f.name)
    if not f.state or f.state.name != "ACTIVE":
        raise RuntimeError(f"upload of {path.name} not active: {f.state}")
    return f


def _seconds(mmss):
    if mmss in (None, "", "null"):
        return None
    parts = [float(x) for x in str(mmss).strip().split(":")]
    s = 0.0
    for p in parts:
        s = s * 60 + p
    return s


def _clock_to_event_s(event, cam, clock):
    """On-screen camera clock -> seconds from event start (reference = camera clock minus offset)."""
    if not clock or not re.fullmatch(r"\d{1,2}:\d{2}:\d{2}", str(clock).strip()):
        return None
    h, m, sec = (int(x) for x in str(clock).strip().split(":"))
    start, _ = data.event_window(event)
    off = fc.OFFSETS[(fc.EVENTS[int(event)], cam)]
    ref = h * 3600 + m * 60 + sec - off
    return float(ref - (start.hour * 3600 + start.minute * 60 + start.second))


def _clip_key(clips):
    return {c: [str(p.relative_to(ROOT)), p.stat().st_size] for c, (p, _) in clips.items()}


def extract(event, cams=("cam1", "cam5"), refresh=False, role=None):
    """Landmark times (s from event start) for one event, from video only. Cached."""
    out = OUT / f"{int(event)}.json"
    clips = {cam: _clip(event, cam) for cam in cams}
    clips = {cam: v for cam, v in clips.items() if v[0] is not None}
    if out.exists() and not refresh:
        cached = json.loads(out.read_text())
        if cached.get("clip_key") == _clip_key(clips):
            return cached
    if not clips:
        raise FileNotFoundError(f"no clips for event {event} in {CLIPS}")

    night = int(event) == 32
    lighting = ("It was filmed at night with infrared: wet concrete is darker and reflective, water lines show on walls."
                if night else "It was filmed in daylight.")
    timing = []
    parts = []
    for cam, (path, lead) in clips.items():
        f = _upload(path)
        parts += [types.Part.from_text(text=f"Clip {cam}: {CAM_ROLE[cam]}."),
                  types.Part.from_uri(file_uri=f.uri, mime_type="video/mp4")]
        if lead:
            timing.append(f"The {cam} clip starts {int(lead)} s before the event; the inflow starts after that.")
    missing = [c for c in cams if c not in clips]
    if missing:
        timing.append(f"No clip is available for {', '.join(missing)}; return null for its moments.")
    prompt = PROMPT.replace("LIGHTING_PLACEHOLDER", lighting).replace("CLIP_TIMING_PLACEHOLDER", " ".join(timing))
    parts.append(types.Part.from_text(text=prompt))

    text, usage, secs = argon.ask(parts, thinking="high", max_output_tokens=16384)
    m = re.search(r"\{.*\}", text, re.S)
    reply = json.loads(m.group(0)) if m else {}

    result = {"event": int(event),
              "role": role or ("calibrate" if int(event) == SPLIT["calibrate"] else
                               "dry" if int(event) == SPLIT["dry"] else
                               "check" if int(event) == SPLIT["holdout"] else "other"),
              "source": "video only", "model": argon.MODEL,
              "clips": {cam: {"path": str(p.relative_to(ROOT)), "video_s_at_event_start": lead}
                        for cam, (p, lead) in clips.items()},
              "clip_key": _clip_key(clips),
              "time_source": "on-screen clock minus camera offset; video time where the clock is unread",
              "confidence": reply.get("confidence"), "notes": reply.get("notes"),
              "evidence": {}, "landmark_confidence": {}, "video_time_s": {}, "clock_time_s": {}}
    for key in LANDMARKS:
        item = reply.get(key[:-2]) or {}
        cam = item.get("camera") or ("cam1" if key.startswith("pond") else "cam5")
        v = _seconds(item.get("video_time"))
        lead = clips.get(cam, (None, 0.0))[1] or 0.0
        vt = None if v is None or cam not in clips else round(v - lead, 1)
        ct = _clock_to_event_s(event, cam, item.get("onscreen_clock")) if cam in clips else None
        result["video_time_s"][key], result["clock_time_s"][key] = vt, ct
        result[key] = ct if ct is not None and vt is not None else vt
        result["landmark_confidence"][key] = item.get("confidence")
        result["evidence"][key] = item.get("evidence")
    result["usage"] = usage
    result["seconds"] = secs
    result["raw"] = text
    OUT.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2))
    return result


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--event", type=int, required=True)
    ap.add_argument("--refresh", action="store_true")
    ap.add_argument("--role", help="calibrate, check or dry (default from config SPLIT)")
    a = ap.parse_args()
    r = extract(a.event, refresh=a.refresh, role=a.role)
    print(json.dumps({k: v for k, v in r.items() if k not in ("raw", "usage")}, indent=2))


if __name__ == "__main__":
    main()
