# Pitch

Gemini 4 Argon SF hackathon, 25 October 2026. Live demo: 3 minutes, no slides. Submission video: 1 minute.

Placeholders in square brackets are filled after the final run. Do not say a number on stage that is still a placeholder.

Events follow the split in `backend/config.py`:

- Calibrate on event 32. Night, infrared. The basement gets wet. Peak 47 mm.
- Hold out event 20. Day. The basement gets wet. Peak 27 mm.
- Dry check on event 21. The basement stays dry.

Words to use on stage:

- "The untuned template" is the published FloodX SWMM model with its default settings. Argon did not set its knobs. Do not call it "Argon's guess".
- "The frozen model" is the model after calibration, locked and hashed before the reveal.

## (a) Spoken script, 3 minutes

Key: LIVE means it runs in front of the judges. RECORDED means a labelled clip from the calibration run earlier today.

### Segment 1. The question (0:00 to 0:20). RECORDED footage, no narration for the first 5 seconds

| Time | On screen | Line |
|---|---|---|
| 0:00 | Camera 5 clip, event 32: a dark basement at night, infrared. Water comes up through the floor drain and spreads. | (Let it play for 5 seconds.) |
| 0:05 | Same clip. | "This is a real flood at a training site in Switzerland. The water is not coming in the door. It is coming up the drain." |
| 0:11 | Same clip. | "Cities plan drains with computer models. Those models are often never checked against a real flood, because sensors cost money. Cameras are cheap." |
| 0:17 | Same clip. | "So we asked: can an AI calibrate a flood model just by watching video?" |

### Segment 2. How it learned (0:20 to 1:15). RECORDED, labelled "Recorded earlier today"

| Time | On screen | Line |
|---|---|---|
| 0:20 | The 3D scene of the site, rotating once. Small caption: "850 lines of Three.js, one pass". | "Argon wrote this 3D scene from the site plan, in one pass. About 850 lines of code. It took eight and a half minutes." |
| 0:30 | Contact sheet: real dry camera 5 frame beside the first render. Then the patched render. The camera view shifts and the drain moves into place. | "Then it compares the real dry camera frame with its render. It sends back small fixes: move the camera, move the drain, set the floor slope. They apply at once. You can see the view snap into line." |
| 0:42 | Note on screen: "Water comes only from the simulation." | "The water in this scene comes only from a standard drainage simulation, called SWMM. Argon cannot paint water." |
| 0:48 | Real frame beside the untuned template's render. The render basement is much deeper. | "Here is the untuned template. It floods the basement two and a half to three times too deep. It even floods it on a day when the real basement stayed dry." |
| 0:57 | Round 1: three renders side by side, labelled "sewer", "door", "both", next to the real frames. The door column shows a dry floor. | "Round one asks how the water gets in. We simulate three ideas: through the sewer, through the door, or both. The door idea never wets the basement. The video shows water rising through the floor drain. Argon picks the sewer." |
| 1:07 | Round 2 contact sheet: real frames, then three candidates: current, less, more. Argon's winner circled. | "After that, each round tries three settings: the current one, a bit less, a bit more. Argon only sees pictures. It picks the one that matches, and the search narrows around it." |

### Segment 3. One live round (1:15 to 1:55). LIVE

| Time | On screen | Line |
|---|---|---|
| 1:15 | Terminal: `python -m backend.loop --live <name>`. Press Enter. | "Now one round, live, from the frozen state." |
| 1:20 | Three simulations finish. Renders appear. | "Three simulations run. Each is rendered from the real camera's view, at five moments around when the floor gets wet." |
| 1:28 | The contact sheet: real frame on the left, candidates A, B, C to the right, one row per moment. | "This is all Argon gets. Real frames and renders. No numbers. No sensor data." |
| 1:35 | Argon's reply: one verdict per row, a winner and a direction, for example "less water". | (Read one row's evidence aloud. Then:) "It picked [LIVE_WINNER] and says the next step is [LIVE_DIRECTION]." |
| 1:45 | Round time on screen. | "That round took [ROUND_SECONDS] seconds. The judge call alone is about 10 seconds." |
| 1:50 | Calibration view, round strip. | "The full run did [N_ROUNDS] rounds like this." |

