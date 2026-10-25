"""Gate test: can gemini-4-argon see basement water arrive in night-IR CCTV?

Usage: python -I scripts/argon_video_gate.py <video.mp4> <out.json> [model]
Reads the key from ~/gemini-key.txt (line `workshop=...`). Never prints it.
"""
import json
import os
import sys
import time

import certifi

os.environ.setdefault("SSL_CERT_FILE", certifi.where())
from google import genai  # noqa: E402

video, out_path = sys.argv[1], sys.argv[2]
model = sys.argv[3] if len(sys.argv) > 3 else "gemini-4-argon"

key = None
with open(os.path.expanduser("~/gemini-key.txt")) as f:
    for line in f:
        if line.startswith("workshop="):
            key = line.strip().split("=", 1)[1]
assert key, "no workshop= key line"
client = genai.Client(api_key=key)

PROMPT = """This is a CCTV recording from a camera pointed at a basement room of a test building, filmed at night.
Watch the whole video and answer as JSON with these keys:
- "can_see_scene": can you see the basement floor at all? Describe lighting / infrared image quality and what is in view.
- "onscreen_clock_visible": true/false, and the format of any timestamp overlay.
- "water_first_appears": {"video_time": "MM:SS", "onscreen_clock": "HH:MM:SS or null", "cues": "..."}
- "water_peak": {"video_time": "MM:SS", "onscreen_clock": "...", "cues": "..."}
- "water_recedes": {"video_time": "MM:SS", "onscreen_clock": "...", "cues": "..."} (when water is clearly draining / mostly gone; null if it never does in the clip)
- "visual_cues": describe what tells you water is present (reflections, darker wet concrete, water lines, floating objects, ripples, etc.).
- "confidence": 0-1 for each of the three times, and an overall note on what you are unsure about.
If you see no water at any point, say so and set the times to null. Do not guess times you cannot see."""

t0 = time.time()
f = client.files.upload(file=video, config={"mime_type": "video/mp4"})
while f.state and f.state.name == "PROCESSING":
    time.sleep(3)
    f = client.files.get(name=f.name)
t_upload = time.time() - t0
print(f"file {f.name} state={f.state.name if f.state else None} upload+processing={t_upload:.1f}s", flush=True)
if not f.state or f.state.name != "ACTIVE":
    sys.exit(f"file not active: {f.state}")

result = {"model": model, "video": video, "file": f.name, "upload_processing_s": round(t_upload, 1)}
t1 = time.time()
try:
    inter = client.interactions.create(
        model=model,
        input=[
            {"type": "video", "uri": f.uri, "mime_type": "video/mp4"},
            {"type": "text", "text": PROMPT},
        ],
    )
    result["api"] = "interactions.create"
    texts = [inter.output_text] if getattr(inter, "output_text", None) else []
    for o in ([] if texts else (getattr(inter, "steps", None) or [])):
        t = getattr(o, "text", None)
        if t:
            texts.append(t)
        for c in getattr(o, "content", None) or []:
            if getattr(c, "text", None):
                texts.append(c.text)
    result["text"] = "\n".join(texts)
    u = getattr(inter, "usage", None)
    result["usage"] = u.model_dump(exclude_none=True) if u is not None else None
    if not result["text"]:
        result["raw"] = inter.model_dump(exclude_none=True, mode="json")
except Exception as e:  # fall back
    result["interactions_error"] = repr(e)[:1000]
    print("interactions failed:", repr(e)[:500], flush=True)
    t1 = time.time()
    resp = client.models.generate_content(
        model=model,
        contents=[f, PROMPT],
        config={"response_mime_type": "application/json"},
    )
    result["api"] = "models.generate_content"
    result["text"] = resp.text
    result["usage"] = resp.usage_metadata.model_dump(exclude_none=True, mode="json") if resp.usage_metadata else None
result["model_call_s"] = round(time.time() - t1, 1)

with open(out_path, "w") as fo:
    json.dump(result, fo, indent=2, default=str)
print(json.dumps({k: v for k, v in result.items() if k != "raw"}, indent=2, default=str))
