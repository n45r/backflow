const $ = id => document.getElementById(id);
const qs = new URLSearchParams(location.search);
const RUN = qs.get('run') || 'calib';
const LIVE_FROM = qs.has('live') ? Number(qs.get('live')) : Infinity;
const PAGE_LOADED = Date.now() / 1000;
const HW = 854, HH = 480;
const CAM_NAMES = { cam1: 'Pond and weir', cam5: 'Basement' };

const state = {
  run: RUN, data: null, roundIdx: 0, mode: 'calib', cam: 'cam5', pred: 'informed',
  t: 0, duration: 0, playing: false, speed: 16, depths: null,
  holdout: { blind: null, informed: null }, reveal: null, sceneUrl: null, clipUrl: null,
};

const video = $('video');
const slider = $('slider');
let harness = null;
let viewToken = 0;
let lastFrame = 0;
let renderedT = -1;

async function getJSON(url) {
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
  if (state.mode === 'reveal') {
    const h = d.holdout;
    if (!h) return null;
    return {
      event: h.event,
      scene: state.pred === 'blind' ? h.blind_scene_url : h.informed_scene_url,
      depths: state.pred === 'blind' ? h.blind_depths_url : h.informed_depths_url,
      clips: h.clips,
      patch: (d.frozen && d.frozen.patch) || {},
    };
  }
  const r = d.rounds[state.roundIdx];
  if (!r) return null;
  return { event: r.event, scene: r.scene_url, depths: r.depths_url, clips: r.clips, patch: r.patch || {} };
}

