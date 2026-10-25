# Offline demo checklist

The venue Wi-Fi can drop. The demo must run with no internet. Only live Argon calls need the network.

## During rehearsal (Wi-Fi up)
1. Run the full demo flow once with `ARGON_CACHE=record`. Every successful Argon reply is saved to `runs/argon_cache/<hash>.json`.
2. Check that `runs/argon_cache/` has files and that `runs/argon_calls.jsonl` shows `"ok": true` lines.
3. Run the same flow again with `ARGON_CACHE=replay`. It must finish with no error. A missing reply raises `CacheMiss` with the file name it wanted.
4. Turn Wi-Fi off and run step 3 again, plus `.venv/bin/python -m backend.server`, then load `/demo.html`.

## On stage
- Wi-Fi up: run live (`ARGON_CACHE` unset) or with `record`.
- Wi-Fi down: restart the loop with `ARGON_CACHE=replay`. Replayed calls show `"replay": true` in `runs/argon_calls.jsonl`.
- Last resort: show the saved fixture run `runs/loop/demo_fixture` in `/demo.html`. It needs no Argon calls.
- Replay only works if the inputs are identical to rehearsal (same frames, same scene code, same prompts, same settings). Do not edit prompts or scenes after recording.

## Files that must exist locally
- Three.js: `web/vendor/three/build/three.module.js` (three@0.170.0). `web/index.html` loads it through the import map. No CDN.
- Scene modules: `web/scene/*.js` and every `round_*/` scene a loop run points to.
- Depths: `runs/<run_id>/depths.json` for each event used (20, 21, 32), and the depths each loop round references.
- Clips: `data/clips/<event>_<cam>.mp4`, or `runs/loop/<name>/fixture_clips/<event>_<cam>.mp4` as a fallback. `data/clips/` is empty now; the fixture run uses `fixture_clips/`.
- Frames: `backend/frames.py` cuts frames from the clips with local ffmpeg (`/opt/homebrew/bin/ffmpeg`). If a clip is missing it rebuilds it from `data/raw/video/`, which must be on disk.
- Loop runs: `runs/loop/<name>/frozen.json`, `round_*/round.json`, contact sheets, `holdout.json`.
- Reveal: `runs/reveal/<name>.json` (for example `runs/reveal/demo_fixture.json`).
- Site: `site/site.json`, `site/params.json`.
- Argon replies: `runs/argon_cache/*.json` (from rehearsal).

## Quick offline check
- `BACKFLOW_PORT=8772` with `backend/render.py`: the harness loads from the local server only. The page load retries 3 times with backoff, then fails with a clear message.
- `.venv/bin/python tests/test_argon_cache.py` prints `ok` (record then replay, no network).
