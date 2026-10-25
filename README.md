# Backflow

Cities use computer models to decide where to spend money on drains, flood walls and basement protection, but those models are often never checked against a real flood, because measuring floods is expensive. Cameras are cheap, and many already point at places that flood. Backflow is an agent that watches real flood video, builds a 3D scene of the site whose water comes only from a drainage simulation, and fixes the simulation until its render matches the video. It then predicts a flood it has never seen, and that prediction is scored against water-level sensors the agent never saw.

## Status

Work in progress. Built during the Gemini 4 Argon SF hackathon on 25 October 2026.

## How it works

- A small shared geometry file (weir crest, door threshold, basement floor, key pipe size, pond footprint) is read by both the Three.js scene and the EPA SWMM model, so a geometric fix seen in the render also changes the physics.
- SWMM runs through PySWMM. Water in the scene always comes from SWMM output, through a fixed mapping from node depth to water planes. A locked harness sets the water, so Argon cannot paint it.
- Argon watches the calibration video and writes a timeline of events (pond overflow, manhole overflow, basement wetting), with camera and time.
- The scene is rendered from the real camera view. Argon sees real frames and renders side by side and lists differences in flood timing and behaviour.
- Parallel hypothesis workers (for example sewer backflow, surface door, weir setting) each change the model, run SWMM, and return a rendered clip. Argon judges which one matches the video.
- When the model stops improving, it is frozen (hashed) and predicts a held-out flood from its inflow only.
- The evaluator reveals the real footage and the gauge curves the agent never saw, and reports the errors, including failures.

## What happens in a run

Split (see `backend/config.py`): calibrate on event 32 (night, infrared, basement wet, peak 47 mm), hold out event 20 (day, basement wet, peak 27 mm), dry check on event 21.

1. **Write the scene.** Argon writes the full Three.js scene from the 1:50 site plan PDF in one pass. In our run this was about 850 lines of code, 10,500 output tokens and 29,000 thinking tokens, in 514 seconds.
2. **Read the video.** Argon watches camera 5 of event 32 once and writes a timeline: when water shows in the floor drain, when the floor gets wet, when it peaks and recedes. The gauge is used only to check this, never as input.
3. **Round 0: structure.** Argon compares the real dry camera 5 frame with its render of the dry scene. It returns small patches: camera position and look-at, moves of named objects, the basement drain position and the floor slope. The harness (`applyPatch` in `web/harness.js`) applies them at once, and the render visibly changes.
4. **Round 1: path.** Three candidates are simulated in SWMM and rendered: water enters the basement through the sewer, through the door, or both. Argon judges which render matches the real frames.
5. **Later rounds: visual search.** Three parameter sets (current, less, more) are simulated and rendered at 5 moments around the wetting time Argon read from the video. Argon judges each row, names a winner and a direction (for example "less water"). The search narrows around the winner. It stops when Argon says "ok" or the current set wins two rounds in a row.
6. **Freeze.** The scene, patch and parameters are saved and hashed in `runs/loop/<name>/frozen.json`.
7. **Predict and reveal.** The untuned template and the frozen model both predict event 20 from its measured inflow only. The evaluator then loads the held-out video and the gauges, and scores both, plus a plain optimiser baseline fitted to Argon's video timeline.

In every judged round Argon sees only renders beside real frames. It never sees simulation numbers or gauges, and it never sets a number: it picks a render, and the code moves the settings. Water in the scene comes only from SWMM depths. A patch can move where water may sit, never how much there is.

For the live demo, `python -m backend.loop --live <name>` runs one more judged round from the frozen state: 3 simulations, renders and one judge call, with a target under 40 seconds. It does not change the frozen model. With `ARGON_CACHE=replay` it plays back recorded answers from rehearsal, so the demo works without Wi-Fi (see `docs/OFFLINE.md`).

## Results

Numbers in square brackets are placeholders until the final run is scored.