async function applyView() {
  const token = ++viewToken;
  const v = currentView();
  const simEmpty = $('simEmpty');
  if (!v) {
    simEmpty.textContent = state.mode === 'reveal' ? 'No held-out prediction saved for this run yet' : 'No rounds yet';
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
    $('simSub').textContent = `${sceneName}, ${state.mode === 'reveal' ? state.pred + ' model' : 'round ' + state.data.rounds[state.roundIdx].round}`;
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
  updateCursor();
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
  const r = rounds[state.roundIdx];
  const live = r && isLive(r);
  for (const id of ['stripBadge', 'critBadge']) {
    $(id).textContent = live ? 'Live' : 'Recorded run';
    $(id).classList.toggle('live', !!live);
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
      verdict = row.verdict === 'tie' ? 'same' : 'different';
      text = row.verdict === 'tie' ? 'tie' : `best ${row.verdict}`;
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

/* ---------- reveal ---------- */

function setMode(mode) {
  state.mode = mode;
  $('modeCalib').classList.toggle('active', mode === 'calib');
  $('modeReveal').classList.toggle('active', mode === 'reveal');
  $('critique').hidden = mode !== 'calib';
  $('revealPanel').hidden = mode !== 'reveal';
  $('chips').hidden = mode !== 'calib';
  $('holdoutInfo').hidden = mode !== 'reveal';
  $('predToggle').hidden = mode !== 'reveal';
  $('stripBadge').hidden = mode !== 'calib';
  setPlaying(false);
  setT(0, true);
  if (mode === 'reveal') {
    const h = state.data && state.data.holdout;
    const f = state.data && state.data.frozen;
    $('holdoutInfo').innerHTML = h
      ? `Held-out event <b>${h.event}</b>. The model never saw this video or its sensors.` + (f ? ` Prediction frozen at <b>${f.sha}</b>.` : '')
      : 'No held-out prediction saved for this run yet.';
    loadHoldoutPredictions();
  } else {
    drawChips();
  }
  applyView().then(drawTicks);
}

async function loadHoldoutPredictions() {
  const h = state.data && state.data.holdout;
  if (!h) { drawChart(); return; }
  try {
    const [b, i] = await Promise.all([getDepths(h.blind_depths_url), getDepths(h.informed_depths_url)]);
    state.holdout = { blind: b, informed: i };
  } catch (e) { console.error(e); }
  $('revealSub').textContent = `Event ${h.event}, depth in mm above the basement floor`;
  drawChart();
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
    $('revealGate').querySelector('p').textContent = 'No evaluator output saved for this run yet.';
    return;
  }
  $('revealGate').hidden = true;
  drawChart(true);
  drawScores();
}

function chartSeries() {
  const rv = state.reveal && state.reveal.gauges && state.reveal.gauges.s6;
  if (rv) {
    const t = state.reveal.t;
    return { t, blind: rv.blind_m, informed: rv.informed_m, measured: rv.measured_m };
  }
  const { blind, informed } = state.holdout;
  const base = informed || blind;
  if (!base) return null;
  return { t: base.t, blind: blind && blind.depth_m.s6, informed: informed && informed.depth_m.s6, measured: null };
}

function niceStep(max) {
  const raw = max / 4;
  const p = Math.pow(10, Math.floor(Math.log10(raw)));
  return [1, 2, 2.5, 5, 10].map(m => m * p).find(s => s >= raw);
}

let chartGeom = null;

function drawChart(animateMeasured) {
  const svg = $('chart');
  const box = svg.getBoundingClientRect();
  const W = box.width, H = box.height;
  svg.setAttribute('viewBox', `0 0 ${W} ${H}`);
  const S = chartSeries();
  if (!S || !W || !H) { svg.innerHTML = ''; chartGeom = null; return; }
  const mm = a => (a || []).map(v => v * 1000);
  const series = [
    ['blind', 'Blind', mm(S.blind)],
    ['informed', 'Informed', mm(S.informed)],
    ['measured', 'Measured', S.measured ? mm(S.measured) : null],
  ].filter(s => s[2] && s[2].length);
  const tMax = S.t[S.t.length - 1];
  const yMaxRaw = Math.max(10, ...series.flatMap(s => s[2]));
  const step = niceStep(yMaxRaw * 1.05);
  const yMax = Math.ceil((yMaxRaw * 1.05) / step) * step;
  const m = { l: 48, r: 104, t: 12, b: 28 };
  const X = t => m.l + (t / tMax) * (W - m.l - m.r);
  const Y = v => m.t + (1 - v / yMax) * (H - m.t - m.b);
  chartGeom = { X, Y, m, W, H, tMax, S, series };
  let g = '';
  for (let v = 0; v <= yMax + 1e-9; v += step) {
    g += `<line class="grid" x1="${m.l}" x2="${W - m.r}" y1="${Y(v)}" y2="${Y(v)}"/>`;
    g += `<text class="axis" x="${m.l - 8}" y="${Y(v) + 4}" text-anchor="end">${Math.round(v)}</text>`;
  }
  const xStep = tMax > 900 ? 300 : 120;
  for (let t = 0; t <= tMax; t += xStep) {
    g += `<text class="axis" x="${X(t)}" y="${H - 6}" text-anchor="middle">${Math.round(t / 60)} min</text>`;
  }
  g += `<text class="axis" x="${m.l - 8}" y="${m.t - 0}" text-anchor="end" dy="-2"></text>`;
  const labels = [];
  for (const [cls, name, ys] of series) {
    const d = ys.map((v, i) => `${i ? 'L' : 'M'}${X(S.t[i]).toFixed(1)},${Y(v).toFixed(1)}`).join('');
    g += `<path class="ser ${cls}${cls === 'measured' && animateMeasured ? ' draw' : ''}" d="${d}"/>`;
    const peak = Math.max(...ys);
    labels.push({ name, cls, y: Y(ys[ys.length - 1]), peak });
  }
  labels.sort((a, b) => a.y - b.y);
  for (let i = 1; i < labels.length; i++) labels[i].y = Math.max(labels[i].y, labels[i - 1].y + 20);
  for (const l of labels) g += `<text class="dl" x="${W - m.r + 8}" y="${l.y + 5}">${l.name}</text>`;
  g += `<line class="cursor" id="cursor" y1="${m.t}" y2="${H - m.b}" x1="${X(0)}" x2="${X(0)}"/>`;
  g += `<rect id="hit" x="${m.l}" y="${m.t}" width="${W - m.l - m.r}" height="${H - m.t - m.b}" fill="transparent"/>`;
  svg.innerHTML = g;
  if (animateMeasured) {
    const p = svg.querySelector('.ser.measured');
    if (p) { const L = p.getTotalLength(); p.style.strokeDasharray = L; p.style.strokeDashoffset = L; }
  }
  svg.querySelector('#hit').addEventListener('mousemove', chartHover);
  svg.querySelector('#hit').addEventListener('mouseleave', () => { $('tip').hidden = true; });
  svg.querySelector('#hit').addEventListener('click', e => { const t = chartTime(e); setPlaying(false); setT(t, true); });
  updateCursor();
}

function chartTime(e) {
  const g = chartGeom;
  const rect = $('chart').getBoundingClientRect();
  const x = e.clientX - rect.left;
  return Math.max(0, Math.min(g.tMax, ((x - g.m.l) / (g.W - g.m.l - g.m.r)) * g.tMax));
}

function chartHover(e) {
  const g = chartGeom;
  if (!g) return;
  const t = chartTime(e);
  let i = 0;
  while (i < g.S.t.length - 1 && g.S.t[i + 1] <= t) i++;
  const tip = $('tip');
  const colors = { blind: 'var(--blind)', informed: 'var(--informed)', measured: 'var(--measured)' };
  tip.innerHTML = `<div class="dim">${fmt(g.S.t[i])}</div>` + g.series.map(([cls, name, ys]) =>
    `<div><span class="sw" style="background:${colors[cls]}"></span>${name} ${ys[i].toFixed(0)} mm</div>`).join('');
  tip.hidden = false;
  const x = g.X(g.S.t[i]);
  tip.style.left = `${x + (x > g.W * 0.6 ? -tip.offsetWidth - 12 : 12)}px`;
  tip.style.top = `${g.m.t + 6}px`;
}

function updateCursor() {
  const c = document.getElementById('cursor');
  if (!c || !chartGeom) return;
  const x = chartGeom.X(Math.min(state.t, chartGeom.tMax));
  c.setAttribute('x1', x);
  c.setAttribute('x2', x);
}

function mmText(v, signed) {
  if (v == null || !isFinite(v)) return 'n/a';
  const n = Math.round(v * 1000);
  return (signed && n > 0 ? '+' : '') + n;
}

function drawScores() {
  const g = state.reveal.gauges.s6;
  const card = (cls, name, e) => `
    <div class="card ${cls}">
      <div class="who">${name}</div>
      <div class="big">${mmText(e.mae_m)}<small>mm</small></div>
      <div class="what">mean error in basement depth</div>
      <div class="more">Peak ${mmText(e.peak_err_m, true)} mm${e.onset_err_s != null ? `, wetting ${e.onset_err_s > 0 ? '+' : ''}${Math.round(e.onset_err_s)} s` : ''}</div>
    </div>`;
  let html = card('blind', 'Blind model', g.blind) + card('informed', 'After watching one flood', g.informed);
  const b = g.blind.mae_m, i = g.informed.mae_m;
  if (b > 0 && i > 0) {
    const ratio = b / i;
    html += `<div class="verdict-line">${ratio >= 1 ? `${ratio.toFixed(1)} times smaller error` : `Error grew ${(1 / ratio).toFixed(1)} times`}`
      + (state.reveal.baseline && state.reveal.baseline.s6
        ? ` <span class="dim">Baseline (${state.reveal.baseline.label || 'numeric optimiser'}): ${mmText(state.reveal.baseline.s6.mae_m)} mm</span>` : '')
      + '</div>';
  }
  $('scoreCards').innerHTML = html;
  $('scoreCards').hidden = false;
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
  await applyView();
}

async function poll() {
  if (!state.data) return;
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
  document.querySelectorAll('#predToggle button').forEach(b => b.onclick = () => {
    state.pred = b.dataset.pred;
    document.querySelectorAll('#predToggle button').forEach(x => x.classList.toggle('on', x === b));
    applyView();
  });
  $('modeCalib').onclick = () => setMode('calib');
  $('modeReveal').onclick = () => setMode('reveal');
  $('revealBtn').onclick = doReveal;
  $('contactBtn').onclick = () => {
    const r = state.data.rounds[state.roundIdx];
    $('overlayImg').src = r.contact_url;
    $('overlay').hidden = false;
  };
  $('overlay').onclick = () => { $('overlay').hidden = true; };
  video.addEventListener('error', () => { $('videoEmpty').hidden = false; $('videoEmpty').textContent = 'Clip could not be played'; });
  document.addEventListener('keydown', e => {
    if (e.target.tagName === 'INPUT' && e.target.type !== 'range') return;
    if (e.key === ' ') { e.preventDefault(); setPlaying(!state.playing); }
    else if (e.key === 'ArrowRight' && state.mode === 'calib') selectRound(state.roundIdx + 1);
    else if (e.key === 'ArrowLeft' && state.mode === 'calib') selectRound(state.roundIdx - 1);
    else if (e.key === 'c') setCam(state.cam === 'cam1' ? 'cam5' : 'cam1');
    else if (e.key === 'r') setMode(state.mode === 'reveal' ? 'calib' : 'reveal');
    else if (e.key === 'Escape') $('overlay').hidden = true;
  });
  new ResizeObserver(fitHarness).observe($('simFrame'));
  new ResizeObserver(() => { if (state.mode === 'reveal') drawChart(); }).observe($('chartWrap'));
}

window.demo = { state, setT, setMode, selectRound, setCam, doReveal };

wire();
fitHarness();
requestAnimationFrame(tick);
loadRun();
setInterval(poll, 4000);
