"""Gate test: can Managed Agents run EPA SWMM in the sandbox?

.venv/bin/python scripts/gate_test.py swmm          # tests 1 + 4 + 5 (cold)
.venv/bin/python scripts/gate_test.py reuse ENV_ID  # test 5 (warm reuse)
.venv/bin/python scripts/gate_test.py model MODEL   # test 3
.venv/bin/python scripts/gate_test.py parallel      # test 6
"""
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, os.path.dirname(__file__))
from managed_agent_probe import (BASE_AGENT, client, download, inline,  # noqa: E402
                                 list_files, run)

HERE = os.path.dirname(__file__)
INP = open(os.path.join(HERE, "fixtures", "tiny.inp")).read()

RUNNER = r'''
import json, re, sys
from pyswmm import Simulation, Nodes
# NOTE: sim.flow_routing_error read inside the `with` block returns 0.0
# (stats are only final after swmm_end), so parse the .rpt instead.
mx = 0.0
inp = sys.argv[1]
with Simulation(inp) as sim:
    j = Nodes(sim)["J1"]
    for _ in sim:
        mx = max(mx, j.depth)
rpt = open(inp[:-4] + ".rpt").read()
sec = rpt[rpt.find("Flow Routing Continuity"):]
m = re.search(r"Continuity Error \(%\) \.+\s+(-?[\d.]+)", sec)
res = {"max_depth_J1_m": mx,
       "flow_routing_continuity_error_pct": float(m.group(1)) if m else None}
json.dump(res, open(sys.argv[2], "w"), indent=2)
print(json.dumps(res))
'''

SWMM_PROMPT = """You are in a Linux sandbox. Do exactly this, using the shell:
1. Run `pip install pyswmm` (if that fails, try `pip install swmm-toolkit`; if that fails,
   clone https://github.com/USEPA/Stormwater-Management-Model and build runswmm with cmake).
2. The files work/model.inp and work/run_swmm.py already exist. Run
   `python3 work/run_swmm.py work/model.inp work/results.json`.
3. Print the full stdout/stderr of each command. Do not modify model.inp.
Reply with: which install method worked, the exact JSON printed, and `pwd` output."""


def show(tag, r):
    print(f"== {tag}")
    print(json.dumps(r, indent=2, default=str))
    sys.stdout.flush()


def swmm():
    env = {"type": "remote",
           "sources": inline({"work/model.inp": INP, "work/run_swmm.py": RUNNER})}
    r = run(SWMM_PROMPT, environment=env)
    show("swmm cold", r)
    eid = r["environment_id"]
    if eid:
        try:
            print("files:", list_files(eid, "work"))
        except Exception as e:  # noqa: BLE001
            print("list_files error:", repr(e))
        try:
            print("results.json:", download(eid, "work/results.json").decode())
        except Exception as e:  # noqa: BLE001
            print("download error:", repr(e))


def reuse(eid):
    r = run("Run `python3 work/run_swmm.py work/model.inp work/results2.json` and print stdout.",
            environment=eid)
    show("swmm warm reuse", r)


def model(name):
    # a) per-interaction agent_config on the base agent
    try:
        r = run("Reply with the word OK.", agent_config={"type": "antigravity", "model": name},
                timeout=600)
        show(f"interaction agent_config model={name}", r)
    except Exception as e:  # noqa: BLE001
        print(f"interaction agent_config model={name} ERROR: {e!r}")
    # b) named custom agent
    aid = "frc-probe-" + name.replace(".", "-").replace("_", "-")[:30]
    try:
        a = client().agents.create(id=aid, base_agent=BASE_AGENT,
                                   agent_config={"type": "antigravity", "model": name},
                                   base_environment="remote")
        print("agents.create OK:", a)
        r = run("Reply with the word OK.", agent=aid, timeout=600)
        show(f"custom agent {aid}", r)
    except Exception as e:  # noqa: BLE001
        print(f"agents.create model={name} ERROR: {e!r}")
    finally:
        try:
            client().agents.delete(id=aid)
        except Exception:  # noqa: BLE001
            pass


def parallel():
    t0 = time.time()
    with ThreadPoolExecutor(3) as ex:
        futs = [ex.submit(run, f"Run `echo worker{i} && nproc && free -m` and print output.")
                for i in range(3)]
        for i, f in enumerate(futs):
            try:
                show(f"parallel {i}", f.result())
            except Exception as e:  # noqa: BLE001
                print(f"parallel {i} ERROR: {e!r}")
    print("parallel wall:", round(time.time() - t0, 1))


if __name__ == "__main__":
    cmd = sys.argv[1]
    {"swmm": lambda: swmm(), "reuse": lambda: reuse(sys.argv[2]),
     "model": lambda: model(sys.argv[2]), "parallel": lambda: parallel()}[cmd]()
