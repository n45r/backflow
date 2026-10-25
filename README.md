# Backflow

An agent watches real flood video, writes a dynamic 3D scene of the site, and compares a render of its own flood simulation with the real footage. It fixes the scene and the model in a render-watch-critique loop, then predicts a held-out flood that is scored against sensors it never saw.

## Status

Work in progress. Built during the Gemini 4 Argon SF hackathon on 25 October 2026.

## How it works

- One site description (positions and heights of the pond, weir, manholes, basement floor, door threshold, and pipe links) generates both the Three.js scene and the EPA SWMM model. A geometric error seen in the render is also an error in the physics.
- Argon watches the calibration video and writes a timeline of events (pond overflow, manhole overflow, basement wetting), with camera and time.
- SWMM runs through PySWMM. Water in the scene always comes from SWMM output, through a fixed mapping from node depth to water planes.
- The scene is rendered from the real camera view. Argon watches the real footage and the render side by side and lists differences in flood timing and behaviour.
- Parallel hypothesis workers (for example sewer backflow, surface door, weir setting) each change the model, run SWMM, and return a rendered clip. Argon judges which one matches the video.
- When the model stops improving, it is frozen (hashed) and predicts a held-out flood from its inflow only.
- The evaluator reveals the real footage and the gauge curves the agent never saw, and reports the errors, including failures.

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
