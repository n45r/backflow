"""Record then replay through argon.ask with a fake client. No network.

Run: .venv/bin/python -m tests.test_argon_cache   (or pytest, if installed)
"""
import json
import os
import pathlib
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from google.genai import types  # noqa: E402

from backend import argon  # noqa: E402


class _Usage:
    def model_dump(self):
        return {"candidates_token_count": 7, "prompt_token_count": 3}


class _Resp:
    text = "hello from the fake"
    usage_metadata = _Usage()


class _Models:
    def __init__(self):
        self.calls = 0

    def generate_content(self, model, contents, config):
        self.calls += 1
        return _Resp()


class _FakeClient:
    def __init__(self):
        self.models = _Models()


def _patch(tmp):
    fake = _FakeClient()
    saved = {k: getattr(argon, k) for k in ("CACHE_DIR", "CALL_LOG", "LOCK_DIR", "_keys", "client")}
    argon.CACHE_DIR = tmp / "argon_cache"
    argon.CALL_LOG = tmp / "argon_calls.jsonl"
    argon.LOCK_DIR = tmp / "slots"
    argon._keys = lambda: {"fake": "x"}
    argon.client = lambda *a, **k: fake
    return fake, saved


def test_record_then_replay():
    old_env = os.environ.get("ARGON_CACHE")
    with tempfile.TemporaryDirectory() as d:
        tmp = pathlib.Path(d)
        fake, saved = _patch(tmp)
        try:
            parts = [types.Part.from_bytes(data=b"\x89PNG fake", mime_type="image/png"),
                     types.Part.from_text(text="describe this")]

            os.environ["ARGON_CACHE"] = "record"
            text, usage, _ = argon.ask(parts, thinking="low")
            assert text == "hello from the fake" and fake.models.calls == 1
            assert len(list(argon.CACHE_DIR.glob("*.json"))) == 1

            def boom(*a, **k):
                raise AssertionError("replay must not call the client")
            fake.models.generate_content = boom

            os.environ["ARGON_CACHE"] = "replay"
            text2, usage2, secs = argon.ask(parts, thinking="low")
            assert (text2, usage2) == (text, usage) and secs == 0.0

            try:
                argon.ask([types.Part.from_text(text="never recorded")], thinking="low")
                raise AssertionError("expected a cache miss")
            except argon.CacheMiss as e:
                assert "ARGON_CACHE=replay" in str(e)

            log = [json.loads(line) for line in argon.CALL_LOG.read_text().splitlines()]
            assert [e.get("replay", False) for e in log] == [False, True]
        finally:
            for k, v in saved.items():
                setattr(argon, k, v)
            if old_env is None:
                os.environ.pop("ARGON_CACHE", None)
            else:
                os.environ["ARGON_CACHE"] = old_env


if __name__ == "__main__":
    test_record_then_replay()
    print("ok")
