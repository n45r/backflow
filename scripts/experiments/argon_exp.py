"""Argon video-processing experiments. Usage: python -I scripts/experiments/argon_exp.py <exp-name> ...
Key read from ~/gemini-key.txt (never printed). Outputs to runs/experiments/."""
import base64, json, os, re, subprocess, sys, time
import certifi
os.environ.setdefault("SSL_CERT_FILE", certifi.where())
from google import genai

ROOT = "/Users/ahmednasr/flood-reality-check"
VIDEO = f"{ROOT}/data/raw/video/cam5_ev32_1fps.mp4"
OUT = f"{ROOT}/runs/experiments"
MODEL = "gemini-4-argon"
GT = {"drain": 19*3600+0 + 0, }  # unused placeholder
def hms(s): h, m, x = s.split(":"); return int(h)*3600+int(m)*60+int(x)
REF = {"onset": hms("21:20:42"), "peak": hms("21:24:13"), "recede": hms("21:27:18")}
CLOCK_OFFSET = 11  # reference = camera clock + 11 s

key = next(l.strip().split("=", 1)[1] for l in open(os.path.expanduser("~/gemini-key.txt")) if l.startswith("workshop="))
client = genai.Client(api_key=key)

Q = """This is CCTV footage of a basement floor at night (infrared). Water may enter the room during the footage.
Answer ONLY as JSON with these keys:
{"drain_water_first_seen": "HH:MM:SS", "floor_wet_onset": "HH:MM:SS", "peak_extent": "HH:MM:SS", "recede": "HH:MM:SS",
 "confidence": {"drain_water_first_seen": 0-1, "floor_wet_onset": 0-1, "peak_extent": 0-1, "recede": 0-1}, "notes": "short"}
Meanings: drain_water_first_seen = water first visible rising inside the floor drain; floor_wet_onset = water first visible on the open floor;
peak_extent = time the water covers the largest area / is deepest; recede = time the water is mostly gone again.
Use null for anything you cannot see. """
TIME_VIDEO = "Give each time as the timestamp shown by the on-screen clock in the top right of the image."
TIME_IMG = "Give each time as the label of the frame (HH:MM:SS) closest to the event."

def upload():
    cache = f"{OUT}/uploaded.json"
    if os.path.exists(cache):
        f = client.files.get(name=json.load(open(cache))["name"])
        if f.state.name == "ACTIVE": return f
    f = client.files.upload(file=VIDEO, config={"mime_type": "video/mp4"})
    while f.state.name == "PROCESSING":
        time.sleep(3); f = client.files.get(name=f.name)
    json.dump({"name": f.name}, open(cache, "w"))
    return f

def call(label, parts):
    t = time.time()
    r = client.interactions.create(model=MODEL, input=parts)
    lat = time.time() - t
    text = r.output_text or ""
    u = r.usage.model_dump(exclude_none=True) if r.usage else {}
    mod = {m["modality"]: m["tokens"] for m in u.get("input_tokens_by_modality", [])}
    rec = {"label": label, "latency_s": round(lat, 1), "tokens_by_modality": mod,
           "total_in": u.get("total_input_tokens"), "out": u.get("total_output_tokens"),
           "thought": u.get("total_thought_tokens"), "tool_use": u.get("total_tool_use_tokens"), "text": text}
    return rec

def parse(text):
    m = re.search(r"\{.*\}", text, re.S)
    try: return json.loads(m.group(0))
    except Exception: return None

def score(rec, kind):
    j = parse(rec["text"]); rec["parsed"] = j
    if not j: return rec
    off = CLOCK_OFFSET if kind == "video" else 0
    err = {}
    for k, ref in (("floor_wet_onset", REF["onset"]), ("peak_extent", REF["peak"]), ("recede", REF["recede"])):
        v = j.get(k)
        try: err[k] = hms(v) + off - ref
        except Exception: err[k] = None
    try: err["drain"] = hms(j["drain_water_first_seen"]) + off - hms("21:19:50")
    except Exception: err["drain"] = None
    rec["err_s"] = err
    return rec

def vpart(f, processing=None, resolution=None):
    p = {"type": "video", "uri": f.uri, "mime_type": "video/mp4"}
    if processing is not None: p["processing"] = processing
    if resolution: p["resolution"] = resolution
    return p

def ctx(rec_extra): return rec_extra

def run(name, f):
    if name.startswith("fps"):
        fps = float(name[3:]); parts = [vpart(f, {"type": "static", "fps": fps})]; kind = "video"
    elif name.startswith("res_"):
        parts = [vpart(f, None, name[4:])]; kind = "video"
    elif name == "agentic":
        parts = [vpart(f, "agentic")]; kind = "video"
    elif name.startswith("clip"):
        s, e = {"clipA": (540, 900), "clipB": (780, 1140)}[name]  # A: 21:19-21:25, B: 21:23-21:29
        parts = [vpart(f, {"type": "static", "start_offset": f"{s}s", "end_offset": f"{e}s"})]; kind = "video"
    elif name == "default":
        parts = [vpart(f)]; kind = "video"
    elif name.startswith("img"):
        start, step = {"imgA": (hms("21:16:00"), 30), "imgB": (hms("21:18:00"), 60)}[name]
        parts = []
        for i in range(12):
            t = start + i*step; vt = t - hms("21:10:00")
            lab = "%02d:%02d:%02d" % (t//3600, t % 3600//60, t % 60)
            p = f"{OUT}/frames/{name}_{lab.replace(':','')}.jpg"
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", str(vt), "-i", VIDEO, "-frames:v", "1", "-q:v", "3", p], check=True)
            parts.append({"type": "text", "text": f"Frame time {lab}:"})
            parts.append({"type": "image", "data": base64.b64encode(open(p, "rb").read()).decode(), "mime_type": "image/jpeg"})
        kind = "img"
    parts.append({"type": "text", "text": Q + (TIME_VIDEO if kind == "video" else TIME_IMG)})
    rec = score(call(name, parts), kind)
    return rec

if __name__ == "__main__":
    f = upload()
    for name in sys.argv[1:]:
        base, _, rep = name.partition("#")
        try: rec = run(base, f)
        except Exception as e: rec = {"label": base, "error": repr(e)[:600]}
        rec["name"] = name
        json.dump(rec, open(f"{OUT}/{name.replace('#','_r')}.json", "w"), indent=2)
        print(name, json.dumps({k: v for k, v in rec.items() if k not in ("text", "name")}, default=str), flush=True)
