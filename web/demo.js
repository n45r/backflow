const $ = id => document.getElementById(id);
const qs = new URLSearchParams(location.search);
const RUN_PARAM = qs.get('run');
const RUN = RUN_PARAM || 'calib_video';
const LIVE_FROM = qs.has('live') ? Number(qs.get('live')) : Infinity;
const PAGE_LOADED = Date.now() / 1000;
// The hosted copy has no server. The exported demo.html sets this, and every /api call reads a recorded JSON file instead.
const STATIC = window.BACKFLOW_STATIC === true;
const RECORDED_LABEL = 'Recorded run, replayed in your browser';
const HW = 854, HH = 480;
const CAM_NAMES = { cam1: 'Pond and weir', cam5: 'Basement' };

const state = {
  run: RUN, data: null, roundIdx: 0, mode: 'live', cam: 'cam5', pred: 'informed',
  t: 0, duration: 0, playing: false, speed: 16, depths: null,
  holdout: { blind: null, informed: null }, reveal: null, sceneUrl: null, clipUrl: null,
};

const video = $('video');
const slider = $('slider');
let harness = null;
let viewToken = 0;
let lastFrame = 0;
let renderedT = -1;

function staticUrl(url) {
  // /api/loop/x -> api/loop/x.json, relative so it works under a sub-path such as /backflow/
  return url.split('?')[0].replace(/^\//, '') + '.json';
}

async function getJSON(url) {
  if (STATIC && url.startsWith('/api/')) url = staticUrl(url);
  const r = await fetch(url, { cache: 'no-store' });
  if (!r.ok) throw new Error(`${url}: ${r.status}`);
  return r.json();
}

const depthCache = new Map();
async function getDepths(url) {
  if (!url) return null;
  if (!depthCache.has(url)) depthCache.set(url, getJSON(url).catch(e => { depthCache.delete(url); throw e; }));
  return depthCache.get(url);
}

function fmt(s) {
  s = Math.max(0, Math.round(s));
  return `${String(Math.floor(s / 60)).padStart(2, '0')}:${String(s % 60).padStart(2, '0')}`;
}

function isLive(r) {
  if (STATIC) return false;
  return r.live || r.round >= LIVE_FROM || r.mtime > PAGE_LOADED;
}

/* ---------- harness (locked page in an iframe) ---------- */

function harnessReady() {
  const frame = $('harness');
  return new Promise(resolve => {
    const check = () => {
      const w = frame.contentWindow;
      if (w && typeof w.loadScene === 'function') resolve(w);
      else setTimeout(check, 50);
    };
    check();
  });
}

function fitHarness() {
  const box = $('simFrame').getBoundingClientRect();
  const s = Math.min(box.width / HW, box.height / HH);
  const frame = $('harness');
  frame.style.transform = `translate(${(box.width - HW * s) / 2}px, ${(box.height - HH * s) / 2}px) scale(${s})`;
}

function renderSim() {
  if (!harness || !state.depths) return;
  try {
    harness.setStep(state.t);
    harness.renderNow();
    renderedT = state.t;
  } catch (e) { console.error(e); }
}

/* ---------- what is on screen ---------- */

function currentView() {
  const d = state.data;
  if (!d) return null;
  const r = d.rounds[state.roundIdx];
  if (!r) return null;
  return { event: r.event, scene: r.scene_url, depths: r.depths_url, clips: r.clips, patch: r.patch || {} };
}

async function applyView() {
  const token = ++viewToken;
  const v = currentView();
  const simEmpty = $('simEmpty');
  if (!v) {
    simEmpty.textContent = 'No rounds yet';
    simEmpty.hidden = false;
    setClip(null);
    return;
  }
  setClip(v.clips ? v.clips[state.cam] : null);
  $('videoSub').textContent = `Event ${v.event}, ${CAM_NAMES[state.cam]} (${state.cam})`;
  try {
    harness = harness || await harnessReady();
    const [depths] = await Promise.all([
      getDepths(v.depths),
      v.scene !== state.sceneUrl ? harness.loadScene(v.scene, state.data.site || {}) : null,
    ]);
    if (token !== viewToken) return;
    state.sceneUrl = v.scene;
    if (typeof harness.applyPatch === 'function') harness.applyPatch(v.patch || {});
    harness.setCamera(state.cam);
    harness.loadDepths(depths);
    state.depths = depths;
    const end = depths && depths.t && depths.t.length ? depths.t[depths.t.length - 1] : 0;
    setDuration(end);
    const sceneName = (v.scene || '').split('/').pop();
    $('simSub').textContent = `${sceneName}, round ${state.data.rounds[state.roundIdx].round}`;
    simEmpty.hidden = true;
    renderSim();
  } catch (e) {
    if (token !== viewToken) return;
    console.error(e);
    simEmpty.textContent = 'Could not load the scene: ' + e.message;
    simEmpty.hidden = false;
  }
}

function setClip(url) {
  $('videoEmpty').hidden = !!url;
  if (url === state.clipUrl) return;
  state.clipUrl = url;
  if (!url) { video.removeAttribute('src'); video.load(); return; }
  video.src = url;
  video.addEventListener('loadedmetadata', () => {
    video.currentTime = Math.min(state.t, video.duration || state.t);
    if (!state.duration) setDuration(video.duration);
  }, { once: true });
}

function setDuration(d) {
  state.duration = d || 0;
  slider.max = Math.max(1, Math.round(state.duration));
  $('timeEnd').textContent = fmt(state.duration);
  if (state.t > state.duration) setT(state.duration, true);
  drawTicks();
}

/* ---------- time ---------- */

function videoOk() {
  return state.clipUrl && video.readyState >= 1 && !video.error && isFinite(video.duration);
}

function setT(t, seekVideo) {
  state.t = Math.max(0, Math.min(t, state.duration || t));
  slider.value = Math.round(state.t);
  $('timeNow').textContent = fmt(state.t);
  if (seekVideo && videoOk()) video.currentTime = Math.min(state.t, video.duration);
  if (Math.abs(state.t - renderedT) > 0.05) renderSim();
}

function setPlaying(p) {
  state.playing = p;
  $('play').innerHTML = p ? '&#10074;&#10074;' : '&#9654;';
  $('play').setAttribute('aria-label', p ? 'Pause' : 'Play');
  if (p && state.t >= state.duration - 0.5) setT(0, true);
  if (!p) video.pause();
}

function tick(now) {
  const dt = lastFrame ? Math.min(0.1, (now - lastFrame) / 1000) : 0;
  lastFrame = now;
  liveTick(dt);
  revealTick(dt);
  if (state.playing) {
    const useVideo = videoOk() && state.speed <= 16 && state.t < video.duration - 0.25;
    if (useVideo) {
      if (video.playbackRate !== state.speed) video.playbackRate = state.speed;
      if (video.paused && !video.seeking) video.play().catch(() => {});
      setT(video.paused ? state.t + dt * state.speed : video.currentTime, false);
    } else {
      if (!video.paused) video.pause();
      setT(state.t + dt * state.speed, false);
      if (videoOk() && !video.seeking && Math.abs(video.currentTime - state.t) > 0.5 && state.t < video.duration) {
        video.currentTime = state.t;
      }
    }
    if (state.duration && state.t >= state.duration) setPlaying(false);
  }
  requestAnimationFrame(tick);
}

function drawTicks() {
  const box = $('ticks');
  box.innerHTML = '';
  if (state.mode !== 'calib' || !state.data || !state.duration) return;
  const r = state.data.rounds[state.roundIdx];
  if (!r) return;
  for (const row of r.rows) {
    const m = /(cam\d).*?t\s*=\s*(\d+(?:\.\d+)?)/.exec(row.label || '');
    if (!m || m[1] !== state.cam) continue;
    const el = document.createElement('div');
    el.className = 'tick' + (row.verdict === 'same' ? ' same' : '');
    el.style.left = `calc(${(Number(m[2]) / state.duration) * 100}% + ${8 - 16 * Number(m[2]) / state.duration}px)`;
    box.appendChild(el);
  }
}

/* ---------- rounds and critique ---------- */

function drawChips() {
  const box = $('chips');
  box.innerHTML = '';
  const rounds = state.data ? state.data.rounds : [];
  rounds.forEach((r, i) => {
    const b = document.createElement('button');
    b.className = 'chip' + (i === state.roundIdx ? ' on' : '') + (isLive(r) ? ' live-chip' : '');
    b.innerHTML = `Round ${r.round}` + (r.round === 0 ? '<span class="k">blind</span>' : '');
    b.onclick = () => selectRound(i);
    box.appendChild(b);
  });
  if (state.data && state.data.frozen) {
    const f = document.createElement('span');
    f.className = 'chip';
    f.style.cursor = 'default';
    f.innerHTML = `Frozen<span class="k">${state.data.frozen.sha || ''}</span>`;
    box.appendChild(f);
  }
}

function fmtVal(v) {
  if (typeof v === 'number') return Number.isInteger(v) ? String(v) : v.toFixed(2);
  return v == null ? 'unset' : String(v);
}

function drawCritique() {
  const r = state.data && state.data.rounds[state.roundIdx];
  const rows = $('rows');
  rows.innerHTML = '';
  if (!r) { $('critSub').textContent = 'No rounds yet'; return; }
  const conf = r.confidence != null ? `, confidence ${Math.round(r.confidence * 100)}%` : '';
  const judged = r.kind === 'path' || r.kind === 'numeric';
  if (judged) {
    const what = r.kind === 'path' ? 'which way water enters' : 'which settings match';
    $('critSub').textContent = `Round ${r.round}, event ${r.event}: Argon judged ${what}. Winner ${r.winner || '-'}${conf}`;
  } else {
    const diff = r.rows.filter(x => x.verdict === 'different' || x.verdict === 'patched').length;
    $('critSub').textContent = `Round ${r.round}, event ${r.event}: ${diff} of ${r.rows.length} moments differ${conf}`;
  }
  for (const row of r.rows) {
    const li = document.createElement('li');
    let verdict, text;
    if (judged) {
      verdict = row.verdict === 'tie' ? 'same' : (row.verdict === r.winner ? 'win' : 'different');
      text = row.verdict === 'tie' ? 'Tie' : `Best ${row.verdict}`;
    } else {
      verdict = row.verdict === 'same' ? 'same' : 'different';
      text = row.verdict || verdict;
    }
    li.innerHTML = `<span class="lab"></span><span class="verdict ${verdict}"></span><span class="ev"></span>`;
    li.querySelector('.verdict').textContent = text;
    li.querySelector('.lab').textContent = row.label;
    li.querySelector('.ev').textContent = row.evidence;
    li.onclick = () => jumpToRow(row);
    rows.appendChild(li);
  }
  const knobs = $('knobs');
  knobs.innerHTML = '';
  const changes = Object.entries(r.applied_knobs || {});
  if (!changes.length) knobs.innerHTML = '<div class="knob dim">No change</div>';
  for (const [k, v] of changes) {
    const el = document.createElement('div');
    el.className = 'knob';
    el.innerHTML = `<span class="name"></span><span class="from"></span><span class="arrow">to</span><span class="to"></span>`;
    el.querySelector('.name').textContent = k;
    el.querySelector('.from').textContent = fmtVal(r.params[k]);
    el.querySelector('.to').textContent = fmtVal(v);
    knobs.appendChild(el);
  }
  $('patch').textContent = r.scene_patch || 'None';
  $('evidence').textContent = r.remaining_error || r.evidence || '';
  $('contactBtn').hidden = !r.contact_url;
  $('watchBtn').hidden = !r.judge_video_url;
}

function jumpToRow(row) {
  const m = /(cam\d).*?t\s*=\s*(\d+(?:\.\d+)?)/.exec(row.label || '');
  if (!m) return;
  setPlaying(false);
  if (m[1] !== state.cam && CAM_NAMES[m[1]]) setCam(m[1]);
  setT(Number(m[2]), true);
}

function selectRound(i) {
  if (!state.data || i < 0 || i >= state.data.rounds.length) return;
  state.roundIdx = i;
  drawChips();
  drawCritique();
  applyView().then(drawTicks);
}

function setCam(cam) {
  state.cam = cam;
  document.querySelectorAll('.cams button').forEach(b => b.classList.toggle('on', b.dataset.cam === cam));
  if (harness && state.sceneUrl) {
    try { harness.setCamera(cam); } catch (e) { console.error(e); }
  }
  renderedT = -1;
  applyView();
  drawTicks();
}


/* ---------- shared pieces: 3D tiles, clocks, urls ---------- */

// Server paths start with "/". The hosted copy has no server, so the same paths are made relative to the page.
function assetUrl(p) {
  if (!p || /^(https?:|blob:|data:)/.test(p)) return p;
  if (STATIC) return p.startsWith('/') ? '.' + p : p;
  return p.startsWith('/') || p.startsWith('./') ? p : '/' + p;
}

function frameReady(frame, ms = 30000) {
  return new Promise((resolve, reject) => {
    const t0 = performance.now();
    const check = () => {
      const w = frame.contentWindow;
      if (w && typeof w.loadScene === 'function') resolve(w);
      else if (performance.now() - t0 > ms) reject(new Error('3D view did not start'));
      else setTimeout(check, 60);
    };
    check();
  });
}

/* A tile is a box holding one copy of the locked 3D harness, scaled down to fit. */
function attachFrame(el) {
  const frame = document.createElement('iframe');
  frame.src = './index.html';
  frame.title = '3D view';
  frame.setAttribute('tabindex', '-1');
  el.insertBefore(frame, el.firstChild);
  const fit = () => {
    const r = el.getBoundingClientRect();
    if (!r.width) return;
    frame.style.transform = `scale(${Math.max(r.width / HW, r.height / HH)})`;
  };
  const ro = new ResizeObserver(fit);
  ro.observe(el);
  const tile = { el, frame, win: null, ready: false, failed: false, pendingT: 0, drawnT: -1 };
  tile.load = async v => {
    try {
      const w = await frameReady(frame);
      tile.win = w;
      await w.loadScene(v.scene, v.site || {});
      if (w.applyPatch) w.applyPatch(v.patch || {});
      w.setCamera(v.cam || 'cam5');
      w.loadDepths(v.depths);
      tile.ready = true;
      tile.draw(tile.pendingT, true);
    } catch (e) {
      console.error(e);
      tile.failed = true;
    }
  };
  tile.draw = (t, force) => {
    tile.pendingT = t;
    if (!tile.ready) return;
    if (!force && Math.abs(t - tile.drawnT) < 0.05) return;
    try { tile.win.setStep(t); tile.win.renderNow(); tile.drawnT = t; } catch (e) { console.error(e); }
  };
  tile.destroy = () => { ro.disconnect(); frame.remove(); tile.ready = false; };
  return tile;
}

/* One shared clock. Everything on a stage reads its time from here. */
function makeClock(lo, hi, seconds, loop) {
  const c = {
    lo, hi, t: lo, playing: true, loop,
    rate: (hi - lo) / seconds,
    set(t) { c.t = Math.max(c.lo, Math.min(c.hi, t)); },
    advance(dt) {
      if (!c.playing) return;
      c.t += c.rate * dt;
      if (c.t >= c.hi) {
        if (c.loop) c.t = c.lo + (c.t - c.hi) % Math.max(1, c.hi - c.lo);
        else { c.t = c.hi; c.playing = false; }
      }
    },
  };
  return c;
}

function syncVideo(v, t, force) {
  if (!v || v.readyState < 1 || v.error || !isFinite(v.duration) || v.seeking) return;
  const want = Math.max(0, Math.min(t, v.duration - 0.05));
  if (force || Math.abs(v.currentTime - want) > 0.35) v.currentTime = want;
}

function clockSeconds(label) {
  const m = /^(\d+):(\d{1,2})$/.exec(String(label || '').trim());
  return m ? Number(m[1]) * 60 + Number(m[2]) : null;
}

function fitBox(wrap, box, aspect) {
  const r = wrap.getBoundingClientRect();
  if (!r.width || !r.height) return;
  const w = Math.min(r.width, r.height * aspect);
  box.style.width = `${Math.floor(w)}px`;
  box.style.height = `${Math.floor(w / aspect)}px`;
}

function mmShort(m) {
  const v = m * 1000;
  if (!isFinite(v)) return 'n/a';
  return (v >= 9.5 ? String(Math.round(v)) : String(Number(v.toFixed(1)))) + ' mm';
}

/* ---------- modes ---------- */

function setMode(mode) {
  state.mode = mode;
  document.body.dataset.mode = mode;
  $('modeLive').classList.toggle('active', mode === 'live');
  $('modeCalib').classList.toggle('active', mode === 'calib');
  $('modeReveal').classList.toggle('active', mode === 'reveal');
  $('critique').hidden = mode !== 'calib';
  $('reveal').hidden = mode !== 'reveal';
  $('chips').hidden = mode !== 'calib';
  $('stripBadge').hidden = true;
  setPlaying(false);
  setT(0, true);
  if (mode === 'live') { fitStage(); return; }
  if (mode === 'reveal') {
    openReveal();
  } else {
    drawChips();
    applyView().then(drawTicks);
  }
}

/* ---------- reveal ---------- */

const rv = { built: false, tiles: {}, clock: null, video: null, tMax: 0, lastSeek: 0, lastDraw: 0, key: null };

function argmax(a) {
  let k = 0;
  for (let i = 1; i < a.length; i++) if (a[i] > a[k]) k = i;
  return k;
}

async function openReveal() {
  const h = state.data && state.data.holdout;
  const f = state.data && state.data.frozen;
  if (!h) {
    $('revealNote').textContent = 'No held-out prediction saved for this run yet.';
    drawChart();
    return;
  }
  $('revealNote').textContent = `Flood ${h.event}. The model never saw this video or its sensors.` + (f && f.sha ? ` Prediction frozen at ${f.sha}.` : '');
  try {
    const [b, i] = await Promise.all([getDepths(h.blind_depths_url), getDepths(h.informed_depths_url)]);
    state.holdout = { blind: b, informed: i };
  } catch (e) { console.error(e); }
  drawChart();
  buildReveal(h);
}

function buildReveal(h) {
  const { blind, informed } = state.holdout;
  const base = informed || blind;
  if (!base) return;
  const key = `${h.event}:${h.informed_depths_url}`;
  if (rv.built && rv.key === key) { fitReveal(); return; }
  for (const t of Object.values(rv.tiles)) t.destroy();
  rv.tiles = {};
  rv.key = key;
  rv.built = true;
  const tMax = base.t[base.t.length - 1];
  rv.tMax = tMax;
  rv.clock = makeClock(0, tMax, 40, true);
  const site = state.data.site || {};
  const frozenPatch = (state.data.frozen && state.data.frozen.patch) || {};
  const mk = (id, scene, depths, patch) => {
    const t = attachFrame($(id));
    rv.tiles[id] = t;
    if (depths && scene) t.load({ scene: assetUrl(scene), depths, patch: patch || frozenPatch, site, cam: 'cam5' });
  };
  mk('rvBlind', h.blind_scene_url, blind, h.blind_patch);
  mk('rvInformed', h.informed_scene_url, informed, h.informed_patch);
  setWhich('informed');
  rv.video = $('rvVideo');
  const clip = h.clips && h.clips.cam5;
  if (clip) {
    rv.video.src = assetUrl(clip);
    rv.video.addEventListener('loadedmetadata', () => syncVideo(rv.video, rv.clock.t, true), { once: true });
  }
  $('rvRealCap').textContent = `Real camera, hidden flood ${h.event}`;
  $('rvSlider').max = Math.round(tMax);
  paintReveal(true);
}

function setWhich(w) {
  $('rvBlind').classList.toggle('off', w !== 'blind');
  $('rvInformed').classList.toggle('off', w !== 'informed');
  $('rvModelCap').textContent = w === 'blind' ? 'Model before, untuned' : 'Model after watching one flood';
  document.querySelectorAll('#rvToggle button').forEach(b => b.classList.toggle('on', b.dataset.w === w));
  if (rv.clock) paintReveal(true);
}

function fitReveal() { paintReveal(true); }

function paintReveal(force) {
  const c = rv.clock;
  if (!c) return;
  $('rvTime').textContent = fmt(c.t);
  $('rvSlider').value = Math.round(c.t);
  $('rvPlay').textContent = c.playing ? 'Pause' : 'Play';
  $('rvPlay').setAttribute('aria-label', c.playing ? 'Pause' : 'Play');
  updateCursor(c.t);
  const now = performance.now();
  if (force || now - rv.lastDraw > 60) {
    for (const [id, t] of Object.entries(rv.tiles)) if (!t.el.classList.contains('off')) t.draw(c.t, force);
    rv.lastDraw = now;
  }
  if (force || now - rv.lastSeek > 160) { syncVideo(rv.video, c.t, force); rv.lastSeek = now; }
}

function revealTick(dt) {
  if (state.mode !== 'reveal' || !rv.clock) return;
  const was = rv.clock.t;
  rv.clock.advance(dt);
  if (rv.clock.playing || rv.clock.t !== was) paintReveal(false);
}

function revealSeek(t) {
  if (!rv.clock) return;
  rv.clock.set(t);
  paintReveal(true);
}

async function doReveal() {
  const btn = $('revealBtn');
  btn.disabled = true;
  btn.textContent = 'Revealing';
  try {
    state.reveal = await getJSON(`/api/reveal/${encodeURIComponent(state.run)}`);
  } catch (e) {
    btn.disabled = false;
    btn.textContent = 'Reveal sensors';
    $('revealGate').querySelector('span').textContent = 'No evaluator output saved for this run yet.';
    return;
  }
  $('revealGate').hidden = true;
  drawChart(true);
  drawScores();
}

function chartSeries() {
  const rvl = state.reveal && state.reveal.gauges && state.reveal.gauges.s6;
  if (rvl) {
    return { t: state.reveal.t, blind: rvl.blind_m, informed: rvl.informed_m, measured: rvl.measured_m };
  }
  const { blind, informed } = state.holdout;
  const base = informed || blind;
  if (!base) return null;
  return { t: base.t, blind: blind && blind.depth_m.s6, informed: informed && informed.depth_m.s6, measured: null };
}

function niceStep(max) {
  const raw = max / 3;
  const p = Math.pow(10, Math.floor(Math.log10(raw)));
  return [1, 2, 2.5, 5, 10].map(m => m * p).find(s => s >= raw);
}

let chartGeom = null;
const SVGNS = 'http://www.w3.org/2000/svg';

function drawChart(animateMeasured) {
  const svg = $('chart');
  const box = svg.getBoundingClientRect();
  const W = box.width, H = box.height;
  svg.setAttribute('viewBox', `0 0 ${W} ${H}`);
  const S = chartSeries();
  if (!S || !W || !H) { svg.innerHTML = ''; chartGeom = null; return; }
  const mm = a => (a || []).map(v => v * 1000);
  const series = [
    ['blind', 'Before', mm(S.blind)],
    ['informed', 'After', mm(S.informed)],
    ['measured', 'Measured', S.measured ? mm(S.measured) : null],
  ].filter(s => s[2] && s[2].length);
  const tMax = S.t[S.t.length - 1];
  const yMaxRaw = Math.max(10, ...series.flatMap(s => s[2]));
  const step = niceStep(yMaxRaw * 1.05);
  const yMax = Math.ceil((yMaxRaw * 1.05) / step) * step;
  const m = { l: 56, r: 96, t: 14, b: 26 };
  const X = t => m.l + (t / tMax) * (W - m.l - m.r);
  const Y = v => m.t + (1 - v / yMax) * (H - m.t - m.b);
  chartGeom = { X, Y, m, W, H, tMax, S, series };
  let g = `<line class="base" x1="${m.l}" x2="${W - m.r}" y1="${Y(0)}" y2="${Y(0)}"/>`;
  g += `<text class="axis" x="${m.l - 10}" y="${Y(0) + 4}" text-anchor="end">0</text>`;
  g += `<text class="axis" x="${m.l - 10}" y="${Y(yMax) + 4}" text-anchor="end">${yMax} mm</text>`;
  const xStep = tMax > 900 ? 300 : 120;
  for (let t = xStep; t <= tMax; t += xStep) {
    g += `<text class="axis" x="${X(t)}" y="${H - 6}" text-anchor="middle">${Math.round(t / 60)} min</text>`;
  }
  const labels = [];
  for (const [cls, name, ys] of series) {
    const d = ys.map((v, i) => `${i ? 'L' : 'M'}${X(S.t[i]).toFixed(1)},${Y(v).toFixed(1)}`).join('');
    g += `<path class="ser ${cls}${cls === 'measured' && animateMeasured ? ' draw' : ''}" d="${d}"/>`;
    const peak = Math.max(...ys);
    const ip = ys.indexOf(peak);
    labels.push({ name, cls, x: X(S.t[ip]) + 10, y: Y(peak) - 12 });
  }
  labels.sort((a, b) => a.y - b.y);
  for (let i = 1; i < labels.length; i++) {
    if (Math.abs(labels[i].x - labels[i - 1].x) < 110) labels[i].y = Math.max(labels[i].y, labels[i - 1].y + 20);
  }
  for (const l of labels) {
    g += `<text class="dl ${l.cls}" x="${Math.min(l.x, W - m.r + 10)}" y="${Math.max(m.t + 8, l.y)}">${l.name}</text>`;
  }
  g += `<line class="cursor" id="cursor" y1="${m.t}" y2="${Y(0)}" x1="${X(0)}" x2="${X(0)}"/>`;
  for (const [cls] of series) g += `<circle class="dot ${cls}" r="4.5" cx="-10" cy="-10" fill="var(--${cls})"/>`;
  g += `<rect id="hit" x="${m.l}" y="0" width="${W - m.l - m.r}" height="${H - m.b}" fill="transparent" style="cursor:pointer"/>`;
  svg.innerHTML = g;
  if (animateMeasured) {
    const p = svg.querySelector('.ser.measured');
    if (p) { const L = p.getTotalLength(); p.style.strokeDasharray = L; p.style.strokeDashoffset = L; }
  }
  const hit = svg.querySelector('#hit');
  const go = e => { if (rv.clock) { rv.clock.playing = false; revealSeek(chartTime(e)); } };
  hit.addEventListener('pointerdown', e => { hit.setPointerCapture(e.pointerId); go(e); });
  hit.addEventListener('pointermove', e => { if (e.buttons & 1) go(e); });
  updateCursor(rv.clock ? rv.clock.t : 0);
}

function chartTime(e) {
  const g = chartGeom;
  const rect = $('chart').getBoundingClientRect();
  const x = e.clientX - rect.left;
  return Math.max(0, Math.min(g.tMax, ((x - g.m.l) / (g.W - g.m.l - g.m.r)) * g.tMax));
}

function updateCursor(t) {
  const c = document.getElementById('cursor');
  if (!c || !chartGeom) return;
  const g = chartGeom;
  const x = g.X(Math.min(t, g.tMax));
  c.setAttribute('x1', x);
  c.setAttribute('x2', x);
  let i = 0;
  while (i < g.S.t.length - 1 && g.S.t[i + 1] <= t) i++;
  g.series.forEach(([cls, , ys]) => {
    const dot = document.querySelector(`#chart .dot.${cls}`);
    if (dot) { dot.setAttribute('cx', x); dot.setAttribute('cy', g.Y(ys[i])); }
  });
}

function drawScores() {
  const g = state.reveal.gauges.s6;
  const before = mmShort(g.blind.mae_m), after = mmShort(g.informed.mae_m);
  $('sentence').innerHTML = `Off by <span class="b">${before}</span> before. Off by <span class="i">${after}</span> after watching one flood.`;
  const ex = state.reveal.experts;
  $('compare').textContent = ex && ex.s6
    ? `For comparison, researchers calibrating on sewer sensors from other floods are off by ${mmShort(ex.s6.mae_m)} on this one (median of 40).`
    : '';
  $('compare').hidden = !(ex && ex.s6);
  $('scoreCards').hidden = false;
}

/* ---------- the round, shown step by step ---------- */

const ORDER = ['agents', 'sim', 'curves', 'draw', 'send', 'watch', 'verdict'];
const STEP_OF = { agents: 0, sim: 1, curves: 1, draw: 2, send: 3, watch: 4, verdict: 5, legacy: 4 };
const CAPTION = {
  agents: 'Three Managed Agents test three theories of how water enters the basement',
  sim: 'Simulating three versions of the model',
  curves: 'Water depth in the basement, three versions',
  draw: 'Drawing each version from the real camera\'s view',
  send: 'Sending the time-lapse to Argon',
  watch: 'Argon is watching',
};
const live = {
  phase: 'idle', startedLocal: 0, elapsed: 0, timer: null, videoPath: null,
  verdictShown: false, replay: false, ready: true, active: false,
  stage: null, stageKey: null, layout: 'stage', moments: [], view: null, viewAt: 0, viewRound: null,
  target: 'sim', verdictEntry: null, cands: null, finished: false, total: 2, firstCands: null, doneEntry: null,
};

function setLiveState(st) {
  live.phase = st;
  $('live').dataset.state = st;
  if (st === 'running' || st === 'done') requestAnimationFrame(fitStage);
}

function stepsShow(now) {
  document.querySelectorAll('#steps li').forEach(li => {
    const i = Number(li.dataset.step);
    li.classList.toggle('done', i < now);
    li.classList.toggle('now', i === now);
  });
}

const KNOB_NAMES = { outlet_cd: 'outlet coefficient', p7_diameter_m: 'pipe 7 diameter', p3_roughness: 'pipe 3 roughness' };
const knobName = k => KNOB_NAMES[k] || k.replace(/_m$/, '').replace(/_/g, ' ');
const num3 = v => String(Number(Number(v).toPrecision(3)));

const THEORY = { sewer: 'Water comes up the sewer drain', door: 'Water comes in under the door', both: 'Both' };
function isPathRound(cands) {
  return !!(cands && cands.A && ['B', 'C'].some(L => cands[L] && cands[L].basement_path !== cands.A.basement_path));
}

function describeShort(label, cands) {
  if (isPathRound(cands) && cands[label]) return THEORY[cands[label].basement_path] || cands[label].basement_path;
  if (!cands || !cands[label] || label === 'A') return describe(label, cands);
  const a = cands.A || {}, c = cands[label];
  const diffs = Object.keys(c).filter(k => c[k] !== a[k]);
  return diffs.length > 1 ? `${diffs.length} settings changed` : describe(label, cands);
}

function describe(label, cands) {
  if (!cands || !cands[label]) return '';
  if (isPathRound(cands)) return THEORY[cands[label].basement_path] || '';
  if (label === 'A') return 'current settings';
  const a = cands.A || {}, c = cands[label];
  const diffs = Object.keys(c).filter(k => c[k] !== a[k]);
  if (!diffs.length) return 'same settings';
  return diffs.map(k => {
    if (k === 'basement_path') return `water enters by the ${c[k]}`;
    return `${knobName(k)} ${typeof c[k] === 'number' ? num3(c[k]) : fmtVal(c[k])}`;
  }).join(', ');
}

function lastWith(log, pred) {
  for (let i = log.length - 1; i >= 0; i--) if (pred(log[i])) return log[i];
  return null;
}

function setLayout(layout) {
  live.layout = layout;
  $('live').dataset.layout = layout;
  fitStage();
}

function fitStage() {
  fitBox($('stageWrap'), $('stageBox'), live.layout === 'legacy' ? 1286 / 726 : 16 / 9);
}

function setLiveVideo(path) {
  if (!path || path === live.videoPath) return;
  live.videoPath = path;
  const v = $('liveVideo');
  $('liveVideoErr').hidden = true;
  v.src = STATIC ? assetUrl(path) : `/api/video?path=${encodeURIComponent(path)}`;
  $('live').dataset.vid = '1';
  if (live.layout === 'stage') $('lapseBtn').hidden = false;
}

function friendlyError(msg, tail) {
  const all = (tail || []).join('\n') + ' ' + (msg || '');
  if (/no recorded answer|CacheMiss|ARGON_CACHE=replay/.test(all)) {
    return 'Offline replay has no recorded answer for this round. Restart with ./demo (no --replay) to call Argon live.';
  }
  return msg || 'The round stopped before Argon gave a verdict.';
}

function showError(msg, tail) {
  setLiveState('error');
  stopTimer();
  $('errText').textContent = friendlyError(msg, tail);
  $('errLog').textContent = (tail || []).slice(-8).join('\n');
  $('errLog').hidden = !(tail && tail.length);
}

const clean = t => String(t || '').replace(/\s*[—–]\s*/g, ', ');

/* ---------- view changes: one stage that visibly changes per step ---------- */

function setView(v) {
  live.view = v;
  live.viewAt = performance.now();
  const box = $('live');
  box.dataset.view = v;
  $('stepAgents').hidden = !live.viewMa;
  $('steps').classList.toggle('ma', !!live.viewMa);
  if (v === 'agents') startAgents();
  stepsShow(STEP_OF[v] ?? 0);
  const vid = $('liveVideo');
  if (v === 'curves') drawCurvesAnimated();
  if (v === 'send') { try { vid.pause(); vid.currentTime = 0; } catch (e) { /* not loaded yet */ } }
  if (v === 'watch') { vid.playbackRate = 4; vid.play().catch(() => {}); }
  if (v !== 'watch' && v !== 'legacy' && box.dataset.lapse !== '1') vid.pause();
  $('watchMark').hidden = v !== 'watch' && v !== 'legacy';
  if (v === 'legacy') $('watchMark').hidden = true;
  const s = live.stage;
  if (s) {
    s.tilesEl.dataset.mode = (v === 'draw' && s.framesOk) ? 'frames' : 'live';
    if (v === 'verdict' || (v === 'draw' && !s.framesOk)) paintStage(true);
  }
  if (v === 'verdict') {
    if (live.verdictEntry) showVerdict(live.verdictEntry, live.cands);
    $('caption').textContent = live.verdictEntry ? `Argon picked ${live.verdictEntry.winner}.` : '';
  } else if (CAPTION[v]) {
    $('caption').textContent = CAPTION[v];
  }
  if (v === 'sim') {
    $('verdict').hidden = true;
    $('trained').hidden = true;
    $('sideHint').hidden = false;
  }
  if (v !== 'draw') stopFrames(); else startFrames();
}

function dwellOf(v) {
  if (v === 'agents') return live.agentsData ? 8000 : 3500;
  if (v === 'sim') return 1000;
  if (v === 'curves') return 2000;
  if (v === 'draw') return 6000;
  if (v === 'send') return 2000;
  if (v === 'watch') return 8000;
  return 0;
}

function advance() {
  if (live.layout === 'legacy' || (live.phase !== 'running' && live.phase !== 'done')) return;
  const i = ORDER.indexOf(live.view), j = ORDER.indexOf(live.target);
  if (j <= i || i < 0) return;
  if (performance.now() - live.viewAt < dwellOf(live.view)) return;
  const next = ORDER[i + 1];
  // curves and the 3D tiles need the stage; wait for it, but never stall the verdict forever
  if ((next === 'curves' || next === 'draw' || next === 'verdict') && !live.stage) {
    if (next === 'curves' && live.target === 'sim') return;
    if (live.layout === 'stage' && live.stageKey) return;
  }
  setView(next);
}

/* ---------- the stage: real camera and three 3D views on one clock ---------- */

function teardownStage() {
  stopFrames();
  const s = live.stage;
  if (s) for (const t of Object.values(s.tiles)) t.destroy();
  live.stage = null;
  live.stageKey = null;
  $('tiles').innerHTML = '';
  $('curveSvg').innerHTML = '';
  $('live').dataset.lapse = '0';
  $('scrubTicks').innerHTML = '';
  $('lapseBtn').textContent = 'Show what Argon sees';
  $('pauseBtn').textContent = 'Pause';
}

function labelHtml(letter, text, picked) {
  return `<b>${letter}</b>${text}${picked ? '<span class="pick">Argon\'s pick</span>' : ''}`;
}

const DASH = { A: '', B: '', C: '26 14' };
function buildCurves(depths, letters, lo, hi) {
  const arr = d => d.depth_m[(d.map && d.map.basement) || 's6'] || d.depth_m.s6;
  const W = 1600, H = 900, m = { l: 170, r: 120, t: 70, b: 80 };
  let ymax = 0.001;
  const series = depths.map(d => {
    const pts = d.t.map((t, i) => [t, arr(d)[i] * 1000]).filter(p => p[0] >= lo && p[0] <= hi);
    pts.forEach(p => { ymax = Math.max(ymax, p[1]); });
    return pts;
  });
  const top = Math.max(10, Math.ceil(ymax * 1.1 / 10) * 10);
  const X = t => m.l + ((t - lo) / (hi - lo)) * (W - m.l - m.r);
  const Y = v => H - m.b - (v / top) * (H - m.t - m.b);
  let g = `<line x1="${m.l}" x2="${W - m.r}" y1="${Y(0)}" y2="${Y(0)}" class="cbase"/>`;
  g += `<text x="${m.l - 16}" y="${Y(0) + 8}" text-anchor="end" class="cax">0</text>`;
  g += `<text x="${m.l - 16}" y="${Y(top) + 8}" text-anchor="end" class="cax">${top} mm</text>`;
  for (let t = Math.ceil(lo / 300) * 300; t <= hi; t += 300) g += `<text x="${X(t)}" y="${H - 28}" text-anchor="middle" class="cax">${Math.round(t / 60)} min</text>`;
  letters.forEach((L, i) => {
    const pts = series[i];
    if (!pts.length) return;
    const d = pts.map((p, k) => `${k ? 'L' : 'M'}${X(p[0]).toFixed(1)},${Y(p[1]).toFixed(1)}`).join('');
    g += `<path class="cl cl${L}" d="${d}" ${DASH[L] ? `stroke-dasharray="${DASH[L]}"` : ''}/>`;
    const peak = pts.reduce((a, p) => (p[1] > a[1] ? p : a), pts[0]);
    g += `<text class="clab cl${L}t" x="${X(peak[0]) + 18}" y="${Y(peak[1]) - 14}">${L}</text>`;
  });
  $('curveSvg').innerHTML = g;
}

function drawCurvesAnimated() {
  const svg = $('curveSvg');
  svg.classList.remove('go');
  void svg.getBoundingClientRect();
  svg.classList.add('go');
}

async function buildStage(rend, cands) {
  const key = `${rend.round}:${rend.t}`;
  if (live.stageKey === key) return;
  teardownStage();
  live.stageKey = key;
  setLayout('stage');
  const paths = rend.depths || {};
  const letters = ['A', 'B', 'C'].filter(L => paths[L]);
  let depths;
  try {
    depths = await Promise.all(letters.map(L => getDepths((STATIC ? '' : '/') + paths[L].replace(/^\/+/, ''))));
  } catch (e) {
    console.error(e);
    if (live.stageKey === key) { live.stageKey = null; fallbackLegacy(); }
    return;
  }
  if (live.stageKey !== key) return;
  const win = rend.window || [0, depths[0].t[depths[0].t.length - 1]];
  const [lo, hi] = win;
  const clock = makeClock(lo, hi, 20, true);
  const site = state.data.site || {};
  const tiles = {};
  const box = $('tiles');
  const mkTile = cls => {
    const el = document.createElement('div');
    el.className = 'tile ' + cls;
    box.appendChild(el);
    return el;
  };
  const realEl = mkTile('real');
  const vid = document.createElement('video');
  vid.muted = true; vid.playsInline = true; vid.preload = 'auto';
  vid.src = assetUrl(`/clips/${rend.event}_cam5.mp4`);
  vid.addEventListener('loadedmetadata', () => syncVideo(vid, clock.t, true), { once: true });
  vid.addEventListener('error', () => { realEl.insertAdjacentHTML('beforeend', '<div class="empty quiet">Camera clip not available</div>'); });
  realEl.appendChild(vid);
  realEl.insertAdjacentHTML('beforeend', '<div class="tile-label">Real camera</div>');
  const scene = assetUrl(rend.scene);
  const imgs = {};
  letters.forEach((L, i) => {
    const el = mkTile('cand');
    el.dataset.letter = L;
    const t = attachFrame(el);
    const img = document.createElement('img');
    img.className = 'fr'; img.alt = '';
    el.appendChild(img);
    imgs[L] = img;
    el.insertAdjacentHTML('beforeend', `<div class="tile-label">${labelHtml(L, describeShort(L, cands || rend.candidates), false)}</div>`);
    tiles[L] = t;
    t.load({ scene, patch: rend.patch || {}, depths: depths[i], site, cam: 'cam5' });
  });
  live.stage = { key, round: rend.round, tiles, imgs, video: vid, clock, lastDraw: 0, lastSeek: 0, rend, cands: cands || rend.candidates,
    tilesEl: box, framesOk: false, frames: null, frameT: lo };
  buildCurves(depths, letters, lo, hi);
  const sc = $('scrubIn');
  sc.min = lo; sc.max = hi;
  fitStage();
  if (live.view === 'draw') startFrames();
  if (live.verdictEntry && live.target === 'verdict') markVerdictOnStage();
}

function fallbackLegacy() {
  teardownStage();
  setLayout('legacy');
  setView('legacy');
  $('lapseBtn').hidden = true;
}

/* frames the renderer writes while it works: the tiles fill in as they appear */
let framesTimer = null;
function stopFrames() { if (framesTimer) { clearTimeout(framesTimer); framesTimer = null; } }

function startFrames() {
  stopFrames();
  if (STATIC) return;
  const s = live.stage;
  if (!s) return;
  const name = s.rend.ma ? 'ma_demo' : encodeURIComponent(state.run + '_cal');
  const rn = s.rend.ma ? 1 : s.round - (live.ma ? 1 : 0);
  const loop = async () => {
    const st = live.stage;
    if (!st || st !== s) return;
    try {
      const r = await getJSON(`/api/frames/${name}/${rn}`);
      applyFrames(r);
    } catch (e) { /* not there yet */ }
    framesTimer = setTimeout(loop, 600);
  };
  loop();
}

function applyFrames(r) {
  const s = live.stage;
  if (!s) return;
  s.frames = r;
  let t = s.frameT, any = false;
  for (const L of Object.keys(s.imgs)) {
    const list = (r.render && r.render[L]) || [];
    if (!list.length) continue;
    any = true;
    const f = list[list.length - 1];
    if (s.imgs[L].dataset.src !== f.url) { s.imgs[L].dataset.src = f.url; s.imgs[L].src = f.url; }
    t = Math.max(t, f.t);
  }
  if (any) {
    s.framesOk = true;
    s.frameT = t;
    if (live.view === 'draw') s.tilesEl.dataset.mode = 'frames';
  }
  if (r.grid && r.grid[0]) $('liveVideo').poster = r.grid[0].url;
  if (r.video && !live.videoPath) setLiveVideo(r.video);
}

function paintStage(force) {
  const s = live.stage;
  if (!s) return;
  const framesMode = live.view === 'draw' && s.framesOk;
  const c = s.clock;
  const t = framesMode ? s.frameT : c.t;
  $('clock').textContent = fmt(t);
  const f = (t - c.lo) / Math.max(1, c.hi - c.lo);
  $('scrubFill').style.width = `${Math.max(0, Math.min(1, f)) * 100}%`;
  if (document.activeElement !== $('scrubIn') || force) $('scrubIn').value = t;
  const now = performance.now();
  if (!framesMode && (force || now - s.lastDraw > 55)) {
    for (const tl of Object.values(s.tiles)) tl.draw(t, force);
    s.lastDraw = now;
  }
  if (force || now - s.lastSeek > 140) { syncVideo(s.video, t, force); s.lastSeek = now; }
}

function liveTick(dt) {
  if (state.mode !== 'live') return;
  advance();
  agentsTick();
  const s = live.stage;
  if (live.view === 'watch') {
    const v = $('liveVideo');
    if (v.duration) $('playHead').style.left = `${(v.currentTime / v.duration) * 100}%`;
  }
  if (!s || (live.phase !== 'running' && live.phase !== 'done')) return;
  if (live.view === 'draw' && s.framesOk) { paintStage(false); return; }
  if (live.view !== 'verdict' && live.view !== 'draw') return;
  if ($('live').dataset.lapse === '1') return;
  s.clock.advance(dt);
  paintStage(false);
}

function setStagePlaying(p) {
  const s = live.stage;
  if (!s) return;
  s.clock.playing = p;
  $('pauseBtn').textContent = p ? 'Pause' : 'Play';
}

function jumpLive(sec) {
  const s = live.stage;
  if (!s || sec == null || live.view !== 'verdict') return;
  if ($('live').dataset.lapse === '1') toggleLapse();
  s.clock.set(sec);
  setStagePlaying(false);
  paintStage(true);
  document.querySelectorAll('#moments li').forEach(li => li.classList.toggle('on', Number(li.dataset.sec) === sec));
}

function toggleLapse() {
  const on = $('live').dataset.lapse !== '1';
  $('live').dataset.lapse = on ? '1' : '0';
  $('lapseBtn').textContent = on ? 'Show the 3D views' : 'Show what Argon sees';
  const v = $('liveVideo');
  if (on) { v.playbackRate = 4; v.play().catch(() => {}); } else v.pause();
  if (!on) paintStage(true);
}

function markVerdictOnStage() {
  const s = live.stage, w = live.verdictEntry && live.verdictEntry.winner;
  if (!s || !w) return;
  for (const [L, t] of Object.entries(s.tiles)) {
    t.el.classList.toggle('win', L === w);
    t.el.classList.toggle('dim', L !== w);
    t.el.querySelector('.tile-label').innerHTML = labelHtml(L, describeShort(L, s.cands), L === w);
  }
  const win = s.clock.hi - s.clock.lo;
  const ticks = $('scrubTicks');
  ticks.innerHTML = '';
  for (const m of live.moments) {
    if (m.sec == null) continue;
    const d = document.createElement('div');
    d.className = 'stick';
    d.style.left = `${((m.sec - s.clock.lo) / win) * 100}%`;
    ticks.appendChild(d);
  }
}

function showVerdict(entry, cands) {
  const w = entry.winner;
  $('winLetter').textContent = w;
  $('winWhat').textContent = describe(w, cands);
  const rem = (entry.text || '').replace(/^Round \d+: Argon picked [ABC]\.?\s*/, '');
  $('remaining').textContent = rem ? `Still off: ${clean(rem)}` : '';
  $('remaining').hidden = !rem;
  const ul = $('moments');
  ul.innerHTML = '';
  live.moments = [];
  for (const m of entry.moments || []) {
    const sec = clockSeconds(m.label);
    live.moments.push({ sec });
    const li = document.createElement('li');
    li.dataset.sec = sec == null ? '' : sec;
    li.innerHTML = '<span class="mt"></span><span class="pick"></span><span class="ev"></span>';
    li.querySelector('.mt').textContent = m.label || '';
    const b = m.verdict;
    const pk = li.querySelector('.pick');
    pk.textContent = b === 'tie' ? 'Tie' : b;
    if (b === w) pk.classList.add('win');
    li.querySelector('.ev').textContent = clean(m.evidence);
    li.onclick = () => jumpLive(sec);
    ul.appendChild(li);
  }
  $('sideHint').hidden = true;
  $('verdict').hidden = false;
  live.verdictShown = true;
  markVerdictOnStage();
  updateTrained();
}

function updateTrained() {
  const show = live.view === 'verdict' && live.finished && !live.testing;
  $('trained').hidden = !show;
  if (!show) return;
  if (!live.trainedShown) { live.trainedShown = true; $('sideCol').scrollTop = 0; }
  const done = live.doneEntry || {};
  const first = live.firstCands && live.firstCands.A;
  const ul = $('changes');
  ul.innerHTML = '';
  if (first && done.params) {
    for (const k of Object.keys(done.params)) {
      if (done.params[k] === first[k] || k === 'basement_path') continue;
      const li = document.createElement('li');
      li.innerHTML = '<span class="k"></span><span class="from"></span> to <span class="to"></span>';
      li.querySelector('.k').textContent = knobName(k);
      li.querySelector('.from').textContent = typeof first[k] === 'number' ? num3(first[k]) : fmtVal(first[k]);
      li.querySelector('.to').textContent = typeof done.params[k] === 'number' ? num3(done.params[k]) : fmtVal(done.params[k]);
      ul.appendChild(li);
    }
  }
  if (!ul.children.length) ul.innerHTML = '<li class="quiet">No setting changed</li>';
  setLiveState('done');
  stopTimer();
}

function renderLive(r) {
  live.replay = !!r.replay;
  if (STATIC) {
    $('modeBadge').textContent = 'Recorded';
    $('runNote').textContent = RECORDED_LABEL;
    $('staticLabel').hidden = false;
  } else {
    $('modeBadge').textContent = live.replay ? 'Offline replay' : 'Live';
    $('runNote').textContent = live.replay ? 'Replays recorded answers, no network needed' : 'Two rounds, about two minutes';
  }
  if (!r.started_here) return;
  // A page opened fresh shows the start button. It only picks up a round that is still running.
  if (!live.active) { if (!r.running) return; live.active = true; }
  if (live.expect && r.started !== live.expect) return;
  const p = r.progress;
  const log = (p && p.log) || [];
  const cur = p && p.current;
  if (r.running) {
    if (live.phase !== 'running' && !live.finished) startTimer(r.elapsed);
    live.elapsed = r.elapsed;
  } else {
    live.elapsed = r.elapsed;
  }
  const rounds = log.filter(e => e.round > 0).map(e => e.round);
  const Rlatest = rounds.length ? Math.max(...rounds) : 0;
  // a new round starts only after the last one has shown its pick for a few seconds
  const uniq = [...new Set(rounds)].sort((x, y) => x - y);
  const nextR = live.viewRound === null || live.viewRound === 0 ? uniq[0] : uniq.find(r => r > live.viewRound);
  if (nextR !== undefined && nextR !== live.viewRound) {
    const free = live.viewRound === null || live.viewRound === 0
      || (live.view === 'verdict' && performance.now() - live.viewAt >= 5500)
      || (live.viewMa && live.view === 'agents' && performance.now() - live.viewAt >= dwellOf('agents'));
    if (free) {
      teardownStage();
      live.viewRound = nextR;
      live.verdictEntry = null;
      live.verdictShown = false;
      live.agentsData = null;
      live.viewMa = inRma(log, nextR);
      setView(live.viewMa ? 'agents' : 'sim');
    }
  }
  const R = live.viewRound ?? 0;
  const lastRound = R === Rlatest;
  const of = Math.max(2, Rlatest);
  live.ma = log.some(e => e.ma);
  const isMa = inRma(log, R);
  $('roundTag').textContent = isMa ? 'Managed Agents' : (R ? `Round ${R - (live.ma ? 1 : 0)} of 4` : '');
  const inR = log.filter(e => e.round === R);
  const vidEntry = lastWith(inR, e => e.video);
  const rend = lastWith(inR, e => e.stage === 'render' && e.depths && e.scene);
  const simR = lastWith(inR, e => e.stage === 'simulate' && e.candidates);
  const cands = (rend && rend.candidates) || (simR && simR.candidates);
  const firstSim = log.find(e => e.stage === 'simulate' && e.candidates);
  live.firstCands = firstSim && firstSim.candidates;
  const verdictR = lastWith(inR, e => e.stage === 'verdict');
  const doneEntry = lastWith(log, e => e.stage === 'done');
  const anyDone = (p && log.some(e => e.stage === 'done'));
  live.doneEntry = doneEntry;
  live.finished = !r.running && lastRound && (anyDone ? !!doneEntry : !!verdictR) && !!verdictR;
  if (cands) {
    $('legendCands').innerHTML = '';
    for (const L of ['A', 'B', 'C']) {
      const sp = document.createElement('span');
      sp.innerHTML = '<b></b><span></span>';
      sp.querySelector('b').textContent = L;
      sp.querySelector('span').textContent = describe(L, cands);
      $('legendCands').appendChild(sp);
    }
  }
  const failed = (cur && cur.stage === 'error') || (!r.running && !verdictR && r.exit_code != null);
  if (failed) {
    showError(cur && cur.stage === 'error' ? cur.text : null, r.log_tail);
    return;
  }
  {
    if (vidEntry) setLiveVideo(vidEntry.video);
    if (rend) buildStage(rend, cands).catch(e => { console.error(e); fallbackLegacy(); });
    else if (vidEntry && !live.stageKey && live.layout !== 'legacy' && !STATIC) { /* renderer data comes with the render entry */ }
    else if (vidEntry && !live.stageKey && STATIC && live.layout !== 'legacy' && log.every(e => e.stage !== 'render' || !e.depths)) fallbackLegacy();
    live.cands = cands;
    if (verdictR) live.verdictEntry = verdictR;
    const agEntry = lastWith(inR, e => e.stage === 'agents');
    if (agEntry) { live.agentsData = agEntry.workers || null; }
    live.target = verdictR ? 'verdict' : lastWith(inR, e => e.stage === 'watching') ? 'watch'
      : lastWith(inR, e => e.stage === 'upload') ? 'send' : rend ? 'draw' : (simR || !agEntry) ? 'sim' : 'agents';
    if (agEntry && !simR && !rend && live.viewMa === undefined) live.viewMa = true;
    if (rend && live.view === 'sim' && live.target !== 'sim') { /* advance() takes it from here */ }
    if (live.layout === 'legacy' && verdictR && !live.verdictShown) {
      showVerdict(verdictR, cands);
      $('caption').textContent = `Argon picked ${verdictR.winner}.`;
      setLiveState('done');
      stopTimer();
    } else if (live.layout === 'legacy') {
      $('caption').textContent = cur ? clean(cur.text) : '';
    }
  }
  if (live.phase === 'idle') setLiveState('running');
  if (live.view === 'verdict') updateTrained();
}

function startTimer(from) {
  live.startedLocal = performance.now() - (from || 0) * 1000;
  stopTimer();
  live.timer = setInterval(() => {
    $('elapsed').textContent = fmt((performance.now() - live.startedLocal) / 1000);
  }, 500);
}

function stopTimer() {
  if (live.timer) clearInterval(live.timer);
  live.timer = null;
}

async function pollLive() {
  if (STATIC) {
    // No server to poll. Load the recorded round once and wait for the button.
    try { replay.prog = (await getJSON(`/api/progress/${encodeURIComponent(state.run)}`)).progress; } catch (e) { replay.prog = null; }
    renderLive({ replay: false, started_here: false });
    return;
  }
  try {
    const r = await getJSON(`/api/progress/${encodeURIComponent(state.run + '_cal')}`);
    renderLive(r);
    live.ready = true;
  } catch (e) { /* server busy */ }
  const busy = live.phase === 'running';
  setTimeout(pollLive, busy ? 600 : 2500);
}

/* Static mode: play the recorded log back with its original timings. Each log entry carries `at`, seconds from the round start. */
const replay = { prog: null, timer: null };

function startStaticRound() {
  const prog = replay.prog;
  if (!prog || !(prog.log || []).length) { showError('The recorded round is not available.', []); return; }
  if (replay.timer) clearInterval(replay.timer);
  const t0 = performance.now();
  const hasDone = prog.log.some(e => e.stage === 'done');
  const step = () => {
    const el = (performance.now() - t0) / 1000;
    const log = prog.log.filter(e => (e.at || 0) <= el);
    const done = hasDone ? log.some(e => e.stage === 'done') : log.some(e => e.stage === 'verdict');
    renderLive({
      replay: false, started_here: true, running: !done, started: 'static', elapsed: el,
      exit_code: done ? 0 : null, progress: { log, current: log[log.length - 1] || null },
    });
    if (done) { clearInterval(replay.timer); replay.timer = null; }
  };
  replay.timer = setInterval(step, 250);
  step();
}

async function startRound() {
  teardownStage();
  live.videoPath = null; live.verdictShown = false; live.verdictEntry = null; live.moments = []; live.finished = false; live.testing = false; live.trainedShown = false; live.ma = false; live.agentsData = null; live.viewMa = undefined;
  live.elapsed = 0; live.expect = null; live.active = true; live.viewRound = null; live.view = null; live.target = 'sim';
  setLayout('stage');
  $('liveVideo').removeAttribute('src');
  $('liveVideo').removeAttribute('poster');
  $('live').dataset.vid = '0';
  $('lapseBtn').hidden = true;
  $('legendCands').innerHTML = '';
  $('verdict').hidden = true;
  $('trained').hidden = true;
  $('testing').hidden = true;
  $('sideHint').hidden = false;
  $('clock').textContent = '00:00';
  $('scrubFill').style.width = '0';
  $('roundTag').textContent = '';
  $('elapsed').textContent = '00:00';
  setView('sim');
  setLiveState('running');
  startTimer(0);
  if (STATIC) { startStaticRound(); return; }
  try {
    const res = await fetch(`/api/calibrate/${encodeURIComponent(state.run)}`, { method: 'POST' });
    if (res.ok) live.expect = (await res.json()).started_at;
    else {
      let detail = res.statusText;
      try { detail = (await res.json()).detail || detail; } catch (e) { /* not JSON */ }
      showError(detail, []);
    }
  } catch (e) {
    showError('Could not reach the demo server.', []);
  }
}

/* The test uses the model the full run froze. One quiet line, then the proving screen. */
async function runTest(lineEl, hideEls) {
  live.testing = true;
  for (const el of hideEls) el.hidden = true;
  const n = state.data && state.data.rounds ? state.data.rounds.length : 6;
  lineEl.textContent = `Testing the model from the full run (${n} rounds, same method)`;
  lineEl.hidden = false;
  const wait = new Promise(r => setTimeout(r, 3200));
  let ok = true;
  if (!STATIC) {
    try { ok = (await fetch(`/api/test/${encodeURIComponent(state.run)}`, { method: 'POST' })).ok; } catch (e) { ok = false; }
  }
  await wait;
  live.testing = false;
  if (!ok) { lineEl.textContent = 'No held-out prediction is saved for this run yet.'; return; }
  setMode('reveal');
  lineEl.hidden = true;
  for (const el of hideEls) el.hidden = false;
}

function useRecorded() {
  $('runCard').classList.add('rec');
  $('leadRec').hidden = false;
  $('testRecBtn').hidden = false;
}

function wireLive() {
  $('runBtn').onclick = startRound;
  $('againBtn').onclick = startRound;
  $('retryBtn').onclick = startRound;
  $('recLink').onclick = useRecorded;
  $('testRecBtn').onclick = () => runTest($('recNote'), [$('testRecBtn')]);
  $('testBtn').onclick = () => { $('trained').hidden = true; runTest($('testing'), []).then(() => { $('trained').hidden = false; }); };
  $('pauseBtn').onclick = () => setStagePlaying(!(live.stage && live.stage.clock.playing));
  $('lapseBtn').onclick = toggleLapse;
  $('scrubIn').addEventListener('input', () => {
    if (!live.stage) return;
    live.stage.clock.set(Number($('scrubIn').value));
    setStagePlaying(false);
    paintStage(true);
  });
  $('liveVideo').addEventListener('error', () => { if ($('liveVideo').getAttribute('src')) $('liveVideoErr').hidden = false; });
  new ResizeObserver(fitStage).observe($('stageWrap'));
}


/* ---------- Managed Agents ---------- */

function inRma(log, R) { return log.some(e => e.round === R && e.ma); }

const AG_ORDER = ['sewer', 'door', 'both'];
function startAgents() {
  live.agentsStart = performance.now();
  for (const h of AG_ORDER) {
    const el = document.querySelector(`.ag[data-h="${h}"]`);
    el.className = 'ag working'; delete el.dataset.done;
    el.querySelector('.ag-body').innerHTML = '';
    el.querySelector('.ag-time').textContent = '00:00';
  }
}

function firstSentence(t, n) {
  t = clean(t || '').replace(/\s+/g, ' ').trim();
  const m = /^(.{40,}?[.!?])\s/.exec(t);
  let x = m ? m[1] : t;
  if (x.length > n) x = x.slice(0, n).replace(/\s+\S*$/, '') + '...';
  return x;
}

function agentsTick() {
  if (live.view !== 'agents') return;
  const data = live.agentsData;
  const el0 = (performance.now() - live.agentsStart) / 1000;
  const FAST = 6; // seconds the slowest replayed agent takes to count up to its real time
  const maxWall = data ? Math.max(...AG_ORDER.map(h => (data[h] && data[h].wall_seconds) || 0), 1) : 1;
  for (const h of AG_ORDER) {
    const el = document.querySelector(`.ag[data-h="${h}"]`);
    const w = data && data[h];
    const time = el.querySelector('.ag-time');
    if (!w) { // no result yet: a plain running timer
      const done = live.target !== 'agents';
      time.textContent = fmt(el0);
      el.classList.toggle('working', !done);
      if (done && !el.querySelector('.ag-body').textContent) el.querySelector('.ag-body').innerHTML = '<div class="big">Finished</div>';
      continue;
    }
    const wall = w.wall_seconds || 60;
    const shown = Math.min(wall, el0 * (maxWall / FAST));
    time.textContent = fmt(shown);
    const finished = shown >= wall - 0.01;
    el.classList.toggle('working', !finished);
    if (finished && !el.dataset.done) {
      el.dataset.done = '1';
      const body = el.querySelector('.ag-body');
      if (!w.used) {
        el.classList.add('out');
        body.innerHTML = '<div class="big">Did not finish, left out</div>';
      } else {
        const k = w.best_knobs || {};
        const set = Object.keys(k).map(x => `${knobName(x)} ${num3(k[x])}`).join(', ');
        const tok = w.tokens ? ` · ${Math.round(w.tokens / 1000)}k tokens` : '';
        body.innerHTML = `<div class="big">${w.runs ?? w.n_cal_runs_logged ?? 0} simulation runs</div>`
          + `<div class="set">Best settings: ${set}</div>`
          + `<div class="quiet set">${fmt(wall)}${tok}</div>`
          + `<div class="ex"></div>`;
        body.querySelector('.ex').textContent = firstSentence(w.report, 170);
      }
    }
  }
}
/* ---------- boot ---------- */

async function loadRun() {
  let data;
  try {
    data = await getJSON(`/api/loop/${encodeURIComponent(state.run)}`);
  } catch (e) {
    if (!qs.get('run') && state.run !== 'demo_fixture') {
      state.run = 'demo_fixture';
      return loadRun();
    }
    $('runName').textContent = `Run "${state.run}" not found`;
    return;
  }
  state.data = data;
  state.roundIdx = qs.has('round') ? Math.min(Number(qs.get('round')), data.rounds.length - 1) : 0;
  $('runName').textContent = `run ${data.name}`;
  $('fixtureBadge').hidden = !data.fixture;
  drawChips();
  drawCritique();
  if (state.mode !== 'live') await applyView();
}

async function poll() {
  if (STATIC || !state.data) return;
  try {
    const data = await getJSON(`/api/loop/${encodeURIComponent(state.run)}`);
    const had = state.data.rounds.length;
    const atEnd = state.roundIdx === had - 1;
    const changed = data.rounds.length !== had || JSON.stringify(data.frozen) !== JSON.stringify(state.data.frozen);
    if (!changed) return;
    state.data = data;
    if (state.mode === 'calib') {
      if (atEnd && data.rounds.length > had) selectRound(data.rounds.length - 1);
      else { drawChips(); }
    }
  } catch (e) { /* server busy, try again next time */ }
}

function wire() {
  $('play').onclick = () => setPlaying(!state.playing);
  slider.addEventListener('input', () => setT(Number(slider.value), true));
  document.querySelectorAll('.speeds button').forEach(b => b.onclick = () => {
    state.speed = Number(b.dataset.speed);
    document.querySelectorAll('.speeds button').forEach(x => x.classList.toggle('on', x === b));
  });
  document.querySelectorAll('.cams button').forEach(b => b.onclick = () => setCam(b.dataset.cam));
  $('modeLive').onclick = () => setMode('live');
  $('modeCalib').onclick = () => setMode('calib');
  $('modeReveal').onclick = () => setMode('reveal');
  $('revealBtn').onclick = doReveal;
  $('rvPlay').onclick = () => { if (!rv.clock) return; rv.clock.playing = !rv.clock.playing; paintReveal(false); };
  $('rvSlider').addEventListener('input', () => revealSeek(Number($('rvSlider').value)));
  document.querySelectorAll('#rvToggle button').forEach(x => x.onclick = () => setWhich(x.dataset.w));
  $('contactBtn').onclick = () => {
    const r = state.data.rounds[state.roundIdx];
    $('overlayVid').hidden = true; $('overlayVid').pause();
    $('overlayImg').hidden = false;
    $('overlayImg').src = r.contact_url;
    $('overlay').hidden = false;
  };
  $('watchBtn').onclick = () => {
    const r = state.data.rounds[state.roundIdx];
    const v = $('overlayVid');
    $('overlayImg').hidden = true;
    v.hidden = false; v.src = r.judge_video_url; v.playbackRate = 4; v.play();
    $('overlay').hidden = false;
  };
  $('overlay').onclick = () => { $('overlay').hidden = true; $('overlayVid').pause(); };
  video.addEventListener('error', () => { $('videoEmpty').hidden = false; $('videoEmpty').textContent = 'Clip could not be played'; });
  document.addEventListener('keydown', e => {
    if (e.target.tagName === 'INPUT' && e.target.type !== 'range') return;
    if (e.key === ' ') {
      e.preventDefault();
      if (state.mode === 'live') setStagePlaying(!(live.stage && live.stage.clock.playing));
      else if (state.mode === 'reveal') $('rvPlay').onclick();
      else setPlaying(!state.playing);
    }
    else if (e.key === 'ArrowRight' && state.mode === 'calib') selectRound(state.roundIdx + 1);
    else if (e.key === 'ArrowLeft' && state.mode === 'calib') selectRound(state.roundIdx - 1);
    else if (e.key === 'c') setCam(state.cam === 'cam1' ? 'cam5' : 'cam1');
    else if (e.key === 'r') setMode(state.mode === 'reveal' ? 'calib' : 'reveal');
    else if (e.key === 'l') setMode('live');
    else if (e.key === 'Escape') $('overlay').hidden = true;
  });
  new ResizeObserver(fitHarness).observe($('simFrame'));
  new ResizeObserver(() => { if (state.mode === 'reveal') drawChart(); }).observe($('chartWrap'));
}


async function boot() {
  if (!RUN_PARAM) {
    try {
      const d = await getJSON('/api/default_run');
      state.run = d.name;
    } catch (e) { /* keep the fallback name */ }
  }
  const asked = qs.get('mode') || (qs.has('round') || qs.has('live') ? 'calib' : 'live');
  await loadRun();
  setMode(['calib', 'reveal'].includes(asked) ? asked : 'live');
  pollLive();
}

window.demo = { state, live, rv, setT, setMode, selectRound, setCam, doReveal, startRound, jumpLive };

document.body.dataset.mode = 'live';
wire();
wireLive();
stepsShow(-1);
fitHarness();
requestAnimationFrame(tick);
boot();
if (!STATIC) setInterval(poll, 4000);
