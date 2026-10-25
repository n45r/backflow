# Backflow

Cities use computer models to decide where to spend money on drains, flood walls and basement protection, but those models are often never checked against a real flood, because measuring floods is expensive. Cameras are cheap, and many already point at places that flood. Backflow is an agent that watches real flood video, builds a 3D scene of the site whose water comes only from a drainage simulation, and fixes the simulation until its render matches the video. It then predicts a flood it has never seen, and that prediction is scored against water-level sensors the agent never saw.

Headline: using only camera video, Backflow corrected a flood model about as well as the researchers' own sensor-based calibrations, and its prediction held on a flood it never saw. The inflow is a measured input and the model structure comes from the researchers' published template, so this is calibration, not prediction from video alone.

## Status

Work in progress. Built during the Gemini 4 Argon SF hackathon on 25 October 2026.

## How it works

- **Argon writes the world.** From the 1:50 site plan PDF and one dry camera frame, Argon writes the full Three.js scene of the site in one pass.
- **Water comes only from physics.** EPA SWMM (through PySWMM) computes depths at the pond, manholes and basement. A locked harness turns those depths into water in the scene. Argon cannot paint water.
- **Argon fixes what it made.** It compares its render of the dry basement with the real camera frame and returns small patches (camera pose, object moves) or a rewrite of its own scene code when something is missing or hidden. In every run it noticed that its own scene hid the basement floor drain, rewrote the scene code (about 90 seconds) so the drain, rod and cables show, then patched the camera.
- **Argon judges the video, the code moves the settings.** Each round, three candidate models are simulated and rendered from the real camera's view. The renders are stitched with the real footage into one time-lapse video, a 2x2 grid of real, A, B and C. Argon watches the whole video, picks the best match and names a direction. The code moves the three allowed settings toward the winner. Argon never writes a setting.
- **Freeze, then a blind test.** When Argon stops preferring change, the model is frozen and hashed. It predicts a flood it never saw from its inflow alone, and only then is it scored against water-level sensors.
- **Managed Agents.** Parallel sandbox workers can each test one hypothesis about how water reaches the basement, running SWMM inside Gemini Managed Agents with gemini-4-argon as the agent model (`workers/hypothesis.py`).

## What happens in a run

Split (see `backend/config.py`): calibrate on event 32 (night, infrared, basement wet, peak 47 mm), hold out event 20 (day, basement wet, peak 27 mm), dry check on event 21.

1. **Write the scene.** Argon writes the full Three.js scene from the 1:50 site plan PDF in one pass. In our run this was about 850 lines of code, 10,500 output tokens and 29,000 thinking tokens, in 514 seconds.
2. **Read the video.** Argon watches camera 5 of event 32 once and writes a timeline: when water shows in the floor drain, when the floor gets wet, when it peaks and recedes. The gauge is used only to check this, never as input.
3. **Round 0: structure.** Argon compares the real dry camera 5 frame with its render of the dry scene. It returns small patches: camera position and look-at, moves of named objects, the basement drain position and the floor slope. The harness (`applyPatch` in `web/harness.js`) applies them at once, and the render visibly changes.
4. **Round 1: path.** Three candidates are simulated and rendered: water enters the basement through the sewer, through the door, or both. Argon judges which one matches the real footage.
5. **Later rounds: video judging.** Three parameter sets (current, less, more) are simulated. Each is rendered from camera 5's viewpoint over the same window, from 180 s before to 420 s after the wetting time Argon read from the video. The renders and the real footage are stitched into one video: a 2x2 grid (real, A, B, C) with a clock on each panel. One video second is 6 s of flood (the live round uses 10 s per video second to run faster). Argon watches the whole video and replies with 4 to 6 deciding moments, a winner, what the winner still gets wrong and a direction (for example "faster drain"). The search narrows around the winner. It stops when Argon says "ok" or the current set wins two rounds in a row.
6. **Freeze.** The scene, patch and parameters are saved and hashed in `runs/loop/<name>/frozen.json`.
7. **Predict and reveal.** The untuned template and the frozen model both predict event 20 from its measured inflow only. The evaluator then loads the held-out video and the gauges, and scores both. It also scores a plain optimiser fitted to Argon's video timeline, and the researchers' own published sensor-based calibrations run in our model.

In every judged round Argon sees only renders beside real footage. It never sees simulation numbers or gauges, and it never sets a number: it picks a render, and the code moves the settings. Water in the scene comes only from SWMM depths. A patch can move where water may sit, never how much there is.

For the live demo, `python -m backend.loop --live calib_video` runs one more video-judged round from the frozen state: 3 simulations, renders, one stitched video and one judge call. It takes 45 to 80 seconds, because API latency varies. Start it at the beginning of the pitch and show the verdict around 1:30. It does not change the frozen model. The demo screen has a "What Argon watched" button that plays the exact video Argon judged. With `ARGON_CACHE=replay` it plays back recorded answers from rehearsal, so the demo works without Wi-Fi (see `docs/OFFLINE.md`).

## Results

Held-out event 20 (basement wet, measured peak 27 mm), scored against gauges the loop never saw. Basement (s6):

