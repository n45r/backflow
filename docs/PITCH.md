# Pitch

Gemini 4 Argon SF hackathon, 25 October 2026. Live demo: 3 minutes, no slides. Submission video: 1 minute.

Placeholders in square brackets are read from the screen or filled at the last minute. Do not say a number on stage that is still a placeholder. Open placeholders: LIVE_WINNER, LIVE_DIRECTION and ROUND_SECONDS (read them from the live round).

Events follow the split in `backend/config.py`:

- Calibrate on event 32. Night, infrared. The basement gets wet. Peak 47 mm.
- Hold out event 20. Day. The basement gets wet. Peak 27 mm.
- Dry check on event 21. The basement stays dry.

Words to use on stage:

- "The untuned template" is the published FloodX SWMM model with its default settings. Argon did not set its knobs. Do not call it "Argon's guess".
- "The frozen model" is the model after calibration, locked and hashed before the reveal.
- "The researchers' sensor-based calibrations" are the 40 calibrations the FloodX team published, which used all three water-level sensors.

Allowed headline: "Using only camera video, Backflow corrected a flood model about as well as the researchers' own sensor-based calibrations, and its prediction held on a flood it never saw."

Do not say: "better than the researchers", "first ever", or "predicted the flood from video alone". The inflow is a measured input, and the model structure comes from the researchers' published template.

Final numbers, held-out event 20, basement:

| Model | Mean error, mm | Peak error, mm | First-water error, s | Predicts the flood? |
|---|---|---|---|---|
| Untuned template | 33.5 | +65 | -20 | Yes, too deep |
| Video-judged | 5.9 | -5 | +50 | Yes |
| Still-frame variant | 3.8 | -8 | +50 | Yes |
| Researchers' sensor calibrations (median of 40) | 5.3 | +7 | not scored | Yes |
| Plain optimiser | 4.0 | -27 (peak 0 vs 27) | never wet | No |

Lead with the peak and wet or dry. The basement is dry most of the time, so mean error alone misleads.

## (a) Spoken script, 3 minutes

Key: LIVE means it runs in front of the judges. RECORDED means a labelled clip from the calibration run earlier today.

Before you start: open a second terminal with `python -m backend.loop --live calib_video` typed and ready. Press Enter at 0:00. The round takes 45 to 80 seconds and its verdict is shown at about 1:30.

### Segment 1. The question (0:00 to 0:20). RECORDED footage, no narration for the first 5 seconds

| Time | On screen | Line |
|---|---|---|
| 0:00 | Camera 5 clip, event 32: a dark basement at night, infrared. Water comes up through the floor drain and spreads. Press Enter on the live round in the second terminal. | (Let it play for 5 seconds.) |
| 0:05 | Same clip. | "This is a real flood at a training site in Switzerland. The water is not coming in the door. It is coming up the drain." |
| 0:11 | Same clip. | "Cities plan drains with computer models. Those models are often never checked against a real flood, because sensors cost money. Cameras are cheap." |
| 0:17 | Same clip. | "So we asked: can an AI calibrate a flood model just by watching video? A round is already running in the background." |

### Segment 2. How it learned (0:20 to 1:15). RECORDED, labelled "Recorded earlier today"

