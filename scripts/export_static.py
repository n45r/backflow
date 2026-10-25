"""Export a replay-only static copy of the Backflow demo, and optionally publish it to GitHub Pages.

    .venv/bin/python scripts/export_static.py RUN_NAME [--publish] [--out build/site]

The site has no server. The demo page reads JSON files that mirror the /api responses
(api/default_run.json, api/loop/<run>.json, api/reveal/<run>.json, api/progress/<run>.json),
and "Run a live round" replays the recorded round with its original timings.
--publish force-pushes the folder to the gh-pages branch of origin (that branch only) and
turns Pages on for it if it is not on yet.
"""
import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from backend import server  # noqa: E402  (reuse the API functions so the JSON mirrors the real responses)

WEB = ROOT / "web"
RUNS = ROOT / "runs"
CLIPS = ROOT / "data" / "clips"
LOOP = RUNS / "loop"
MAX_BYTES = 120 * 1024 * 1024
REPO = "n45r/backflow"
PAGES_URL = "https://n45r.github.io/backflow/"
SCRUB = re.compile(r"\s*[—–]\s*")
SECRETS = re.compile(r"AIza[0-9A-Za-z_\-]{20,}|sk-[0-9A-Za-z]{20,}|GEMINI_API_KEY\s*=\s*\S|/Users/")
STATIC_PREFIXES = ("runs/", "clips/", "scene/")


def sh(*cmd, cwd=ROOT, check=True, capture=False):
    r = subprocess.run(cmd, cwd=cwd, check=check, text=True, capture_output=capture)
    return r.stdout if capture else r


def rel_url(value):
    """Turn a server URL or an absolute file path into a site-relative path, or None if it is neither."""
    if not isinstance(value, str):
        return None
    if value.startswith("/") and value[1:].startswith(STATIC_PREFIXES):
        return value[1:]
    if value.startswith("runs/") and value.endswith(".json") and (ROOT / value).is_file():
        return value  # a path written relative to the repo root, such as the depths of a live round
    if value.startswith(str(ROOT) + "/"):
        u = server._url(value)
        return u[1:] if u else None
    return None


def rewrite(obj, used):
    """Copy of obj with every file reference made relative; the paths found are added to `used`."""
    if isinstance(obj, dict):
        return {k: rewrite(v, used) for k, v in obj.items()}
    if isinstance(obj, list):
        return [rewrite(v, used) for v in obj]
    if isinstance(obj, str):
        r = rel_url(obj)
        if r:
            used.add(r)
            # a scene is loaded with import(), which needs "./" for a path under the site root
            return "./" + r if r.startswith("scene/") else r
        return SCRUB.sub(", ", obj)
    return obj


def source_of(rel):
    if rel.startswith("clips/"):
        return CLIPS / rel[len("clips/"):]
    if rel.startswith("scene/"):
        return WEB / rel
    return ROOT / rel


def write_json(site, rel, data):
    p = site / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, separators=(",", ":")))


def timed_log(log, judge_s):
    """Give every log entry `at`, seconds from the round start. Argon's wait was logged at one instant, so spread it."""
    if not log:
        return log
    t0 = log[0].get("t", 0)
    out, upload_at = [], None
    for e in log:
        e = dict(e)
        e["at"] = round(max(0.0, e.get("t", t0) - t0), 1)
        if e.get("stage") == "upload":
            upload_at = e["at"]
        if upload_at is not None and e.get("stage") == "watching":
            e["at"] = round(max(e["at"], upload_at + 1.0), 1)
        if upload_at is not None and e.get("stage") == "verdict":
            e["at"] = round(max(e["at"], upload_at + max(4.0, judge_s)), 1)
        out.append(e)
    return out


def progress_from_round(loop_summary):
    """No recorded live round: replay the last calibration round that Argon judged."""
    judged = [r for r in loop_summary["rounds"] if r.get("candidates") and r.get("winner") and r.get("judge_video_url")]
    if not judged:
        return None
    r = judged[-1]
    secs = r.get("seconds") or {}
    sim = float(secs.get("sim_render") or 25)
    judge = float(secs.get("judge") or 8)
    n = r["round"]
    video = r["judge_video_url"]
    moments = [{"label": x.get("label"), "verdict": x.get("verdict"), "evidence": x.get("evidence")} for x in r["rows"]]
    text = f"Round {n}: Argon picked {r['winner']}. {r.get('remaining_error') or ''}".strip()
    log = [
        {"stage": "simulate", "text": f"Round {n}: simulating 3 versions of the model", "round": n, "candidates": r["candidates"], "at": 0.0},
        {"stage": "render", "text": f"Round {n}: drawing each version in Argon's 3D scene, from the real camera's view", "round": n, "at": round(sim * 0.3, 1)},
        {"stage": "upload", "text": f"Round {n}: sending Argon a time-lapse, real flood beside the 3 versions", "round": n, "video": video, "at": round(sim, 1)},
        {"stage": "watching", "text": f"Round {n}: Argon is watching the video", "round": n, "video": video, "at": round(sim + 1, 1)},
        {"stage": "verdict", "text": text, "round": n, "winner": r["winner"], "moments": moments, "video": video, "at": round(sim + max(4.0, judge), 1)},
    ]
    return {"current": log[-1], "log": log}