| Model | Mean error, mm | Peak error, mm | First-water error, s | Predicts the flood? |
|---|---|---|---|---|
| Untuned template | 33.5 | +64.9 | -20 | Yes, but 92 mm deep against 27 mm |
| Video-judged (main method, `calib_video`) | 5.9 | -5.1 | +50 | Yes, 22 mm against 27 mm |
| Still-frame variant, an earlier variant (`calib_v3`, repeated as `calib_v4`) | 3.8 | -8.3 | +50 | Yes |
| Researchers' sensor-based calibrations (median of 40, run in our model) | 5.3 (best 3.5) | +6.9 | not scored | Yes |
| Plain numeric optimiser fitted to Argon's video timeline | 4.0 | -26.7 | never wet | No, basement stays dry (peak 0 mm) |

Read the peak and the wet/dry column first. The basement is dry most of the time, so mean error alone is misleading. The plain optimiser has a mean error of 4.0 mm only because it predicts no flood. An engineer reading that model would be told the basement stays dry when it floods to 27 mm.

Video judging cut the mean error from 33.5 mm to 5.9 mm and the peak error from +65 mm to -5 mm. Timing got worse: the first water comes 50 s late, against 20 s early for the untuned template. The loop judges camera 5 (the basement) only. The pond (s3) was not judged. Its peak error went from -6.5 to +10.2 mm and its mean error from 92.8 to 75.8 mm.

Comparison on the same hidden flood. The FloodX researchers published 40 calibrations that used all three water-level sensors, on events 21 to 24 (Zenodo 3475502, `calibration_experiment_results_summary.csv`). Run in our model on event 20, they give a median mean error of 5.3 mm (best 3.5 mm) and a median peak error of +6.9 mm. Video-only calibration reached about the same accuracy. Caveats: their settings came from their simpler template and we ran them in our model (with our storage-curve fix), and this is one hidden flood. We do not claim to beat them.

The `calib_video` run took six rounds, about 6 minutes after the scene was written. The structure round took 119 s. Each judged round took 46 to 55 s: about 30 s to simulate and render, 8 to 17 s for the judge call. The settings it found: outlet coefficient 0.63, pipe p7 diameter 0.103 m, pipe p3 roughness 0.0226. The still-frame variant ran twice (`calib_v3`, `calib_v4`) and reached the same parameters and scores both times.

Engineer experiment. Argon watched a 10-minute side-by-side video, the plan PDF and the SWMM input file, and named the two settings that matter: pipe p7 is too wide and the outlet valve is too restrictive. A brute-force sensitivity analysis found the same two. But when we let Argon set 8 values at once, the result on the hidden flood was worse: about 50 mm mean error, and a basement peak of 162 mm against 27 mm measured. Argon is good at diagnosing and judging, and worse at writing exact numbers. So the loop lets Argon judge and the code moves the settings.

Already measured:

- Before a storage-curve fix, the untuned template flooded the basement 2.5 to 3 times too deep and wetted it on dry event 21. After the fix it overfloods event 32 by about 4 times (213 vs 47 mm). See `docs/gates/gate_a_results.md`.
- In night infrared video, Argon found when the basement floor got wet within about 10 seconds of the sensor. It saw water rising in the floor drain about 50 seconds before the sensor registered.
- The door hypothesis never wets the basement, while the video shows water rising through the floor drain.
- In the earlier still-frame variant, one judge call on a contact sheet takes about 10 seconds. In a test it chose correctly: partial water for the onset frame, a full floor for the peak frame.
- SWMM ran inside Managed Agents sandboxes with gemini-4-argon as the agent model: three hypotheses in parallel, about 225 seconds each.

### Every other flood: does the basement flood or not?

We also ran the untuned and the corrected model (`calib_video`) on all 23 FloodX events that have inflow data, except event 32, which the loop watched. Water-level sensors decide the truth. File: `docs/gates/all_events_wet_dry.csv`.

| Model | Correct wet/dry calls | False alarms (predicts a flooded basement that stayed dry) | Missed floods |
|---|---|---|---|
| Untuned template | 16 of 23 | 7 | 0 |
| After watching one flood video | 21 of 23 | 2 (18.5 mm against 7 mm measured; 10.6 mm against 0 mm) | 0 |

Some of these events had different valve settings or a breached dam, which the model does not know about, so this is a rough check, not a clean benchmark.

## Honest limits

- The site is staged. FloodX is a training facility with controlled inflow, not a real street.
- We calibrate on one event and test on one hidden flood. One flood is little evidence for a model.
- The inflow is a measured input, and the model structure comes from the researchers' published template. This is not prediction from video alone.
- The researchers' settings came from their simpler template and are run in our model, with our storage-curve fix. The comparison with them is approximate. It is one hidden flood.
- The first water in the basement is 50 s late after calibration. Timing got worse while depth got much better. Peak time read from video is unreliable. The wetting onset is good.
- Real sites will have less data: fewer cameras, rougher plans, and often no measured inflow.
- Which three settings the loop may change (outlet coefficient, p7 diameter, p3 roughness) was chosen by an offline sensitivity analysis that ran the model on all events, including the held-out one. The values were then chosen by the loop from video only. A stricter test would choose the settings without the held-out event.
- The video-judged result comes from one run. The two still-frame runs agreed with each other, which is still a small sample.
- The live round is slow and varies. It takes 45 to 80 seconds, depending on API latency, so it must start at the beginning of the pitch. Offline replay mode exists if Wi-Fi drops.
- Argon cannot be trusted to write exact numbers. In the engineer experiment, 8 values set by Argon gave a worse result than the tuned model.
- The SWMM model's basement storage curve had a bug that we fixed during the build. Scores above use the fixed model for the untuned, frozen and researcher runs.

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
  - Published calibration results (used for the comparison): Zenodo record 3475502
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
