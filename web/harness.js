import * as THREE from 'three';

const W = 854, H = 480;
const params = new URLSearchParams(location.search);
const hudEl = document.getElementById('hud');
const showHud = params.get('hud') === '1';
if (showHud) hudEl.style.display = 'block';

const renderer = new THREE.WebGLRenderer({ antialias: true, preserveDrawingBuffer: true });
renderer.setPixelRatio(1);
renderer.setSize(W, H);
renderer.setClearColor(0x9fb7c9);
document.body.appendChild(renderer.domElement);

const scene = new THREE.Scene();
scene.background = new THREE.Color(0x9fb7c9);
scene.add(new THREE.HemisphereLight(0xffffff, 0x556070, 1.0));
const sun = new THREE.DirectionalLight(0xffffff, 1.4);
sun.position.set(8, 20, 6);
scene.add(sun);

let sceneRoot = null;
let waterRoot = null;
let spec = null;
let camDefs = {};
let camera = new THREE.PerspectiveCamera(60, W / H, 0.05, 500);
let camName = null;
let sceneVersion = '-';
let depths = null;
let curT = 0;
let nodeMap = { pond: 's3', basement: 's6', manhole_m2: 'm2' };
const meshes = {};

function waterMaterial() {
  const m = (spec && spec.materials && spec.materials.water) || {};
  return new THREE.MeshStandardMaterial({
    color: new THREE.Color(m.color || '#3a7bd5'),
    opacity: m.opacity ?? 0.6,
    transparent: true,
    roughness: 0.15,
    metalness: 0.1,
    side: THREE.DoubleSide,
    depthWrite: false,
  });
}

function polyGeometry(pts, y) {
  const v2 = pts.map(p => new THREE.Vector2(p[0], p[1]));
  const tris = THREE.ShapeUtils.triangulateShape(v2, []);
  const pos = [];
  for (const p of pts) pos.push(p[0], y, p[1]);
  const g = new THREE.BufferGeometry();
  g.setAttribute('position', new THREE.Float32BufferAttribute(pos, 3));
  g.setIndex(tris.flat());
  g.computeVertexNormals();
  return g;
}

// Sutherland-Hodgman: clip subject polygon by a convex clip polygon.
function clipConvex(subject, clip) {
  let area = 0;
  for (let i = 0; i < clip.length; i++) {
    const a = clip[i], b = clip[(i + 1) % clip.length];
    area += a[0] * b[1] - b[0] * a[1];
  }
  const sgn = area >= 0 ? 1 : -1;
  let out = subject;
  for (let i = 0; i < clip.length && out.length; i++) {
    const a = clip[i], b = clip[(i + 1) % clip.length];
    const inside = p => sgn * ((b[0] - a[0]) * (p[1] - a[1]) - (b[1] - a[1]) * (p[0] - a[0])) >= 0;
    const inter = (p, q) => {
      const dx = q[0] - p[0], dz = q[1] - p[1];
      const ex = b[0] - a[0], ez = b[1] - a[1];
      const den = dx * ez - dz * ex;
      const t = ((a[0] - p[0]) * ez - (a[1] - p[1]) * ex) / den;
      return [p[0] + t * dx, p[1] + t * dz];
    };
    const inp = out;
    out = [];
    for (let j = 0; j < inp.length; j++) {
      const cur = inp[j], prev = inp[(j + inp.length - 1) % inp.length];
      if (inside(cur)) {
        if (!inside(prev)) out.push(inter(prev, cur));
        out.push(cur);
      } else if (inside(prev)) out.push(inter(prev, cur));
    }
  }
  return out;
}

function clearWater() {
  if (waterRoot) {
    waterRoot.traverse(o => { if (o.geometry) o.geometry.dispose(); if (o.material) o.material.dispose(); });
    scene.remove(waterRoot);
  }
  waterRoot = new THREE.Group();
  scene.add(waterRoot);
  for (const k of Object.keys(meshes)) delete meshes[k];
}

