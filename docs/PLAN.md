# Plan

Gemini 4 Argon SF Hackathon, 25 Oct 2026. Track: More Dimensions. Submission 17:00 PDT.
Repo: https://github.com/n45r/backflow

## Pitch
"Flood models are often never checked against real floods, because measuring is expensive. Video is everywhere. Backflow is an agent that watches flood video, compares it with a 3D render of its own simulation, fixes the model, and then predicts a flood it has never seen, scored against sensors it never saw."

User: a drainage engineer who must trust a flood model before spending money on drains, walls or basement protection.

## Evidence rules (the honesty contract)
| Data | Who sees it | Role |
|---|---|---|
| Measured inflow (L/s) | Simulator | Known input of the experiment |
| Site plans and documented dimensions | Argon and our code | Starting geometry; key sizes live in one shared file that Argon may correct within plan tolerances |
| Real camera video, calibration events | Argon | The only calibration evidence |
| SWMM output numbers | Renderer only | Argon never sees them; it sees only the render |
| Water-level gauges, all events | Evaluator only | Final score and reveal |
| Held-out event video | Evaluator only, until the prediction is frozen | Reveal |

## Data
FloodX (Eawag, Switzerland, Oct 2016): 22 staged floods, 5 fixed cameras plus 1 GoPro, about 20 minutes per event, day and night infrared, measured inflow, water-level sensors, plans. Zenodo records 1039631 (video, CC0), 3643878 (docs, CC BY 4.0), 830513 and 830511 (sensor data, CC0). File lists and checksums verified against the Zenodo API.
Cameras: 1 (pond and weir) and 5 (basement).
Events: calibrate on a wet-basement event (to be found in the sensor data; event 33 is dry). Hold out another wet-basement event, such as event 32 (night infrared, basement peak 47 mm).

## Design: dynamic scene, physics-guarded water, video-only critique
1. Argon writes the Three.js scene of the site from plans and frames, in one long pass. Two virtual cameras start roughly aligned with real cameras 1 and 5.
2. The scene is dynamic in two ways. Water moves over time, driven by SWMM. The scene itself changes between rounds: Argon rewrites the scene code (camera alignment, layout, slopes, walls, water appearance). The demo shows round 1 beside the latest round.
3. Shared geometry file (site.json, about 5 values): weir crest height, door threshold height, basement floor height, key pipe diameter, pond footprint. Both the scene and the SWMM model read it. Argon may change these values only within the tolerances of the plans; every change is logged with its visual evidence. A change in the scene is therefore also a change in the physics.
4. Water guard: water heights in the scene always come from SWMM node depths through a fixed mapping that Argon cannot edit. A render check confirms the scene uses that mapping. Argon cannot paint water.
5. Loop: SWMM runs -> headless render from both camera views -> contact sheet (real frame and render side by side at 4 to 6 key times) -> Argon critiques landmark timing and geometry (weir overflow, manhole overflow, basement wetting, misaligned or misplaced parts) -> changes to scene code, site.json values and SWMM parameters (roughness, weir and orifice coefficients, active basement path) -> repeat.
6. Argon never sees SWMM numbers or gauges. The render is the only way it observes the simulation.
7. Night infrared: the prompt tells Argon to look for reflections, darker wet concrete and water lines on walls.
8. Full side-by-side video is used for the first watch of each calibration event; the live loop uses contact-sheet images for speed.

## Baseline
Argon extracts a landmark timeline from the real video once; a plain numeric optimiser then tunes SWMM to that timeline. Both methods are scored on the hidden gauges of the held-out event. This answers "why not just use an optimiser?" with data, whichever way it goes.

## Managed Agents
One sandbox worker per hypothesis (basement wets via sewer pipe backflow; via the surface door; weir setting wrong). Each worker is autonomous and loops several times inside its own sandbox: edit SWMM parameters and site.json within bounds, run SWMM, check water conservation and where the water goes, revise. It then returns its best candidate (or depths for our renderer if headless browsers fail in the sandbox) plus a short report. Argon judges the clips side by side with the real video. Our Python orchestrates. Fallback if PySWMM fails in the sandbox: run workers locally (and lose the Managed Agents prize).

## The loop in one line
Real video + inflow -> SWMM -> render -> side-by-side video -> Argon critique -> parameter change (parallel workers) -> repeat until no improvement -> freeze (hash) -> predict held-out flood from its inflow only -> reveal real footage and the hidden gauge curves, with errors.

## Demo (3 minutes, presenter-driven)
1. Real footage of a flood. The question.
2. Recorded run, labelled: earlier rounds and a wrong mechanism rejected with video evidence.
3. Live: one loop round on a contact sheet (target under about 40 seconds): the scene visibly changes and the water re-renders.
4. Live: frozen model predicts the held-out event; reveal real footage and gauges it never saw.
5. One line on the real world: USGS runs about 1,400 cameras at river gauges.

## Tech stack
Python 3.12, FastAPI, PySWMM 2.2.0 (works locally after re-signing its bundled libraries), google-genai 2.33.0 (Interactions API), Three.js via CDN import map in plain HTML, Playwright plus ffmpeg for headless rendering, ffmpeg for video prep (AVI to 480p MP4 at 1 to 2 fps).

## Build plan
1. 11:45-12:30 gate tests in parallel:
   a. Find wet-basement events in the sensor data; inspect the SWMM template network for both basement paths.
   b. Argon finds when water enters the basement in a night infrared clip.
   c. PySWMM runs inside a Managed Agents sandbox; try Argon as the agent's model.
   d. Time one loop round: render, contact sheet, Argon critique, scene rewrite; target under 40 s.
   f. Visual check: render 47 mm of water in Argon's basement scene beside a camera 5 frame; can a person see it?
   e. Published SWMM template runs on one event.
2. 12:30 tripwire: cut failed parts and change the claim to match.
3. 12:30-15:00 core loop, evaluator, workers; UI skeleton started early.
4. 15:00-16:00 demo screen.
5. 16:00-16:30 the held-out run; save traces.
6. 16:30-16:50 1-minute video; README with credits.
7. 16:50-17:00 submit.

## Known facts
- Sewer backflow into basements is real and common.
- Drainage modelling codes say calibrate on one data set and verify on another; in practice calibration is often skipped because measuring is expensive.
- A 2018 review found a lack of methods for using crowdsourced images or video for model calibration.
- A 2020 FloodX study calibrated a 7-parameter SWMM model with hand-built video-derived trends.
