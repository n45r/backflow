# Gate A results (2026-10-25)

## Downloads
- calib/calib.zip md5 67170114156066fb34fb727245de6ff9 OK (events 25-34)
- monitor/monitor.zip md5 afbf083d140bcfd7e079d83f3f11d678 OK (events 14-23, 25-35; 25-34 identical to calib; no 24)
- meta_v2/: experiment_list.csv, datasource_list.csv, datasource_files.csv + READMEs (fetched per member via Zenodo /container)
- video_meta/offsets.txt (camera offsets per session); cq-analysis/ and swmm_calibration/ (shallow clones)
- Full table: gate_a_events.csv (scripts/gate_a_events.py). Wet = s6 > 5 mm for >= 30 s.

## Events with a wet basement
| id | session | light | s6 peak mm | first wet | s3 peak mm | inflow m3 | src |
|---|---|---|---|---|---|---|---|
| 19 | 161006A | day | 41.7 | 14:10:39 | 592 | 44.5 | processed; "valves not configured correctly" |
| 20 | 161006A | day | 27.2 | 14:35:47 | 564 | 31.7 (logi clipped; minilog 34.4; full rise in cq all_ file: 35.5) | processed |
| 24 | 161006A | day | 164.9 | 16:36:57 | 621 | 76.5 | cq-analysis all_ files only |
| 32 | 161006B | night | 46.8 | 21:21:06 | 585 | 62.2 | processed (calibration set) |
| 36 | 161007A | day | 58.0 | 12:50:12 | 610 | 41.4 | all_ only; m2 cover on, dam breached |
| 37 | 161007A | day | 179.9 | 13:17:05 | 471 | 192 | all_ only; tank emptying |
| 2,5,6,12 | 161005A/B | day/dusk | 21-129 | | n/a | n/a (no logi inflow before 6/10 12:15) | all_ only |
All other processed events peak s6 <= 7.6 mm (22) and mostly 0-2.6 mm.

## Configuration columns (experiment_list.csv, exact names)
id, start_datetime, end_datetime, duration, p1_q_mid_promag_high_resolution, waterpilot_high_resolution,
v4_valve_opening, description_short, description_detailed, initial_conditions, env_lighting, env_wind_level,
sensor_comments, hydraulic_network_comments, experiment_quality.
No columns exist for notches, manhole covers or grates. Config lives in v4_valve_opening (4 / 8 / Variable),
initial_conditions ("Pipes p3 and p4 full|empty") and free text hydraulic_network_comments
(bad valves on 2 and 19; "Repetition of previous experiment" on 20; rope tethering on 22; m2 manhole cover on 35-37).
Events 14-34: v4 = 8; events 18-25, 27-34 have p3/p4 empty.

## Cameras
Zenodo record 1039631 has s3_cam1_instar_* and s6_cam5_instar_* tars for all six sessions.
Event->session mapping is inferred (date + time gap + night lighting); tar contents not inspected. Event 13 says "no camera recording".

## Recommendation (all v4=8, pipes p3/p4 empty, no hydraulic comment)
- Calibration (wet): 32 (161006B, calibration grade, night with IR/flood light)
- Dry check: 31 (same session, night, 23.9 m3, peak s6 0) or 21/28 (day)
- Held-out (wet): 20 (161006A, day, same "Multiple big shots" protocol; 31.7-35.5 m3 vs 62.2 m3)
- Alternative held-out with a different inflow shape: 24 (slow event with peak, 76.5 m3), but it is absent from the processed zips.
Caveat: 20 and 32 differ in lighting (day vs night).

## SWMM template (cq-analysis swmm_model_template.inp)
- Storage: s3 (pond), s6 (basement, 418.44, tabular), s5, s2 (tank), s4, m1, m2, m3 (417.44)
- Junctions 4, 9, v9, v7, virt2, v6, virtual1, virt3, 28, 29, v4, v8, 1; outfall 5
- Conduits p7 (9->m3), p5_b, p5, c2, p8, c1, p3, c3, c4, p2, p6, 1, 2
- Orifices r5 (s6<->m3 BOTTOM), r6, r4, r3, r2, r1, v2; weirs w1 (s3->virt2, crest 0.51), w3, w4, w2
- Basement: only link is r5 to m3 (sewer backflow). No surface/door overflow path to s6.
- Placeholders ($ string.Template): sim_*; forcing_data_file; r_px, r_p3, cd_m1, cd_m2, cd_m3, cd_r4, cd_r6, cd_v2, cd_w1,
  seepage; id_1, id_4, id_9, id_v4, id_v7, id_v8, id_v9, id_m1, id_m2, id_m3, id_s5.
- cq-analysis settings.py actually uses swmm_model_template_simple.inp. No calibrated values are published.
  cd_m2, cd_v2, seepage, id_1 are defined nowhere (assumed 0.6, 0.6, 0, id_m2+0.21).

## SWMM run (scripts/gate_a_swmm.py; bound midpoints; outputs in runs/gate_a/)
| event | runtime | continuity err (.rpt) | s6 peak model/meas mm | s3 peak model/meas mm |
|---|---|---|---|---|
| 20 | 3.5 s | 3.34 % | 78 / 27 | 582 / 564 |
| 32 | 4.2 s | 3.38 % | 120 / 47 | 603 / 585 |
| 21 (dry) | 3.6 s | 2.14 % | 54 / 2 | 451 / 512 |
Uncalibrated model wets the basement in dry event 21: it fails the dry check until calibrated.
pyswmm's flow_routing_error returned 0.0; the .rpt value is used.