def build(name, site):
    loop_dir = LOOP / name
    if not (loop_dir / "frozen.json").exists():
        sys.exit(f"run {name} has no frozen.json, nothing to export")
    if site.exists():
        shutil.rmtree(site)
    site.mkdir(parents=True)
    used = set()

    # API mirrors
    summary = server.loop_summary(name)
    write_json(site, "api/default_run.json", {"name": name, "live_ready": True, "replay": False})
    write_json(site, f"api/loop/{name}.json", rewrite(summary, used))

    reveal = server.reveal(name)
    write_json(site, f"api/reveal/{name}.json", rewrite(reveal, used))

    live_prog = server._read_json(LOOP / f"{name}_live" / "progress.json")
    if live_prog and (live_prog.get("log") or []):
        judge_s = 0.0
        recs = sorted((LOOP / f"{name}_live").glob("round_*/round.json"))
        if recs:
            judge_s = float(((server._read_json(recs[-1]) or {}).get("seconds") or {}).get("judge") or 0)
        prog = {"current": live_prog.get("current"), "log": timed_log(live_prog["log"], judge_s)}
        source = "recorded live round"
    else:
        prog = progress_from_round(summary)
        source = "last calibration round"
    # the Managed Agents cards come first, from the recorded run, then the rounds after them
    ag = server.agents_entry()
    if prog and ag:
        order = sorted({e["round"] for e in prog["log"] if e.get("round")})
        renum = {r: i + 2 for i, r in enumerate(order)}
        shifted = [dict(e, round=renum[e["round"]]) if e.get("round") else dict(e) for e in prog["log"] if e.get("round") != 0]
        log = [ag] + shifted
        prog = {"current": log[-1], "log": log}
    out = {"name": name, "running": False, "started_here": False, "started": None, "progress": prog, "replay": False}
    write_json(site, f"api/progress/{name}.json", rewrite(out, used))
    print(f"replay source: {source}")

    # pages and scripts
    for f in ("demo.css", "demo.js", "harness.js"):
        shutil.copy2(WEB / f, site / f)
    html = (WEB / "demo.html").read_text()
    assert 'src="./index.html"' in html
    html = html.replace('src="./index.html"', 'src="./harness.html"')
    html = html.replace("<head>", "<head>\n<script>window.BACKFLOW_STATIC = true;</script>", 1)
    (site / "demo.html").write_text(html)
    shutil.copy2(WEB / "index.html", site / "harness.html")
    (site / "index.html").write_text(
        '<!doctype html>\n<html lang="en"><head><meta charset="utf-8"><title>Backflow</title>\n'
        f'<meta http-equiv="refresh" content="0; url=demo.html?run={name}">\n'
        f'<script>location.replace("demo.html?run={name}");</script></head>\n'
        f'<body><a href="demo.html?run={name}">Open the Backflow demo</a></body></html>\n')
    (site / ".nojekyll").write_text("")
    shutil.copytree(WEB / "vendor", site / "vendor")

    # media, scenes, depths, contact sheets: exactly what the JSON points at
    missing = []
    for rel in sorted(used):
        src = source_of(rel)
        if not src.is_file():
            missing.append(rel)
            continue
        dst = site / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
    if missing:
        print("missing files (left out):")
        for m in missing:
            print("  ", m)

    # nothing private may ship
    for p in site.rglob("*"):
        if p.is_file() and p.suffix in (".json", ".html", ".js", ".css") and "vendor" not in p.parts:
            m = SECRETS.search(p.read_text(errors="replace"))
            if m:
                sys.exit(f"refusing to export: {p.relative_to(site)} contains {m.group(0)!r}")

    total = sum(p.stat().st_size for p in site.rglob("*") if p.is_file())
    print(f"exported {name} to {site}: {total / 1e6:.1f} MB, {sum(1 for p in site.rglob('*') if p.is_file())} files")
    if total > MAX_BYTES:
        sys.exit(f"site is {total / 1e6:.0f} MB, over the {MAX_BYTES // 2**20} MB budget")
    return total


def publish(site):
    origin = sh("git", "remote", "get-url", "origin", capture=True).strip()
    user = sh("git", "config", "user.name", capture=True).strip()
    email = sh("git", "config", "user.email", capture=True).strip()
    if (site / ".git").exists():
        shutil.rmtree(site / ".git")
    sh("git", "init", "-q", "-b", "gh-pages", cwd=site)
    sh("git", "config", "user.name", user, cwd=site)
    sh("git", "config", "user.email", email, cwd=site)
    sh("git", "add", "-A", cwd=site)
    sh("git", "commit", "-q", "-m", "Static replay of the Backflow demo", cwd=site)
    sh("git", "push", "-q", "--force", origin, "gh-pages:gh-pages", cwd=site)
    have = subprocess.run(["gh", "api", f"repos/{REPO}/pages"], capture_output=True, text=True)
    if have.returncode != 0:
        sh("gh", "api", "-X", "POST", f"repos/{REPO}/pages", "-f", "source[branch]=gh-pages", "-f", "source[path]=/")
        print("Pages enabled from gh-pages")
    else:
        src = json.loads(have.stdout).get("source") or {}
        if src.get("branch") != "gh-pages" or src.get("path") != "/":
            sh("gh", "api", "-X", "PUT", f"repos/{REPO}/pages", "-f", "source[branch]=gh-pages", "-f", "source[path]=/")
    print(f"published: {PAGES_URL}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("run")
    ap.add_argument("--out", default=str(ROOT / "build" / "site"))
    ap.add_argument("--publish", action="store_true")
    a = ap.parse_args()
    site = Path(a.out).resolve()
    build(a.run, site)
    if a.publish:
        publish(site)


if __name__ == "__main__":
    main()
