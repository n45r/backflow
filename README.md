# Backflow

Cities use computer models to decide where to spend money on drains, flood walls and basement protection, but those models are often never checked against a real flood, because measuring floods is expensive. Cameras are cheap, and many already point at places that flood. Backflow is an agent that watches real flood video, builds a 3D scene of the site whose water comes only from a drainage simulation, and fixes the simulation until its render matches the video. It then predicts a flood it has never seen, and that prediction is scored against water-level sensors the agent never saw.

## Status

Work in progress. Built during the Gemini 4 Argon SF hackathon on 25 October 2026.

## How it works

- **Argon writes the world.** From the 1:50 site plan PDF and one dry camera frame, Argon writes the full Three.js scene of the site in one pass.
- **Water comes only from physics.** EPA SWMM (through PySWMM) computes depths at the pond, manholes and basement. A locked harness turns those depths into water in the scene. Argon cannot paint water.
- **Argon fixes what it made.** It compares its render of the dry basement with the real camera frame and returns small patches (camera pose, object moves) or a rewrite of its own scene code when something is missing or hidden.
- **Argon judges, the code moves.** Each round, three candidate models are simulated and rendered from the real camera's view. Argon sees only the real frames beside the renders, picks the best match per moment and names a direction. The code moves the three allowed settings toward the winner.
- **Freeze, then a blind test.** When Argon stops preferring change, the model is frozen and hashed. It predicts a flood it never saw from its inflow alone, and only then is it scored against water-level sensors.
- **Managed Agents.** Parallel sandbox workers can each test one hypothesis about how water reaches the basement, running SWMM inside Gemini Managed Agents with gemini-4-argon as the agent model (`workers/hypothesis.py`).

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

Held-out event 20, scored against gauges the loop never saw:

| Model | Basement (s6) peak error, mm | Basement first-water timing error, s | Basement mean abs. error, mm | Pond (s3) peak error, mm |
|---|---|---|---|---|
| Untuned template | +64.9 | -20 | 33.5 | -6.5 |
| Frozen model (after one flood video) | -8.3 | +50 | 3.8 | +14.6 |

The basement mean error falls from 33.5 mm to 3.8 mm, about 9 times smaller. The frozen model predicts the wetting 50 s late, against 20 s early for the untuned template, so timing got worse while depth got much better. The loop judges camera 5 (the basement) only; the pond is scored but was not judged.

Two independent runs (`calib_v3`, `calib_v4`) reached the same parameters and the same held-out scores. Each run took about 3 minutes: a structure round of about 2 minutes (in both runs Argon rewrote its scene code to uncover the floor drain), then judged rounds of 20 to 30 seconds each. One live round takes 25 seconds.

Already measured:

- Before a storage-curve fix, the untuned template flooded the basement 2.5 to 3 times too deep and wetted it on dry event 21. After the fix it overfloods event 32 by about 4 times (213 vs 47 mm). See `docs/gates/gate_a_results.md`.
- In night infrared video, Argon found when the basement floor got wet within about 10 seconds of the sensor. It saw water rising in the floor drain about 50 seconds before the sensor registered.
- The door hypothesis never wets the basement, while the video shows water rising through the floor drain.
- One judge call on a contact sheet takes about 10 seconds. In a test it chose correctly: partial water for the onset frame, a full floor for the peak frame.
- SWMM ran inside Managed Agents sandboxes with gemini-4-argon as the agent model: three hypotheses in parallel, about 225 seconds each.

## Honest limits

- The site is staged. FloodX is a training facility with controlled inflow, not a real street.
- We calibrate on one event. One flood is little evidence for a model.
- Peak time read from video is unreliable. The wetting onset is good.
- Real sites will have less data: fewer cameras, rougher plans, and often no measured inflow.
- Which three settings the loop may change (outlet coefficient, p7 diameter, p3 roughness) was chosen by an offline sensitivity analysis that ran the model on all events, including the held-out one. The values were then chosen by the loop from video only. A stricter test would choose the settings without the held-out event.
- The search took one step toward "less water" and then stopped, so the result rests on a few judgements. Two runs agreed, which is still a small sample.
- The SWMM model's basement storage curve had a bug that we fixed during the build; scores above use the fixed model for both the untuned and the frozen runs.

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
