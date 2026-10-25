# Plan

Gemini 4 Argon SF Hackathon, 25 Oct 2026. Track: More Dimensions. Submission 17:00 PDT.
Repo: https://github.com/n45r/backflow

## Pitch
"Flood models are often never checked against real floods, because measuring is expensive. Video is everywhere. Backflow is an agent that watches flood video, compares it with a 3D render of its own simulation, fixes the model, and then predicts a flood it has never seen, scored against sensors it never saw."

User: a drainage engineer who must trust a flood model before spending money on drains, walls or basement protection.

## Evidence rules
| Data | Who sees it | Role |
|---|---|---|
| Measured inflow (L/s) | Simulator | Known input of the experiment |
| Site plans and documented dimensions | Argon and our code | Starting geometry |
| Real camera video, calibration events | Argon | The only calibration evidence |
| Argon's video timeline (landmark times) | Hypothesis workers | Targets for feasibility checks |
| SWMM output numbers | Renderer and hypothesis workers | The visual critic never sees them |
| Water-level gauges, all events | Evaluator only | Final score and reveal |
| Held-out event video | Evaluator only, until the prediction is frozen | Reveal |

## Data
FloodX (Eawag, Switzerland, Oct 2016): 22 staged floods, 5 fixed cameras plus 1 GoPro, about 20 minutes per event, day and night infrared, measured inflow, water-level sensors, plans. Zenodo records 1039631 (video, CC0), 3643878 (docs, CC BY 4.0), 830513 and 830511 (sensor data, CC0). Cameras: 1 (pond and weir) and 5 (basement).

## Final design rules
1. **Scene generation (round 0).** Argon writes the full Three.js scene in one pass from plans and dry frames. The scene exposes `updateScene(siteConfig, patchConfig)` and named geometry groups.
2. **Scene updates (round 1 onward).** Round 1 fixes structure and camera alignment, shown with a before/after wireframe diff. Later rounds render the active way water enters the basement (a sheet over the door sill, or upwelling from the floor drain) and the spreading wet area. Every round's change is visible; no change is made for show.
3. **Water guard.** A locked host harness sets water heights only from SWMM node depths. Argon cannot paint water.
4. **Floor slope.** Argon sets the basement floor slope and drain position once, from plans or dry frames, then they are frozen. A sloped floor turns small depth changes into a visible spreading puddle.
5. **Shared geometry file (site.json).** About 5 values (weir crest, door threshold, basement floor, key pipe diameter, pond footprint) read by both SWMM and the scene. Frozen after round 1, except at most one value the visual critique explicitly justifies.
6. **Hydraulic knobs.** At most 3: the basement entry path (door or sewer backflow), one weir coefficient (mainly constrained by camera 1), one pipe or orifice coefficient (mainly constrained by camera 5).
7. **Two roles for Argon.** Hypothesis workers see Argon's video timeline and SWMM numbers, never gauges or held-out video. The visual critic sees only contact sheets: real frames beside renders. Gauges stay with the evaluator.
8. **Event selection.** One wet calibration event, one dry check event, one wet held-out event. All three must have the same physical setup in experiment_list.csv (valves, notches, grates, manhole covers, initial states). Any difference is given to the model as a known input, never fitted.
9. **Dry check.** Any parameter set that fits the wet calibration event must also keep the basement dry on the dry event. This runs inside each worker and costs about half a second of SWMM time.
10. **Loop mechanics.** A warm Playwright browser tab renders key times (`window.setStep(t)` then a screenshot). A contact sheet of 4 to 6 key times, real beside render, goes to Argon. No video encoding inside the loop. Full video is used once per calibration event for the first watch.
11. **Managed Agents.** One autonomous sandbox worker per hypothesis. Each loops several times: edit allowed parameters, run SWMM, check conservation, the dry check and where the water goes, then revise. It returns its best candidate and a short report. Used in the recorded calibration run, not in the live 40-second round.
12. **Baseline.** Argon extracts a landmark timeline from the real video once; a plain numeric optimiser tunes SWMM to it. Both are scored on the hidden gauges of the held-out event.

## Blind guess, then learn
1. Blind: Argon sees only the dry site (plans, photos, dry frames) and builds the scene and the model. That model predicts the held-out flood. It is locked.
2. Learn: the loop calibrates on one real flood video.
3. Informed: the calibrated model predicts the same held-out flood. It is locked.
4. Reveal both against the hidden gauges. The gain from watching one flood is measured, not claimed.

Gate A showed the untuned template floods the basement 2.5 to 3 times too deep and wets it on a dry event, so the blind guess has a real error to fix.

## Demo (3 minutes, presenter-driven)
1. Real footage of a flood. The question.
2. Recorded, labelled: worker hypotheses, a wrong mechanism rejected with video evidence, the scene changing round by round.
3. Live: one contact-sheet critique, a visible 3D patch and a re-render, in under about 40 seconds.
4. Live: the frozen model predicts the held-out event; reveal the real footage and the gauges it never saw, with errors and the baseline.
5. One line on the real world: USGS runs about 1,400 cameras at river gauges.

## Fallback ladder (12:30 tripwire)
- Argon cannot see night infrared water: use daytime wet events; or add a small inset showing the difference from a dry frame (derived from video only).
- PySWMM fails in the sandbox: compile EPA SWMM from its C source inside the sandbox; or let the workers call our local SWMM runner as a tool.
- A loop round takes more than 2 minutes: keep the browser tab warm and reduce key times; pre-record the multi-round run and keep one round live.

## Gate tests
a. Wet-basement events, matching configurations, the SWMM template network, a template run.
b. Argon finds basement wetting times in night infrared video, checked against the gauge.
c. SWMM inside a Managed Agents sandbox; Argon as the agent's model.
d. Time one loop round.
e. A person can see 47 mm of water in the rendered sloped basement beside a camera 5 frame.

## Prior work
- Vid2Sid (arXiv 2602.19359, 2026): a vision-language model compares paired sim and real robot videos and proposes physics parameter updates. Backflow applies this idea to an urban drainage model.
- HydroAgent (arXiv 2605.17792, 2026): LLM agents calibrate a hydrology model from text diagnostics; names a vision-language verifier as future work.
- Moy de Vitry et al. 2020: calibrated SWMM at FloodX with hand-built video-derived trend data.
- Agentic SWMM, SWMM-Agentic, AQUAH: LLM agents that operate stormwater or hydrology models from text.

## Known facts
- Sewer backflow into basements is real and common.
- Drainage modelling codes say calibrate on one data set and verify on another; in practice calibration is often skipped because measuring is expensive.
- A 2018 review found a lack of methods for using crowdsourced images or video for model calibration.