Note: the target for the live round is under 40 seconds. If it is still running at 1:50, say: "While this finishes: the model I use next was frozen earlier, and its hash is on screen. This round does not change it." Then move on. If Wi-Fi is down, run the same command with `ARGON_CACHE=replay` and say: "The Wi-Fi is down, so this replays Argon's recorded answer from rehearsal." If the round fails, show the same round from the rehearsal and say so plainly: "That did not finish. Here is the same step from this morning."

### Segment 4. The test (1:55 to 2:45). LIVE scoring, on models frozen before the demo

| Time | On screen | Line |
|---|---|---|
| 1:55 | Reveal view. Two cards: "Untuned template" and "Frozen model", each with a short hash. | "Here is the test. Two models. The untuned template, and the model after watching one flood. Both are locked. Here are their fingerprints." |
| 2:05 | Both predict event 20 from inflow only. Renders play. | "Now they predict a different flood, in daylight. They get only how much water was poured in. Nothing in the loop has seen this flood's video or any sensor." |
| 2:15 | Press "Reveal sensors". Held-out video beside both renders. Gauge curves draw in: measured, untuned, frozen, baseline. | "Now the reveal. The real video, and the water-level sensors the loop never saw." |
| 2:23 | Error table. | "Untuned: basement peak off by [BLIND_ERROR_MM] millimetres. After one flood: [INFORMED_ERROR_MM]. First water: [BLIND_ONSET_S] seconds off, then [INFORMED_ONSET_S]." |
| 2:33 | Baseline row. | "We also ran a plain optimiser, fitted to the timeline Argon read from the video. Same hidden sensors. It got [BASELINE_ERROR_MM]." |
| 2:40 | Any row that got worse stays on screen. | "[FAILURE_LINE, for example: The pond level got slightly worse. We show that too.]" |

### Segment 5. Why it matters (2:45 to 3:00). LIVE, presenter only

| Time | On screen | Line |
|---|---|---|
| 2:45 | Back to the basement video, paused. | "Sewer water in basements is a common problem. Drainage codes say: calibrate on one flood, check on another. Most models skip that, because sensors cost money." |
| 2:53 | Same. | "The US Geological Survey already runs about 1,400 cameras at river gauges. The video exists. Backflow is one way to use it. Thank you." |

## (b) Judge questions

**1. Why give Argon pictures instead of numbers?**
Because the point is to calibrate where there are no sensors. If Argon saw sensor numbers, we would just have rebuilt normal calibration. A 2018 review found no good methods for calibrating with crowdsourced images or video. So in every judged round Argon sees only real frames beside renders. It never sees simulation numbers or gauges. It also never sets a number in those rounds. It picks which render matches, and our code moves the settings. And pictures carry enough signal. In night infrared video, Argon found when the basement floor got wet within about 10 seconds of the sensor. It saw water rising in the floor drain about 50 seconds before the sensor registered anything. We used the gauge only to check this.

**2. Why a staged site and not a real street?**
Because we need the truth to score against. FloodX is 22 staged floods at a Swiss training site, recorded by Eawag in 2016, with fixed cameras, measured inflow and water-level sensors. On a real street we could not prove the model got better. Here we can.

**3. Would it work on a real street?**
We have not shown that. A real street needs a camera with a known view, rough geometry from plans, and an estimate of how much water came in. Real sites will also have less data than this one. The closest real setting is the roughly 1,400 cameras USGS runs at river gauges, where flow is already measured. That is the next test, not a claim.

**4. How do you know it did not cheat?**
The gauge data is read only by the evaluator and the reveal. Nothing in the loop imports them. The moments we render are picked around the wetting time Argon read from the video, not from a gauge. The held-out video stays hidden until the models are frozen and hashed. Water in the scene is set by a locked harness, from simulation output only. A scene fix can move where water may sit, such as the drain or the floor slope. It cannot change how much water there is. There are only 3 knobs: the entry path, one weir coefficient and one drain coefficient. All of this is in the repo.