Held-out event 20, scored against gauges the loop never saw:

| Model | Basement (s6) peak error, mm | Basement first-water timing error, s | Basement mean abs. error, mm | Pond (s3) peak error, mm |
|---|---|---|---|---|
| Untuned template | [BLIND_ERROR_MM] | [BLIND_ONSET_S] | [BLIND_MAE_MM] | [BLIND_S3_MM] |
| Frozen model (after one flood video) | [INFORMED_ERROR_MM] | [INFORMED_ONSET_S] | [INFORMED_MAE_MM] | [INFORMED_S3_MM] |
| Plain optimiser (fitted to Argon's video timeline) | [BASELINE_ERROR_MM] | [BASELINE_ONSET_S] | [BASELINE_MAE_MM] | [BASELINE_S3_MM] |

The loop judges camera 5 (the basement) only. The pond is scored but was not judged.

Run details: [N_ROUNDS] judged rounds, [RUN_MINUTES] minutes, about [RUN_COST_USD] US dollars in model calls. One live round takes [ROUND_SECONDS] seconds.

Already measured:

- The untuned template floods the basement 2.5 to 3 times too deep (120 mm modelled vs 47 mm measured on event 32; 78 vs 27 mm on event 20) and wets the basement on dry event 21 (54 vs 2 mm). See `docs/gates/gate_a_results.md`.
- In night infrared video, Argon found when the basement floor got wet within about 10 seconds of the sensor. It saw water rising in the floor drain about 50 seconds before the sensor registered.
- The door hypothesis never wets the basement, while the video shows water rising through the floor drain.
- One judge call on a contact sheet takes about 10 seconds. In a test it chose correctly: partial water for the onset frame, a full floor for the peak frame.
- SWMM ran inside Managed Agents sandboxes with gemini-4-argon as the agent model: three hypotheses in parallel, about 225 seconds each.

## Honest limits

- The site is staged. FloodX is a training facility with controlled inflow, not a real street.
- We calibrate on one event. One flood is little evidence for a model.
- Peak time read from video is unreliable. The wetting onset is good.
- Real sites will have less data: fewer cameras, rougher plans, and often no measured inflow.

## Evidence rules

| Data | Who sees it | Role |
|---|---|---|
| Measured inflow (litres per second) | Agent | Known input of the experiment |
| Site plans and documented dimensions | Agent | Geometry anchors, not free knobs |
| Camera video of calibration events | Agent | The only calibration evidence |
| Water-level gauges (all events) | Evaluator only | Final score and reveal; never shown to the agent |
| Held-out event video | Evaluator only, until the prediction is frozen | Reveal |

Calibration is from video only. Gauges are used only to score.

## What is new vs borrowed

Borrowed:

- FloodX dataset (Eawag). Moy de Vitry, M., Dicht, S., Leitão, J. P. (2017). Earth System Science Data, 9, 657-666. https://doi.org/10.5194/essd-9-657-2017
  - Videos: Zenodo record 1039631 (CC0)
  - Documentation: Zenodo record 3643878 (CC BY 4.0)
  - Preprocessed data: Zenodo records 830513 and 830511 (CC0)
- EPA SWMM (public domain, US EPA)
- PySWMM (BSD-2-Clause)
- Three.js (MIT)
- Possibly the published FloodX SWMM template from https://github.com/mmmatthew/cq-analysis (MIT), if used

Related work: Vid2Sid (2026) compares sim and real robot video with a vision-language model; HydroAgent (2026) names a vision-language verifier as future work; Moy de Vitry et al. (2020) calibrated SWMM at FloodX from hand-built video signals. Backflow does not claim to have invented sim-vs-real video critique, or to be first to calibrate SWMM from video.

New: everything else in this repository.

## Setup

```
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Then put your Gemini API key in `.env`.

## Data

Data is downloaded by the scripts in `scripts/`. It is not stored in this repository.

## License

MIT. See `LICENSE`.
