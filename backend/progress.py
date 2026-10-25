"""Live progress of a run, for the demo app. One JSON file per run directory, rewritten at each stage."""
import json
import time
from pathlib import Path

STAGES = ["simulate", "render", "video", "upload", "watching", "verdict", "done", "error"]


def report(run_dir, stage, text, **extra):
    """stage is one of STAGES; text is one plain sentence for the screen; extra may hold paths or numbers."""
    p = Path(run_dir) / "progress.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    prev = json.loads(p.read_text()) if p.exists() else {"log": []}
    entry = {"t": round(time.time(), 1), "stage": stage, "text": text, **{k: (str(v) if isinstance(v, Path) else v) for k, v in extra.items()}}
    log = (prev.get("log") or [])[-40:] + [entry]
    p.write_text(json.dumps({"current": entry, "log": log}, indent=1))