**5. Why Managed Agents?**
Each hypothesis is a longer job than one call. We ran SWMM inside Managed Agents sandboxes, with gemini-4-argon as the agent model. Three hypotheses ran in parallel, about 225 seconds each. Each sandbox has its own files and no gauge data, so the workers cannot see the answer or touch each other's work. The live round is one judge call on local simulations, so it does not need them.

**6. What is new compared with Vid2Sid?**
Vid2Sid had a vision model compare sim and real robot videos and suggest physics changes. We did not invent that idea, and we say so. Moy de Vitry and colleagues calibrated SWMM at this same site in 2020, using video signals they built by hand. HydroAgent names a vision checker as future work. What we add for drainage: Argon writes the 3D scene from the plan and aligns it to the real camera; water comes only from the simulation, so Argon cannot paint it; Argon judges rendered candidates instead of guessing numbers; and the result is scored on a hidden flood, against sensors the loop never saw. As far as we know, no one has calibrated an urban drainage model this way and scored it on a hidden flood.

**7. What if the untuned template was already good?**
It was not. It floods the basement 2.5 to 3 times too deep: 120 mm against 47 mm on event 32, and 78 mm against 27 mm on event 20. It also wets the basement on dry event 21. So there is a real error to fix. We report the gain as measured. If the frozen model had not improved, the table would say so. [If results show a small or mixed gain, say it here in one sentence.]

**8. Cost, speed, and what if the Wi-Fi drops?**
Writing the scene is a one-time cost: 514 seconds, about 10,500 output tokens and 29,000 thinking tokens. One SWMM run of a full event takes about 4 seconds on a laptop. One judge call takes about 10 seconds. One live round, with 3 simulations, renders and one judge call, took [ROUND_SECONDS] seconds. The full calibration run took [RUN_MINUTES] minutes and cost about [RUN_COST_USD] dollars. If the Wi-Fi drops, the demo has a replay mode. It plays back Argon's recorded answers from rehearsal, and it fails loudly if an answer is missing.

## (c) 1-minute submission video

Total: 60 seconds. Read the voice-over at a calm pace. Each line fits its shot.

| # | Time | Shot | Voice-over |
|---|---|---|---|
| 1 | 0:00 to 0:07 | Night infrared basement clip, event 32. Water rises through the floor drain. | "This basement is flooding from below. The water is coming up the drain." |
| 2 | 0:07 to 0:13 | Same clip, title "Backflow" fades in. | "Flood models are often never checked against real floods. Sensors are expensive. Video is not." |
| 3 | 0:13 to 0:21 | The 3D scene. Then the dry real frame beside the render, and the render snapping into line. | "Argon wrote this 3D scene from the site plan. Then it compared it with the real camera and fixed the view." |
| 4 | 0:21 to 0:28 | Real frame beside the untuned template's render. Deep water in the render. | "The water comes only from a drainage simulation. Untuned, it floods the basement about three times too deep." |
| 5 | 0:28 to 0:36 | Round 1: sewer, door, both. The door column stays dry beside the real drain frame. | "Which way does the water get in? The door idea never wets the floor. The video shows the drain. Argon picks the sewer." |
| 6 | 0:36 to 0:44 | A later contact sheet: current, less, more. Winner circled. | "Each round, Argon picks the render that matches the video. Pictures only. No sensor data." |
| 7 | 0:44 to 0:52 | Two locked cards with hashes. Reveal: held-out daytime video, gauge curves, error table. | "Then we lock the model and predict a new flood. Against sensors it never saw: untuned, off by [BLIND_ERROR_MM] millimetres. After one flood, [INFORMED_ERROR_MM]." |
| 8 | 0:52 to 1:00 | Basement clip, paused. Repo URL. | "The cameras already exist. Backflow is one way to use them." |
