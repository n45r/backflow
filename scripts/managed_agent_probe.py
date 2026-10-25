"""Minimal helper for Gemini Managed Agents (google-genai 2.33.0).

Usage (from repo root, with the venv):
    .venv/bin/python scripts/managed_agent_probe.py "print python version"

Library use:
    from managed_agent_probe import client, run, inline, download
    r = run("Run /work/model.inp with pyswmm ...",
            environment={"type": "remote",
                         "sources": inline({"work/model.inp": inp_text})})
    print(r["status"], r["seconds"], r["output_text"])
    data = download(r["environment_id"], "work/results.json")

The API key is read from ~/gemini-key.txt (line `workshop=<key>`).
It is never printed.
"""
from __future__ import annotations

import json
import os
import sys
import threading
import time
import warnings

warnings.filterwarnings("ignore", message=".*experimental.*")

from google import genai  # noqa: E402

BASE_AGENT = "antigravity-preview-09-2026"
KEY_FILE = os.path.expanduser("~/gemini-key.txt")
_client = None
_lock = threading.Lock()


def _key() -> str:
    if os.environ.get("GEMINI_API_KEY"):
        return os.environ["GEMINI_API_KEY"]
    with open(KEY_FILE) as f:
        for line in f:
            if line.strip().startswith("workshop="):
                return line.strip().split("=", 1)[1]
    raise RuntimeError("no workshop= line in ~/gemini-key.txt")


def client() -> genai.Client:
    # Lock matters: two threads racing here create two Clients, and the
    # discarded one closes the shared HTTP transport ("client has been closed").
    global _client
    with _lock:
        if _client is None:
            _client = genai.Client(api_key=_key())
    return _client


def inline(files: dict[str, str]) -> list[dict]:
    """Turn {target_path: text} into inline sources (1 MB/file, 2 MB total).
    Target must not be '/'; use a relative subdir like 'work/x.inp'."""
    return [{"type": "inline", "target": t, "content": c} for t, c in files.items()]


def _usage(u) -> dict:
    if u is None:
        return {}
    keys = ["total_input_tokens", "total_output_tokens", "total_thought_tokens",
            "total_tool_use_tokens", "total_cached_tokens", "total_tokens"]
    return {k: getattr(u, k, None) for k in keys}


def start(input: str, *, agent: str = BASE_AGENT, environment="remote",
          agent_config: dict | None = None, previous_interaction_id: str | None = None):
    """Create a background interaction. Returns (interaction, t0)."""
    kw = dict(agent=agent, input=input, environment=environment, background=True)
    if agent_config:
        kw["agent_config"] = agent_config
    if previous_interaction_id:
        kw["previous_interaction_id"] = previous_interaction_id
    t0 = time.time()
    return client().interactions.create(**kw), t0


def wait(interaction, t0: float, poll: float = 5.0, timeout: float = 1800) -> dict:
    c = client()
    while interaction.status in ("in_progress", None) and time.time() - t0 < timeout:
        time.sleep(poll)
        interaction = c.interactions.get(id=interaction.id)
    return {
        "id": interaction.id,
        "status": interaction.status,
        "seconds": round(time.time() - t0, 1),
        "environment_id": getattr(interaction, "environment_id", None),
        "output_text": interaction.output_text,
        "usage": _usage(interaction.usage),
        "errors": [str(e) for e in (interaction.errors or [])],
    }


def run(input: str, **kw) -> dict:
    """Start a background interaction and poll until it finishes."""
    poll = kw.pop("poll", 5.0)
    timeout = kw.pop("timeout", 1800)
    ia, t0 = start(input, **kw)
    return wait(ia, t0, poll=poll, timeout=timeout)


def download(environment_id: str, path: str) -> bytes:
    """Download one file (or a dir, returned as tar bytes) from the sandbox.
    Path is relative to the sandbox working dir (same as inline targets)."""
    return client().environments.files.download(environment=environment_id, path=path)


def list_files(environment_id: str, path: str = "", recursive: bool = True):
    r = client().environments.files.list(environment=environment_id, path=path,
                                         recursive=recursive)
    return [(f.path, f.type) for f in (r.files or [])]


if __name__ == "__main__":
    prompt = " ".join(sys.argv[1:]) or "Run `python3 --version` and print the output."
    print(json.dumps(run(prompt), indent=2, default=str))
