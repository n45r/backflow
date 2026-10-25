# Notes for agents working on this repo

Lessons from building Backflow, so the next run does not hit the same snags.

## Gemini 4 Argon
- Thinking tokens share the output cap. A visual call capped at 16k output came back empty after Argon spent the whole budget thinking. Visual calls use a 65,536 cap.
- Calls go through the Interactions API first (`backend/argon.py`, `_interactions_call`) and fall back to `generate_content` if a part type cannot be mapped (for example PDFs).
- Long "high" thinking calls need long HTTP timeouts. Scene generation took 514 s; it uses a 900 s timeout.
- Venue Wi-Fi drops showed up as `RemoteProtocolError: Server disconnected`. Every call retries with backoff, and the call log is `runs/argon_calls.jsonl`.
- Shown two identical images, a judge prompt without an explicit "same" option invented a difference. Ask for a per-row same/different verdict first and say that "no difference" is a valid answer.
- Video sampling is 1 frame per second by default. A time-lapse for judging is encoded at 1 fps so no frame is skipped.
- Argon is good at diagnosing and judging, and poor at writing exact values for many coupled settings at once. The loop lets Argon judge rendered candidates and the code moves the settings.

## Video judging
- The video window must cover the whole flood, including the drain-down. With the window cut before the floor drained, Argon could not see an overshoot, because 46 mm and 76 mm of water look the same while the floor is covered.
- Windows are taken from Argon's own video timeline (`runs/timeline/<event>.json`), never from gauges.

## Search
- Moving all settings along one "less water" line could not reach settings that fit two floods. The search moves one setting per round, cycling through them, and stops after a full cycle with no change.

## SWMM
- On macOS the bundled SWMM libraries in swmm-toolkit can be killed with exit 137 (invalid code signature). Fix: `codesign --force --sign -` on each `.dylib` and `.so` in `.venv/lib/python3.12/site-packages/swmm/toolkit`.
- PySWMM reports a 0.0 % continuity error inside the `with` block; read it from the `.rpt` file instead.
- The published template's basement storage curve stopped at 0.03 m and SWMM extrapolated it; it is held flat at 43 m2 above that (`backend/sim.py`).
- PySWMM allows one simulation per process; candidates run in separate processes.

## Managed Agents
- Agent `antigravity-preview-09-2026` with `agent_config={"type": "antigravity", "model": "gemini-4-argon"}` runs SWMM in the sandbox after `pip install pyswmm`.
- Some worker interactions stayed `in_progress` with an empty error until the timeout. A worker that does not finish is left out of the comparison rather than replaced with unfitted settings.

## Honesty rules
- Nothing in the loop reads gauges or the held-out event. `tests/test_boundaries.py` checks this statically.
- Live rounds write to `runs/loop/<name>_live`, never into the frozen run.
- Offline replay (`ARGON_CACHE=replay`) returns recorded answers and fails loudly on a miss.
