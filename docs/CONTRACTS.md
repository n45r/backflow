# Contracts

How the parts connect. Change this file first if an interface must change.

## Events
- Clean wet-basement events with inflow: 20 (day, session 161006A, basement peak 27 mm) and 32 (night, session 161006B, 47 mm).
- Dry check: 21 (day, 161006A). Alternatives 28, 31.
- Default split (configurable in `backend/config.py`): calibrate on 20, hold out 32, dry check 21.
- Time: seconds from the event start in experiment_list.csv, on the dataset reference clock. Video frames are mapped with the camera offsets (reference = camera clock minus signed offset).

## Folders
- `data/` raw downloads, prepared clips and frames (git-ignored).
- `runs/<run_id>/` simulation inputs and outputs (git-ignored).
- `evaluation/` gauge data; only the evaluator reads it (git-ignored).
- `site/site.json` shared geometry. `site/params.json` hydraulic knobs.

## site/site.json (shared geometry, metres)
```json
{
  "weir_crest_m": 0.51,
  "door_threshold_m": null,
  "basement_floor_m": null,
  "pipe_p7_diameter_m": 0.1472,
  "pond_area_m2": null,
  "basement_floor_slope": 0.0,
  "basement_drain_xy": [0, 0]
}
```
Values are filled from the FloodX technical documents and the SWMM template. `null` means not yet set. Both the SWMM builder and the 3D scene read this file.

## site/params.json (hydraulic knobs, at most 3)
```json
{ "basement_path": "sewer", "weir_cd": null, "orifice_cd": null }
```
`basement_path` is one of `sewer`, `door`, `both`.

## Simulation output: runs/<run_id>/depths.json
```json
{
  "event": 20,
  "dt_s": 10,
  "t": [0, 10, 20],
  "depth_m": { "s3": [], "s6": [], "m2": [], "m3": [] },
  "continuity_error_pct": 2.1,
  "inputs": { "site_sha": "", "params_sha": "", "template_sha": "" }
}
```
Depth is metres above each node's invert. This is the only water data the scene ever receives.

## 3D scene module (written and patched by Argon)
File: `web/scene/<version>.js`, an ES module.
```js
export default function build(THREE, root, site) {
  // add static geometry to `root` (a THREE.Group)
  return {
    cameras: { cam1: { position: [x, y, z], lookAt: [x, y, z], fov: 60 },
               cam5: { position: [x, y, z], lookAt: [x, y, z], fov: 70 } },
    water: { pond:     { outline: [[x, z], ...], base_y: 0 },
              basement: { outline: [[x, z], ...], floor_y: 0, slope: 0.0, drain_xz: [x, z] },
              manhole_m2: { center: [x, z], radius: 0.4, base_y: 0 } },
    materials: { water: { color: "#3a7bd5", opacity: 0.6 } }
  };
}
```
The scene module never receives depths. It may describe where water can sit and how water looks, but it cannot place water.

## Host harness (locked, `web/harness.js`)
Owns the renderer, the water meshes and the timeline. Argon cannot edit it.
- `await window.loadScene(url)` builds the scene from a module.
- `window.loadDepths(json)` takes a depths.json object.
- `window.setStep(t)` sets water from depths at time t: pond and manhole as planes at base_y + depth; basement as the intersection of a level plane with the sloped floor, so the wet area grows with depth.
- `window.setCamera(name)` switches to `cam1` or `cam5`.
- `window.ready` is true when the scene is loaded and a frame has rendered.

## Renderer (`backend/render.py`)
`render(scene_url, depths_path, cam, times_s, out_dir) -> list[png_path]`, using a warm Playwright tab.

## Real frames (`backend/frames.py`)
`real_frames(event, cam, times_s, out_dir) -> list[jpg_path]`, from prepared clips on the reference clock.

## Contact sheet (`backend/contact.py`)
`contact_sheet(real_paths, render_paths, labels, out_path) -> png_path`: one row per time, real left, render right, time label on each row.

## Gauges (`backend/evaluator.py`, evaluator only)
`score(event, depths_path) -> dict` with per-gauge MAE, peak error and onset timing error for s3 and s6. Nothing in the loop may import this module.
