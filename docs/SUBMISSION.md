# Submission text

**Project name:** Backflow

**One line:** Flood video in, a flood model you can trust out: Gemini 4 Argon watches a real flood beside renders of a drainage simulation, steers the model until they match, and the corrected model then predicts a flood it never saw.

**Track:** More Dimensions

**Repository:** https://github.com/n45r/backflow

**Live demo (recorded run, replays in the browser):** https://n45r.github.io/backflow/

**Video:** (YouTube link)

## Description

Cities decide where to spend money on drains and basement protection using flood models such as EPA SWMM. Some settings in those models cannot be measured, so they are guesses, and checking them normally needs sensors in the sewer and a real flood. Video of floods is cheap and already exists.

Backflow uses Gemini 4 Argon to check and correct a flood model with video only:

1. Argon read the 1:50 site plan of the FloodX test site and wrote the whole Three.js scene in one pass. Comparing its render with the real camera, it noticed its own scene hid the basement floor drain and rewrote its code.
2. SWMM computes the water; a locked harness draws exactly that water in Argon's scene, filmed from the real camera's angle. Argon never paints water and never sees simulation numbers.
3. Each round, three versions of the model are rendered and stitched with the real footage into one time-lapse. Argon watches the whole video, picks the best match and says what is still wrong. The code moves the settings toward its pick.
4. The model is frozen and hashed, then predicts a different flood it never saw, from its inflow alone. Only then are the water-level sensors revealed.

Results on the hidden flood (basement): mean error 33.5 mm untuned, 5.9 mm after watching one flood video, within the range of the FloodX researchers' own sensor-based calibrations (median 5.3 mm over 40). Across all 23 other floods with data, the corrected model calls "basement floods or stays dry" correctly 21 times, up from 16, with no missed floods. In control experiments, simple rules and even sensor-based oracles fitted to the watched flood drove the model to a dry basement on the hidden flood; Argon's sequence of picks ranked 12th of the 74 out of 81 possible sequences that predict the flood.

Gemini 4 Argon is used for: one-pass 3D scene generation from a PDF plan, self-correction of that scene, night-infrared long-video understanding (wetting onset within about 10 s of the sensor), and video judging in a verification loop. Managed Agents (`antigravity-preview-09-2026` with `gemini-4-argon`) run SWMM inside sandboxes as hypothesis workers. Calls use the Interactions API.

Honest limits: a staged test site; one watched flood and one hidden flood; the three tuned settings were chosen by an offline analysis over all events; the inflow is a measured input (the question, not the answer).

## Built during the event
Everything in the repository was written on 25 October 2026 (see the commit history). Borrowed and credited: the FloodX dataset (Eawag, CC0 and CC BY 4.0), the researchers' SWMM template (MIT), EPA SWMM, PySWMM and Three.js.
