# Site value sources

Elevations are metres above datum (FloodX local datum, e.g. 418.44). Lengths are metres.

| Key | Value | Source |
|---|---|---|
| weir_crest_m | 0.51 | Height above s3 invert (419.94). SWMM template w1 CrestHt 0.51. Technical details Table 8: w1 elevation 420.45 to 420.50 (0.51 to 0.56 above invert). |
| basement_floor_m | 418.44 | Technical details Table 1: S6 invert 418.44; Table 3 m3 cover 418.44. Plan shows 418.47 spot levels. |
| pipe_p7_diameter_m | 0.1472 | Technical details Table 6 (P7 inner diameter 147.2 mm); template p7 Geom1. |
| pond_area_m2 | 8.5 | Derived from Table 2 level-volume for s3: 2.13 m3 at 0.25 m (8.5 m2); 0.25 to 0.7 m gives 9.0 m2. Template curve uses 9.2 to 12.8 m2 (not used). |
| basement_floor_slope | 0.0 | Plan 1:50: basement spot levels all -2.37 (418.47). Flat. |
| basement_drain_xy | [-0.37, -2.28] | ASSUMED proxy: manhole m3 offset from s6 in SWMM template coordinates (schematic, east/north). Not a surveyed floor drain. |
| door_threshold_m | 419.8 | NOT DOCUMENTED. Elevation assumed 4 cm above s4 invert (419.76) so the door hypothesis is testable. Neither the technical details nor the plan list a door sill. Treat as a placeholder to be fixed from video. |

Other values the SWMM build uses are listed in `backend/sim.py` (FIXED_DEFAULTS). cd_m2, cd_v2, seepage, id_1 are not defined in the cq-analysis repo; they are assumptions.