function buildWater() {
  clearWater();
  const w = spec.water || {};
  if (w.pond) {
    const m = new THREE.Mesh(polyGeometry(w.pond.outline, 0), waterMaterial());
    m.visible = false;
    waterRoot.add(m);
    meshes.pond = m;
  }
  if (w.manhole_m2) {
    const c = w.manhole_m2;
    const g = new THREE.CircleGeometry(c.radius, 48);
    g.rotateX(-Math.PI / 2);
    g.translate(c.center[0], 0, c.center[1]);
    const m = new THREE.Mesh(g, waterMaterial());
    m.visible = false;
    waterRoot.add(m);
    meshes.manhole_m2 = m;
  }
  if (w.basement) {
    const m = new THREE.Mesh(new THREE.BufferGeometry(), waterMaterial());
    m.visible = false;
    waterRoot.add(m);
    meshes.basement = m;
  }
}

function sampleDepth(key, t) {
  if (!depths || !depths.depth_m) return 0;
  const arr = depths.depth_m[(depths.map || nodeMap)[key]] || depths.depth_m[nodeMap[key]];
  const ts = depths.t;
  if (!arr || !ts || !ts.length) return 0;
  if (t <= ts[0]) return arr[0];
  if (t >= ts[ts.length - 1]) return arr[arr.length - 1];
  let lo = 0, hi = ts.length - 1;
  while (hi - lo > 1) { const mid = (lo + hi) >> 1; if (ts[mid] <= t) lo = mid; else hi = mid; }
  const f = (t - ts[lo]) / (ts[hi] - ts[lo]);
  return arr[lo] + f * (arr[hi] - arr[lo]);
}

const EPS = 1e-4;

function applyWater() {
  if (!spec) return;
  const w = spec.water || {};
  if (meshes.pond) {
    const d = sampleDepth('pond', curT);
    meshes.pond.visible = d > EPS;
    meshes.pond.position.y = (w.pond.base_y || 0) + d;
  }
  if (meshes.manhole_m2) {
    const d = sampleDepth('manhole_m2', curT);
    meshes.manhole_m2.visible = d > EPS;
    meshes.manhole_m2.position.y = (w.manhole_m2.base_y || 0) + d;
  }
  if (meshes.basement) {
    const b = w.basement;
    const d = sampleDepth('basement', curT);
    const slope = b.slope || 0;
    const m = meshes.basement;
    m.visible = false;
    if (d > EPS) {
      let region;
      if (slope > 1e-9) {
        // floor height = floor_y + slope * distance to drain; wet where that is below the water level
        const R = d / slope;
        const circle = [];
        for (let i = 0; i < 64; i++) {
          const a = (i / 64) * Math.PI * 2;
          circle.push([b.drain_xz[0] + R * Math.cos(a), b.drain_xz[1] + R * Math.sin(a)]);
        }
        region = clipConvex(circle, b.outline);
      } else {
        region = b.outline;
      }
      if (region.length >= 3) {
        m.geometry.dispose();
        m.geometry = polyGeometry(region, b.floor_y + d);
        m.visible = true;
      }
    }
  }
}

function updateHud() {
  if (showHud) hudEl.textContent = `t=${curT.toFixed(1)} s\ncamera=${camName}\nscene=${sceneVersion}`;
}

function renderNow() {
  applyWater();
  updateHud();
  renderer.render(scene, camera);
}

window.ready = false;

window.loadScene = async function (url, site = {}) {
  window.ready = false;
  if (sceneRoot) {
    sceneRoot.traverse(o => { if (o.geometry) o.geometry.dispose(); });
    scene.remove(sceneRoot);
  }
  sceneRoot = new THREE.Group();
  scene.add(sceneRoot);
  const mod = await import(/* @vite-ignore */ url + (url.includes('?') ? '&' : '?') + 'v=' + Date.now());
  spec = mod.default(THREE, sceneRoot, site);
  camDefs = spec.cameras || {};
  sceneVersion = url.split('/').pop().split('?')[0].replace(/\.js$/, '');
  buildWater();
  const first = camName && camDefs[camName] ? camName : Object.keys(camDefs)[0];
  window.setCamera(first);
  renderNow();
  window.ready = true;
};

window.loadDepths = function (json) {
  depths = json;
  curT = 0;
};

window.setStep = function (t) {
  curT = t;
  applyWater();
  updateHud();
};

window.setCamera = function (name) {
  const c = camDefs[name];
  if (!c) throw new Error('unknown camera ' + name);
  camName = name;
  camera = new THREE.PerspectiveCamera(c.fov || 60, W / H, 0.05, 500);
  camera.position.set(...c.position);
  camera.lookAt(new THREE.Vector3(...c.lookAt));
  camera.updateMatrixWorld();
};

window.renderNow = renderNow;
