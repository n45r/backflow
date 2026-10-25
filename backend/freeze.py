"""Freeze a prediction: commit to the scene, geometry, knobs and SWMM template before any reveal.

freeze() writes runs/frozen/<name>.json with sha256 hashes of every input and a short
commitment id. verify() recomputes the hashes from the files on disk and the stored values.
"""
import argparse
import hashlib
import json
import time
from pathlib import Path

from . import config

FROZEN = config.RUNS / "frozen"
TEMPLATE = config.TEMPLATE


def _canon(obj):
    return json.dumps(obj, sort_keys=True, separators=(",", ":")).encode()


def _sha_bytes(raw):
    return hashlib.sha256(raw).hexdigest()


def _hashes(scene_path, site, params):
    return {
        "scene_sha256": _sha_bytes(Path(scene_path).read_bytes()),
        "site_sha256": _sha_bytes(_canon(site)),
        "params_sha256": _sha_bytes(_canon(params)),
        "template_sha256": _sha_bytes(Path(TEMPLATE).read_bytes()),
    }


def _commitment(hashes):
    return _sha_bytes(_canon(hashes))[:12]


def frozen_path(name):
    if not name or "/" in name or "\\" in name or name.startswith("."):
        raise ValueError(f"bad freeze name: {name!r}")
    return FROZEN / f"{name}.json"


def freeze(scene_path, site, params, name):
    """Write runs/frozen/<name>.json and return the record. A name cannot be re-frozen to different inputs."""
    path = frozen_path(name)
    hashes = _hashes(scene_path, site, params)
    record = {
        "name": name,
        "scene_path": str(Path(scene_path).resolve()),
        "site": site,
        "params": params,
        **hashes,
        "commitment": _commitment(hashes),
        "frozen_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
    }
    if path.exists():
        old = json.loads(path.read_text())
        if old.get("commitment") != record["commitment"]:
            raise FileExistsError(f"{path} is already frozen with commitment {old.get('commitment')}")
        return old
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record, indent=1))
    return record


def verify(name):
    """True when the scene file, stored site and params, and template still match the commitment."""
    path = frozen_path(name)
    if not path.exists():
        return False
    rec = json.loads(path.read_text())
    try:
        hashes = _hashes(rec["scene_path"], rec["site"], rec["params"])
    except (OSError, KeyError):
        return False
    stored = {k: rec.get(k) for k in hashes}
    return hashes == stored and _commitment(hashes) == rec.get("commitment")


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    f = sub.add_parser("freeze")
    f.add_argument("--scene", required=True)
    f.add_argument("--site", default=str(config.SITE_JSON))
    f.add_argument("--params", default=str(config.PARAMS_JSON))
    f.add_argument("--name", required=True)
    v = sub.add_parser("verify")
    v.add_argument("--name", required=True)
    a = ap.parse_args()
    if a.cmd == "freeze":
        rec = freeze(a.scene, json.loads(Path(a.site).read_text()), json.loads(Path(a.params).read_text()), a.name)
        print(rec["commitment"], frozen_path(a.name))
    else:
        ok = verify(a.name)
        print("ok" if ok else "MISMATCH")
        raise SystemExit(0 if ok else 1)


if __name__ == "__main__":
    main()