| Time | On screen | Line |
|---|---|---|
| 0:20 | The 3D scene of the site, rotating once. Small caption: "850 lines of Three.js, one pass". | "Argon wrote this 3D scene from the site plan, in one pass. About 850 lines of code. It took eight and a half minutes." |
| 0:30 | Real dry camera 5 frame beside the first render, then the render after the rewrite and patch. The drain, rod and cables appear. | "Then it compared its scene with the real camera. It noticed its own scene hid the floor drain. It rewrote its scene code, about 90 seconds, so the drain shows. Then it fixed the camera. This happened in every run." |
| 0:42 | Note on screen: "Water comes only from the simulation." | "The water in this scene comes only from a standard drainage simulation, called SWMM. Argon cannot paint water." |
| 0:48 | Real frame beside the untuned template's render. The render basement is much deeper. | "Here is the untuned template. It floods the basement two and a half to three times too deep. It even floods it on a day when the real basement stayed dry." |
| 0:57 | Round 1: three renders labelled "sewer", "door", "both", next to the real frames. The door column shows a dry floor. | "Round one asks how the water gets in. The door idea never wets the basement. The video shows water rising through the floor drain. Argon picks the sewer." |
| 1:05 | The recorded judge video: 2x2 grid, real top left, A, B, C beside it, playing as a time-lapse. | "After that, each round is a video. Three candidate floods, rendered from the real camera's view, next to the real footage. Argon watches the whole thing and picks the best match. Six rounds like this took about six minutes." |

### Segment 3. The live round (1:15 to 1:55). LIVE, started at 0:00

| Time | On screen | Line |
|---|---|---|
| 1:15 | The second terminal, with the round finishing. | "This round started when I started talking. Three simulations ran. Each was rendered from the real camera's view." |
| 1:22 | Click "What Argon watched". The exact video plays: real top left, A, B, C. | "This is the exact video Argon watched. Real footage, and three renders. No numbers. No sensor data." |
| 1:30 | Argon's reply: moments, a winner and a direction, for example "less water". | (Read one moment's evidence aloud. Then:) "It picked [LIVE_WINNER] and says the next step is [LIVE_DIRECTION]." |
| 1:42 | Round time on screen. | "That round took [ROUND_SECONDS] seconds. The network is the slow part, so the time changes from run to run. Argon only judges. My code moves the settings." |
| 1:50 | Calibration view, round strip. | "The full run did six rounds like this." |

Notes on the live round:

- The round takes 45 to 80 seconds. Start it at 0:00 so the verdict is ready by 1:30.
- If it is still running at 1:30, say: "While this finishes: the model I use next was frozen earlier, and its hash is on screen. This round does not change it." Then move on.
- If Wi-Fi is down, run the same command with `ARGON_CACHE=replay` and say: "The Wi-Fi is down, so this replays Argon's recorded answer from rehearsal."
- If the round fails, show the same round from the rehearsal and say so plainly: "That did not finish. Here is the same step from this morning."

### Segment 4. The test (1:55 to 2:45). LIVE scoring, on models frozen before the demo

| Time | On screen | Line |
|---|---|---|
| 1:55 | Reveal view. Two cards: "Untuned template" and "Frozen model", each with a short hash. | "Here is the test. Two models. The untuned template, and the model after watching one flood. Both are locked. Here are their fingerprints." |
| 2:03 | Both predict event 20 from inflow only. Renders play. | "Now they predict a different flood, in daylight. They get only how much water was poured in. Nothing in the loop has seen this flood's video or any sensor." |
| 2:10 | Press "Reveal sensors". Held-out video beside both renders. Gauge curves draw in. | "Now the reveal. The real video, and the water-level sensors the loop never saw." |
| 2:16 | Error table, basement rows. | "The real peak was 27 millimetres. The untuned model was 65 too deep. After one flood video: 5 millimetres off. Average error fell from 34 to 6." |
| 2:26 | Researchers' row. | "The researchers who built this site published 40 calibrations using all their water sensors. Run in our model, the median average error is 5. Same accuracy, and we used video only." |
| 2:34 | Plain optimiser row, with its flat dry line. | "We also fitted a plain optimiser to the timeline Argon read. Its average error is 4, which looks great. But it predicts a dry basement. The real one flooded. Mean error alone hides that." |
| 2:41 | The first-water row stays on screen. | "One thing got worse. The first water comes 50 seconds late. Before, it was 20 seconds early." |

### Segment 5. Why it matters (2:45 to 3:00). LIVE, presenter only

