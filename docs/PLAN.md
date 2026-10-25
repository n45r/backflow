# Plan

Gemini 4 Argon SF Hackathon, 25 Oct 2026. Track: More Dimensions. Submission 17:00 PDT. Now about 11:35.

## Pitch
"Flood models are often never checked against real floods, because measuring is expensive. Video is everywhere. We built an agent that turns flood video into a corrected flood model, then checks it against sensors it never saw."

User: a drainage engineer who must trust a flood model before spending money on drains, walls or basement protection.

## Evidence rules (the honesty contract)
| Data | Who sees it | Role |
|---|---|---|
| Measured inflow (litres per second) | Agent | Known input of the experiment |
| Site plans and documented dimensions | Agent | Geometry anchors, not free knobs |
| Camera video of calibration events | Agent | The only calibration evidence |
| Water-level gauges (all events) | Evaluator only | Final score and reveal; never shown to the agent |
| Held-out event video | Evaluator only, until the prediction is frozen | Reveal |

Calibration is from video only. Gauges are used only to score. Errors are shown, including failures.

## Data
FloodX (Eawag, Switzerland, Oct 2016): 22 staged floods at an outdoor training site (pond, weir, channels, real sewer pipes and manholes, building with basement). 5 fixed cameras plus 1 GoPro, about 20 minutes per event, day and night infrared. Measured inflow, water-level sensors, site plans. Public on Zenodo (CC0 / CC BY 4.0).

Cameras: camera 1 (pond and weir) and camera 5 (basement) first.
Events: calibrate on an event where the basement gets wet (to be found in the data; event 33 is dry, so it cannot teach the basement path). Hold out a different wet-basement event, such as event 32 (night infrared, basement peak 47 mm).

## What Argon does
1. Observer: watches the calibration video and writes a timeline (pond overflow start, manhole overflow, basement wetting), with camera and time.
2. World builder: writes the Three.js scene of the site from plans and frames, before the demo. We then lock two virtual cameras to match real cameras 1 and 5, so the critic spends its rounds on the flood, not on the camera angle.
3. Critic: watches a recording of our rendered scene (water driven by SWMM output) beside the real camera footage. It lists differences in flood timing and behaviour, then proposes model changes. For night infrared video it is told to look for reflections, darker wet concrete and water lines on walls.
4. Judge: compares the results of competing hypotheses against the video and picks the best.

## Physics
EPA SWMM through PySWMM. The published FloodX SWMM template is a disclosed starting point. Argon never draws water; water in the scene always comes from SWMM output.

SWMM gives a depth at each node, not a 3D water surface. A fixed rule maps it: the pond node depth sets the pond water plane, the basement node depth sets the basement water plane, manhole head drives an overflow effect. The mapping is written once and never edited by the agent.

Before relying on the template, check that its network contains both candidate paths into the basement (surface door and sewer pipe backflow). If one is missing, we add it ourselves as a fixed, validated option the workers can switch on or tune, so the agent never writes raw SWMM network syntax.

## Single site description
Argon edits one site file: the positions and heights of the pond, weir, manholes, basement floor, door threshold, and pipe links. Our code builds both the Three.js scene and the SWMM model from it, so a geometric error Argon sees in the render is also an error in the physics.

The critic watches one side-by-side video: real footage on the left, our render on the right, at the same time and from the same camera angle. Hypothesis workers return rendered clips, and Argon judges them.

## Managed Agents (Gemini API sandboxes)
One worker per hypothesis, for example: basement wets via sewer pipe backflow; basement wets via the surface door; weir setting wrong. Each worker edits the model, runs SWMM, renders or summarises the result, compares it with the video timeline, revises up to a fixed budget, and returns an evidence report. Our Python orchestrates, because agents cannot start agents. Fallback if PySWMM will not run in the sandbox: run workers locally (and lose the Managed Agents prize).

## The loop
Evidence -> Argon writes scene and model -> SWMM runs -> render the scene as video from the real camera view -> Argon compares render with real video -> still improving? yes: fix and rerun (parallel hypothesis workers); no: freeze (hash) -> predict the held-out flood from its inflow only -> reveal real footage and gauge curves, with errors.

## Demo (3 minutes, presenter-driven)
1. Real footage of a flood. The question.
2. Recorded run, labelled: the earlier calibration rounds and the wrong mechanism rejected with video evidence.
3. Live: one full loop round runs on stage in under about 40 seconds. Argon watches the render beside the real clip (low frame rate, short window), workers fix the model, the scene re-renders.
4. Live: the frozen model predicts the held-out event; then reveal real footage and the gauges it never saw.
5. One line on the real world: USGS runs about 1,400 cameras at river gauges.

## Build plan
1. 11:50-12:30 gate tests in parallel:
   a. Find wet-basement events in the FloodX sensor data, and inspect the SWMM template network for both basement paths (small downloads).
   b. Argon finds when water enters the basement in a night infrared clip.
   c. PySWMM runs inside a Managed Agents sandbox; try Argon as the agent's model.
   d. Time one loop round (render clip, Argon critique, model change, re-render); target under 40 seconds.
   e. Published SWMM template runs on one event.
2. 12:30 tripwire: cut failed parts and change the claim to match.
3. 12:30-15:00 core loop, evaluator, workers; UI skeleton started early.
4. 15:00-16:00 demo screen.
5. 16:00-16:30 the real held-out run; save traces.
6. 16:30-16:50 1-minute video, README with credits.
7. 16:50-17:00 submit.

## Known facts
- Sewer backflow into basements is real and common.
- Drainage modelling codes say calibrate on one data set and verify on another; in practice calibration is often skipped because measuring is expensive.
- A 2018 review found a lack of methods for using crowdsourced images or video for model calibration.
- A 2020 FloodX study calibrated a 7-parameter SWMM model with hand-built video-derived trends; errors in those trends could cancel the benefit.
