import json, time
from pathlib import Path
from backend.render import Renderer
from backend.contact import contact_sheet

run = Path("runs/test_synth")
run.mkdir(parents=True, exist_ok=True)
ts = list(range(0, 601, 10))
dep = {"event": 0, "dt_s": 10, "t": ts,
       "depth_m": {"s3": [0.6 * t / 600 for t in ts], "s6": [0.05 * t / 600 for t in ts],
                   "m2": [0.0 if t < 300 else 0.1 * (t - 300) / 300 for t in ts], "m3": [0] * len(ts)}}
(run / "depths.json").write_text(json.dumps(dep))
times = [0, 150, 300, 450, 600]
t0 = time.time(); r = Renderer().start(); t1 = time.time()
print("browser start", round(t1 - t0, 2), r.gl_mode)
p5 = r.render("/scene/placeholder.js", run / "depths.json", "cam5", times, run / "r")
t2 = time.time(); print("first cam (scene load + 5 frames)", round(t2 - t1, 2))
p1 = r.render("/scene/placeholder.js", run / "depths.json", "cam1", times, run / "r")
t3 = time.time(); print("cam1 5 frames warm", round(t3 - t2, 2), "per frame", round((t3 - t2) / 5, 3))
p5 = r.render("/scene/placeholder.js", run / "depths.json", "cam5", times, run / "r")
t4 = time.time(); print("cam5 5 frames warm", round(t4 - t3, 2), "total 10 frames warm", round(t4 - t2 + 0, 2))
contact_sheet(p5, p5, [f"{t} s" for t in times], run / "contact.png")
r.close()