| Time | On screen | Line |
|---|---|---|
| 2:45 | Back to the basement video, paused. | "Using only camera video, Backflow corrected a flood model about as well as the researchers' own sensor-based calibrations, and its prediction held on a flood it never saw." |
| 2:53 | Same. | "The US Geological Survey already runs about 1,400 cameras at river gauges. The video exists. Backflow is one way to use it. Thank you." |

## (b) Judge questions

**1. Why give Argon video instead of numbers?**
Because the point is to calibrate where there are no sensors. If Argon saw sensor numbers, we would just have rebuilt normal calibration. A 2018 review found no good methods for calibrating with crowdsourced images or video. So in every judged round Argon watches a video of the real flood beside three renders. It never sees simulation numbers or gauges. It also never sets a number in those rounds. It picks which render matches, and our code moves the settings. And video carries enough signal. In night infrared video, Argon found when the basement floor got wet within about 10 seconds of the sensor. It saw water rising in the floor drain about 50 seconds before the sensor registered anything. We used the gauge only to check this.

**2. Why a staged site and not a real street?**
Because we need the truth to score against. FloodX is 22 staged floods at a Swiss training site, recorded by Eawag in 2016, with fixed cameras, measured inflow and water-level sensors. On a real street we could not prove the model got better. Here we can.

**3. Would it work on a real street?**
We have not shown that. A real street needs a camera with a known view, rough geometry from plans, and an estimate of how much water came in. Real sites will also have less data than this one. The closest real setting is the roughly 1,400 cameras USGS runs at river gauges, where flow is already measured. That is the next test, not a claim.

**4. How do you know it did not cheat?**
The gauge data is read only by the evaluator and the reveal. Nothing in the loop imports them. The window we render is picked around the wetting time Argon read from the video, not from a gauge. The held-out video stays hidden until the models are frozen and hashed. Water in the scene is set by a locked harness, from simulation output only. A scene fix can move where water may sit, such as the drain or the floor slope. It cannot change how much water there is. The loop can change the entry path and three settings: the outlet coefficient, the width of pipe p7 and the roughness of pipe p3. All of this is in the repo. One honest caveat: we picked those three settings with an offline sensitivity analysis that included the held-out event. The values came from video only.

**5. Why Managed Agents?**
Each hypothesis is a longer job than one call. We ran SWMM inside Managed Agents sandboxes, with gemini-4-argon as the agent model. Three hypotheses ran in parallel, about 225 seconds each. Each sandbox has its own files and no gauge data, so the workers cannot see the answer or touch each other's work. The live round is one judge call on local simulations, so it does not need them.

**6. What is new compared with Vid2Sid?**
Vid2Sid had a vision model compare sim and real robot videos and suggest physics changes. We did not invent that idea, and we say so. Moy de Vitry and colleagues calibrated SWMM at this same site in 2020, using video signals they built by hand. HydroAgent names a vision checker as future work. What we add for drainage: Argon writes the 3D scene from the plan, fixes it against the real camera and rewrites its own scene code when it hides something; water comes only from the simulation, so Argon cannot paint it; Argon watches a video of rendered candidates beside the real flood instead of guessing numbers; and the result is scored on a hidden flood, against sensors the loop never saw.

**7. What if the untuned template was already good?**
It was not. It floods the basement 2.5 to 3 times too deep: 120 mm against 47 mm on event 32, and 92 mm against 27 mm on event 20. It also wets the basement on dry event 21. So there is a real error to fix. We report the gain as measured. The mean error fell from 33.5 to 5.9 mm and the peak error from +65 to -5 mm. The first water got later, not better: 50 seconds late, against 20 seconds early.

**8. Cost, speed, and what if the Wi-Fi drops?**
Writing the scene is a one-time cost: 514 seconds, about 10,500 output tokens and 29,000 thinking tokens. One SWMM run of a full event takes about 4 seconds on a laptop. The video-judged run took six rounds, about six minutes: the structure round took about 2 minutes, and each judged round 46 to 55 seconds (about 30 seconds to simulate and render, 8 to 17 seconds for the judge call). One live round takes 45 to 80 seconds, because API latency varies, so we start it at the beginning of the pitch. By our token count (about 90k input and 42k output tokens, scene generation included), a full run costs under one dollar at the listed Standard price. If the Wi-Fi drops, the demo has a replay mode. It plays back Argon's recorded answers from rehearsal, and it fails loudly if an answer is missing.

**9. Did you beat the researchers?**
No, and we do not say that. Video-only calibration reached about the same accuracy as their sensor-based calibrations. They published 40 calibrations that used all three water-level sensors (Zenodo 3475502). Run in our model on the same hidden flood, the median mean error is 5.3 mm (best 3.5 mm) and the median peak error is +6.9 mm. Our video run gives 5.9 mm and -5 mm. Two caveats. Their settings came from their simpler template and we ran them in our model, with our storage-curve fix. And it is one hidden flood.

**10. Is that a prediction from video alone?**
No. The inflow is a measured input. The model structure comes from the researchers' published template. What the video does is correct the settings of that model, so that it holds on a flood it never saw.

**11. A plain optimiser got a lower mean error. Why not use that?**
Its mean error is 4.0 mm, but it predicts that the basement stays dry. The real basement flooded to 27 mm. The peak error is -27 mm. The basement is dry most of the time, so a model that predicts no flood scores well on mean error. An engineer needs the peak and whether the basement floods. That is why we lead with peak and wet or dry.

**12. Why doesn't Argon set the numbers itself?**
We tried. In an engineer experiment, Argon watched a 10-minute side-by-side video, the plan PDF and the SWMM input file. It correctly named the two settings that matter: pipe p7 is too wide and the outlet valve is too restrictive. A brute-force sensitivity analysis found the same two. But when it set 8 values at once, the result on the hidden flood was worse, about 50 mm mean error. Argon is good at diagnosing and judging, and worse at writing exact numbers. So the loop lets Argon judge, and the code moves the settings.

## (c) 1-minute submission video

Total: 60 seconds. Read the voice-over at a calm pace. Each line fits its shot.

| # | Time | Shot | Voice-over |
|---|---|---|---|
| 1 | 0:00 to 0:06 | Night infrared basement clip, event 32. Water rises through the floor drain. | "This basement is flooding from below. The water is coming up the drain." |
| 2 | 0:06 to 0:12 | Same clip, title "Backflow" fades in. | "Flood models are often never checked against real floods. Sensors are expensive. Video is not." |
| 3 | 0:12 to 0:19 | The 3D scene. Then the dry real frame beside the render, the drain appearing after the rewrite. | "Argon wrote this 3D scene from the site plan. It saw its scene hid the drain, rewrote its own code, and fixed the camera." |
| 4 | 0:19 to 0:26 | Real frame beside the untuned template's render. Deep water in the render. | "The water comes only from a drainage simulation. Untuned, it floods the basement about three times too deep." |
| 5 | 0:26 to 0:36 | The judge video: 2x2 grid, real, A, B, C, playing as a time-lapse. Winner highlighted. | "Each round, Argon watches three simulated floods beside the real one, and picks the best match. Video only. No sensor data." |
| 6 | 0:36 to 0:48 | Two locked cards with hashes. Reveal: held-out daytime video, gauge curves, error table with the researchers' row. | "Then we lock the model and test it on a flood it never saw. Untuned, the peak is 65 millimetres too deep. After one flood video, 5 off. The researchers' own sensor-based calibrations: about the same." |
| 7 | 0:48 to 0:55 | The plain optimiser's flat dry line against the measured basement curve. | "A plain optimiser has a low average error, but it predicts a dry basement. The real one flooded." |
| 8 | 0:55 to 1:00 | Basement clip, paused. Repo URL. | "Using only video, a flood model corrected about as well as sensors. The cameras already exist." |
