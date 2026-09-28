"use strict";
/* TRACE rPPG: the live app.
   Displays what the Python pipeline produces; it never recomputes pipeline
   math. Live values arrive over /ws (app/engine.py). The evaluation numbers
   come from /static/lab/results.json (scripts/build_dashboard_data.py). */

const METHODS = ["green", "chrom", "pos"];
const MNAME = { green: "GREEN", chrom: "CHROM", pos: "POS" };
const TITLES = { measure: "Measure", methods: "Methods", signal: "How it works", scenarios: "Scenarios", collect: "Collect", next: "What's next" };
const ART_TAG = 0.25; // artifact share at a method's peak above which the card is tagged

const $ = s => document.querySelector(s);
const $$ = s => Array.from(document.querySelectorAll(s));
function localGet(k) { try { return localStorage.getItem(k); } catch { return null; } }
function localSet(k, v) { try { localStorage.setItem(k, v); } catch { /* storage unavailable */ } }

let view = "measure", state = {}, ws = null, simSource = null, scenarios = null, hrv = null;
let lastT = null;
const wHistory = []; // {t, w: {green, chrom, pos}}

/* ================================================================== helpers */
const fmt = (v, d = 0) => (v == null || !isFinite(v)) ? "--" : (+v).toFixed(d);
const pct = v => (v == null || !isFinite(v)) ? "--" : `${Math.round(v * 100)}%`;
function mmss(s) { s = Math.max(0, Math.floor(s || 0)); return `${String(Math.floor(s / 60)).padStart(2, "0")}:${String(s % 60).padStart(2, "0")}`; }
function css(name) { return getComputedStyle(document.documentElement).getPropertyValue(name).trim(); }
const MCOL = () => ({ green: css("--m-green"), chrom: css("--m-chrom"), pos: css("--m-pos") });
function dominantOf(w) { if (!w) return null; let best = null; for (const k of METHODS) if (w[k] != null && (best == null || w[k] > w[best])) best = k; return best; }
function haveBpm() { return typeof state.bpm === "number"; }
function setPill(el, text, cls) {
  if (!el) return;
  el.className = el.className.replace(/\b(good|warn|info|coral)\b/g, "").trim() + (cls ? " " + cls : "");
  const s = el.querySelector(".dot") ? el.querySelector("span:last-child") : null;
  if (s) s.textContent = text; else el.textContent = text;
}
function wbar(name, v, max, col, text, cls = "") {
  return `<div class="wb ${cls}" style="--c:${col}"><span class="n"><i></i>${name}</span><span class="b"><i style="width:${Math.max(0, Math.min(100, v / max * 100))}%"></i></span><span class="v">${text}</span></div>`;
}

/* ================================================================== theme and privacy */
function applyTheme(t) { document.documentElement.dataset.theme = t === "light" ? "light" : "dark"; }
applyTheme(localGet("theme"));
$("#theme").addEventListener("click", () => {
  const nxt = document.documentElement.dataset.theme === "light" ? "dark" : "light";
  applyTheme(nxt); localSet("theme", nxt); renderAll();
});
const about = $("#about");
function toggleAbout(open) { about.hidden = !open; $("#about-btn").setAttribute("aria-expanded", String(open)); if (open) $("#about-close").focus(); }
$("#about-btn").addEventListener("click", () => toggleAbout(about.hidden));
$("#about-close").addEventListener("click", () => toggleAbout(false));
document.addEventListener("keydown", e => { if (e.key === "Escape" && !about.hidden) toggleAbout(false); });

/* ================================================================== navigation */
function moveIndicator() {
  const b = $(`.nav button[data-view="${view}"]`), ind = $("#nav-indicator");
  if (!b) { ind.style.opacity = 0; return; }
  ind.style.opacity = 1; ind.style.transform = `translateY(${b.offsetTop}px)`;
}
function go(v) {
  view = v;
  $$(".view").forEach(s => s.classList.toggle("active", s.dataset.view === v));
  // Any rail button with a destination counts, in the main list or the footer.
  $$(".rail button[data-view]").forEach(b => b.classList.toggle("active", b.dataset.view === v));
  $("#view-title").textContent = TITLES[v];
  $("#ctx-view").textContent = TITLES[v].toUpperCase();
  if (v === "scenarios" || v === "signal") loadHub();
  moveIndicator(); renderAll();
  window.scrollTo({ top: 0 });
}
$$(".rail button[data-view]").forEach(b => b.addEventListener("click", () => go(b.dataset.view)));
// data-res-tab also picks which source Scenarios opens on (for example the volunteers).
const goFrom = c => { if (c.dataset.resTab) { hubTab = c.dataset.resTab; localSet("res-tab", hubTab); hubKey = ""; } go(c.dataset.goto); };
$$("[data-goto]").forEach(c => {
  c.addEventListener("click", () => goFrom(c));
  c.addEventListener("keydown", e => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); goFrom(c); } });
});

/* ================================================================== server link */
function connect() {
  ws = new WebSocket(`ws://${location.host}/ws`);
  ws.onmessage = ev => {
    const msg = JSON.parse(ev.data);
    if (msg.type === "state") { state = msg.state || {}; onState(); }
    if (msg.type === "hrv") { hrv = msg.result; renderHrv(); }
    if (msg.type.startsWith("rec_") && window.onRecMessage) window.onRecMessage(msg);
  };
  ws.onopen = () => { while (outbox.length) ws.send(JSON.stringify(outbox.shift())); };
  ws.onclose = () => { setPill($("#pill-live"), "OFFLINE", "warn"); setTimeout(connect, 1500); };
}
// Commands sent before the connection is open (a fast click right after the
// page loads, or during a reconnect) wait here instead of being dropped.
const outbox = [];
function send(o) {
  if (ws && ws.readyState === 1) ws.send(JSON.stringify(o));
  else outbox.push(o);
}

function startSource(kind = "sim") {
  simSource = kind === "sim" ? { ...simSettings } : null;
  send(simSource ? { cmd: "start", source: "sim", options: simSource } : { cmd: "start", source: "webcam" });
  $$("img.feed").forEach(img => { img.src = `/video.mjpg?${Date.now()}`; });
  wHistory.length = 0;
  lock = null; lastLock = null; lockGapUntil = 0;
  audioCtx();  // a click is the gesture browsers need before any sound
}

/* ================================================================== confidence lock
   A live reading moves every half second. When the confidence (the frozen
   logistic P(within 5 BPM)) reaches 95 percent, the number is held for 3 s
   and the device buzzes, then the display goes live again. The next lock
   needs at least 3 s of live display first, so a steady face gives a calm
   rhythm of locks instead of one endless freeze. Display only: the pipeline
   keeps running underneath. */
const LOCK = { p: 0.95, hold: 3000, gap: 3000 };
let lock = null, lastLock = null, lockGapUntil = 0, actx = null;
function audioCtx() {
  try {
    actx = actx || new (window.AudioContext || window.webkitAudioContext)();
    if (actx.state === "suspended") actx.resume();
  } catch { actx = null; }
  return actx;
}
function buzz() {
  try { navigator.vibrate?.(220); } catch { /* not a phone */ }
  const a = audioCtx(); if (!a) return;
  const lp = a.createBiquadFilter(); lp.type = "lowpass"; lp.frequency.value = 900; lp.connect(a.destination);
  const t0 = a.currentTime, o = a.createOscillator(), g = a.createGain(), am = a.createOscillator(), ag = a.createGain();
  o.type = "sawtooth"; o.frequency.value = 118; am.type = "square"; am.frequency.value = 34; ag.gain.value = 0.07;
  g.gain.setValueAtTime(0, t0); g.gain.linearRampToValueAtTime(0.12, t0 + 0.012);
  g.gain.setValueAtTime(0.12, t0 + 0.2); g.gain.linearRampToValueAtTime(0, t0 + 0.24);
  am.connect(ag); ag.connect(g.gain); o.connect(g); g.connect(lp);
  o.start(t0); am.start(t0); o.stop(t0 + 0.26); am.stop(t0 + 0.26);
}
function updateLock(s, have) {
  const now = performance.now();
  if (lock && now >= lock.until) { lock = null; lockGapUntil = now + LOCK.gap; }
  if (!lock && have && s.confident && s.p_correct != null && s.p_correct >= LOCK.p && now >= lockGapUntil) {
    lock = lastLock = { bpm: s.bpm, p: s.p_correct, until: now + LOCK.hold, at: new Date() };
    buzz();
    setTimeout(() => { if (state.running) renderMeasure(); }, LOCK.hold + 30);
  }
}
// The two source cards on the landing start a session directly.
$$(".source-card[data-source]").forEach(b => b.addEventListener("click", () => { startSource(b.dataset.source); hrv = null; renderHrv(); }));
$("#stop").addEventListener("click", () => send({ cmd: "stop" }));

/* ================================================================== live state */
function onState() {
  const s = state;
  if (s.running && s.t != null && s.t !== lastT) {
    lastT = s.t;
    if (s.scores) { wHistory.push({ t: s.t, w: { ...s.scores }, sel: dominantOf(s.weights) }); while (wHistory.length && wHistory[0].t < s.t - 60) wHistory.shift(); }
  }
  if (s.error) setPill($("#pill-live"), "ERROR", "warn");
  else setPill($("#pill-live"), s.running ? "LIVE" : "IDLE", s.running ? "good" : "");
  const src = $("#pill-source");
  src.hidden = !s.running;
  if (s.running) {
    const sim = s.source === "sim";
    src.textContent = sim ? `SIMULATED / SKIN TYPE ${["", "I", "II", "III", "IV", "V", "VI"][s.fitzpatrick] || "--"}${s.sim && s.sim.pulse < 0.5 ? " / NO PULSE" : ""}` : "WEBCAM";
    src.className = "pill " + (sim ? "sim" : "info");
  }
  $("#pill-timer").hidden = !s.running;
  $("#pill-timer span").textContent = mmss(s.t);
  $("#stop").hidden = !s.running;
  // A page reload while the engine is running must reattach the preview.
  // When the source stops, drop the stream so the preview goes dark instead
  // of freezing on the last frame the browser received.
  $$("img.feed").forEach(img => {
    if (s.running && !img.getAttribute("src")) img.src = `/video.mjpg?${Date.now()}`;
    if (!s.running && img.getAttribute("src")) img.removeAttribute("src");
  });
  $$(".cam-empty").forEach(el => {
    el.hidden = !!s.running;
    el.textContent = s.error ? (s.error.includes("camera") ? "NO CAMERA FOUND. CHOOSE A SIMULATED VOLUNTEER." : s.error) : "CAMERA OFF";
  });
  renderAll();
}

function renderAll() {
  renderSimPanel();
  renderPip();
  if (view === "measure") renderMeasure();
  if (view === "methods") { renderFusion(); drawHistory(); }
  if (view === "scenarios" && hubDirty()) renderScenarios();
  if (view === "signal") { renderSignal(); renderDeckEvidence(); }
  if (view === "next") { updateHrvRing(); renderLiveness(); renderUses(); }
  if (view === "collect" && window.renderCollect) window.renderCollect();
}

/* ================================================================== charts (display only) */
function fit(cv) {
  const dpr = window.devicePixelRatio || 1, w = cv.clientWidth, h = cv.clientHeight;
  if (!w || !h) return null;
  if (cv.width !== Math.round(w * dpr) || cv.height !== Math.round(h * dpr)) { cv.width = Math.round(w * dpr); cv.height = Math.round(h * dpr); }
  const ctx = cv.getContext("2d"); ctx.setTransform(dpr, 0, 0, dpr, 0, 0); ctx.clearRect(0, 0, w, h);
  return { ctx, w, h };
}
function emptyMsg(cv, text) {
  const f = fit(cv); if (!f) return;
  f.ctx.fillStyle = css("--ink-3"); f.ctx.font = "11px 'IBM Plex Mono', monospace"; f.ctx.textAlign = "center";
  f.ctx.fillText(text, f.w / 2, f.h / 2 + 4);
}
function drawTrace(cv, ys, color, o = {}) {
  if (!ys || ys.length < 2) { emptyMsg(cv, state.running ? "COLLECTING SIGNAL" : "START A MEASUREMENT"); return; }
  const f = fit(cv); if (!f) return;
  const { ctx, w, h } = f, pad = o.pad ?? 8;
  if (o.grid) {
    ctx.strokeStyle = css("--grid"); ctx.lineWidth = 1;
    for (let i = 1; i < 4; i++) { const y = Math.round(h * i / 4) + .5; ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(w, y); ctx.stroke(); }
  }
  let lo = Infinity, hi = -Infinity;
  for (const v of ys) { if (v < lo) lo = v; if (v > hi) hi = v; }
  if (o.sym) { const m = Math.max(Math.abs(lo), Math.abs(hi)) || 1; lo = -m; hi = m; }
  if (hi - lo < 1e-9) { hi += 1; lo -= 1; }
  const X = i => i / (ys.length - 1) * w, Y = v => h - pad - (v - lo) / (hi - lo) * (h - 2 * pad);
  ctx.beginPath(); ys.forEach((v, i) => i ? ctx.lineTo(X(i), Y(v)) : ctx.moveTo(X(i), Y(v)));
  ctx.strokeStyle = color; ctx.lineWidth = o.width || 1.5; ctx.lineJoin = "round";
  if (o.glow) { ctx.shadowColor = color; ctx.shadowBlur = 8; }
  ctx.stroke(); ctx.shadowBlur = 0;
  if (o.head) { const x = X(ys.length - 1), y = Y(ys[ys.length - 1]); ctx.fillStyle = color; ctx.beginPath(); ctx.arc(x - 2, y, 2.5, 0, 7); ctx.fill(); }
}
function drawSpec(cv, f, p, color, o = {}) {
  if (!f || !p || f.length < 2) { if (o.axis) emptyMsg(cv, state.running ? "COLLECTING SIGNAL" : "START A MEASUREMENT"); else fit(cv); return; }
  const c = fit(cv); if (!c) return;
  const { ctx, w, h } = c, bottom = o.axis ? 20 : 4, top = o.axis ? 22 : 4;
  const x = v => (v - f[0]) / (f[f.length - 1] - f[0]) * w;
  const y = v => h - bottom - Math.max(0, Math.min(1, v)) * (h - bottom - top);
  if (o.axis) {
    ctx.strokeStyle = css("--grid"); ctx.lineWidth = 1;
    ctx.fillStyle = css("--ink-3"); ctx.font = "10px 'IBM Plex Mono', monospace"; ctx.textAlign = "center";
    [60, 90, 120, 150, 180, 210].forEach(b => { if (b > f[0] && b < f[f.length - 1]) { ctx.beginPath(); ctx.moveTo(x(b) + .5, top); ctx.lineTo(x(b) + .5, h - bottom); ctx.stroke(); ctx.fillText(b, x(b), h - 5); } });
    ctx.textAlign = "left"; ctx.fillText("BPM", 2, h - 5);
  }
  const g = ctx.createLinearGradient(0, top, 0, h - bottom); g.addColorStop(0, color + "55"); g.addColorStop(1, color + "00");
  ctx.beginPath(); ctx.moveTo(x(f[0]), h - bottom); f.forEach((v, i) => ctx.lineTo(x(v), y(p[i]))); ctx.lineTo(x(f[f.length - 1]), h - bottom); ctx.closePath();
  ctx.fillStyle = g; ctx.fill();
  ctx.beginPath(); f.forEach((v, i) => i ? ctx.lineTo(x(v), y(p[i])) : ctx.moveTo(x(v), y(p[i])));
  ctx.strokeStyle = color; ctx.lineWidth = o.width || 1.4; ctx.stroke();
  if (o.peak != null) {
    const px = x(o.peak);
    ctx.strokeStyle = o.peakColor || css("--lime"); ctx.lineWidth = 1; ctx.setLineDash([3, 3]);
    ctx.beginPath(); ctx.moveTo(px + .5, top - (o.axis ? 8 : 0)); ctx.lineTo(px + .5, h - bottom); ctx.stroke(); ctx.setLineDash([]);
    if (o.axis) {
      const label = `${fmt(o.peak, 1)} BPM`;
      ctx.font = "11px 'IBM Plex Mono', monospace"; const tw = ctx.measureText(label).width + 12;
      const bx = Math.min(Math.max(px - tw / 2, 0), w - tw);
      ctx.fillStyle = o.peakColor || css("--lime"); ctx.fillRect(bx, 0, tw, 18);
      ctx.fillStyle = css("--lime-ink"); ctx.textAlign = "left"; ctx.fillText(label, bx + 6, 13);
    }
  }
}

/* ================================================================== measure */
function renderMeasure() {
  const s = state, have = haveBpm(), C = MCOL();
  $("#measure-idle").hidden = !!s.running; $("#measure-live").hidden = !s.running;
  if (!s.running) return;
  const checks = s.checks || {};
  $$("#checks li").forEach(li => li.classList.toggle("ok", !!checks[li.dataset.check]));
  const bad = ["face", "light", "still"].filter(k => !checks[k]);
  $("#check-help").textContent = bad.includes("face") ? "Move so your whole face is inside the frame."
    : bad.includes("light") ? "Face a window or lamp. Avoid bright light behind you."
    : bad.includes("still") ? "Rest your head. Small movements are fine."
    : "Red box: tracked face. Green boxes: forehead and cheeks, where the pulse is read.";

  updateLock(s, have);
  const card = $(".live-readout"), was = card.classList.contains("locked");
  card.classList.toggle("locked", !!lock);
  if (lock && !was) { card.classList.remove("buzzing"); void card.offsetWidth; card.classList.add("buzzing"); }
  $("#lock-tag").hidden = !lock;
  $("#live-lock").textContent = lastLock ? `${fmt(lastLock.bpm)} BPM / ${pct(lastLock.p)}` : "--";
  const b = $("#live-bpm");
  b.textContent = lock ? fmt(lock.bpm) : have ? fmt(s.bpm) : "--";
  b.className = "big mono" + (lock ? "" : !have ? " none" : s.confident ? "" : " low");
  setPill($("#live-state"), lock ? "LOCKED" : !have ? "COLLECTING" : s.confident ? "LIVE" : "LOW CONFIDENCE", lock || (have && s.confident) ? "good" : !have ? "info" : "warn");
  const ring = $("#ring-fg");
  ring.setAttribute("stroke-dasharray", `${(lock ? 100 : have && s.p_correct != null ? s.p_correct * 100 : 0).toFixed(1)} 100`);
  ring.classList.toggle("low", !lock && have && !s.confident);
  $("#live-p").textContent = have ? pct(s.p_correct) : `${fmt(Math.max(0, (s.needed_s || 8) - (s.buffered_s || 0)))} S TO GO`;
  $("#live-p").className = "mono " + (have ? (s.confident ? "good" : "warn") : "");
  $("#live-q").textContent = have ? fmt(s.quality, 2) : "--";
  $("#live-truth-wrap").hidden = !s.true_bpm;
  if (s.true_bpm) $("#live-truth").textContent = `${fmt(s.true_bpm, 1)} BPM`;

  const w = s.scores, sel = dominantOf(s.weights);
  $("#mini-weights").innerHTML = METHODS.map(m => wbar(MNAME[m] + (m === sel ? " *" : ""), w ? w[m] : 0, 1, C[m], w ? pct(w[m]) : "--", m === sel ? "sel" : "")).join("");
  $("#tm-src").textContent = s.source === "sim" ? "SIMULATED" : "WEBCAM";
  $("#tm-buf").textContent = `${fmt(s.buffered_s, 1)} S`;
  $("#tm-motion").textContent = s.motion_px != null ? `${fmt(s.motion_px, 1)} PX` : "--";
  drawTrace($("#c-pulse"), s.trace?.pulse, css("--coral"), { width: 1.8, glow: true, grid: true, head: true, sym: true });
  $("#pulse-best").textContent = s.trace?.best ? `FROM ${MNAME[s.trace.best]}, THE SELECTED METHOD` : "";
}

/* ================================================================== methods: TRACE fusion module */
function buildFusion(host) {
  host.innerHTML = `
    <div class="fusion-h">
      <span class="label mono">TRACE FUSION</span>
      <span class="pill small" data-r="state">WAITING</span>
    </div>
    <div class="fusion">
      <div class="channels">${METHODS.map(m => `
        <div class="ch" data-m="${m}">
          <span class="ch-name"><i></i>${MNAME[m]}</span>
          <span class="ch-bpm mono"><span data-r="bpm">--</span><small>BPM</small></span>
          <div class="ch-bar" role="meter" aria-label="${MNAME[m]} weight" aria-valuemin="0" aria-valuemax="100"><i></i></div>
          <div class="ch-meta"><span class="w">TRUST <b data-r="w">--</b></span><span>QUALITY <b data-r="q">--</b></span><span class="ch-tags" data-r="tags"></span></div>
          <div class="ch-viz"><canvas data-r="wave" aria-hidden="true"></canvas><canvas data-r="spec" aria-hidden="true"></canvas></div>
        </div>`).join("")}
      </div>
      <div class="routes-wrap"><svg class="routes" viewBox="0 0 100 300" preserveAspectRatio="none" aria-hidden="true">
        ${METHODS.map((m, i) => `<path data-route="${m}" d="M0 ${50 + i * 100} C 55 ${50 + i * 100}, 45 150, 100 150" vector-effect="non-scaling-stroke"/>
        <path class="flowdash" data-dash="${m}" d="M0 ${50 + i * 100} C 55 ${50 + i * 100}, 45 150, 100 150" vector-effect="non-scaling-stroke"/>`).join("")}
      </svg></div>
      <div class="trace-node">
        <span class="tn-k">TRACE</span>
        <span class="tn-bpm" data-r="tbpm">--<small>BPM</small></span>
        <dl>
          <div><dt>CONFIDENCE</dt><dd data-r="tp">--</dd></div>
          <div><dt>SELECTED</dt><dd data-r="td">--</dd></div>
        </dl>
        <canvas data-r="fspec" aria-label="Fused spectrum"></canvas>
      </div>
    </div>
    <p class="fusion-note">Each method gives its own spectrum. TRACE suppresses the frequencies a motion reference flags, scores every spectrum by how sharp its remaining peak is (the trust bars), and every half second selects the method it trusts most. The heart rate is read from that method's cleaned spectrum.</p>`;
  host.dataset.built = "1";
}
function renderFusion() {
  const s = state, C = MCOL(), thr = s.params?.confidence ?? 0.24, truth = s.true_bpm;
  const host = $(".fusion-host");
  if (!host.dataset.built) buildFusion(host);
  const q = r => host.querySelector(`[data-r="${r}"]`);
  const w = s.scores || {}, dom = dominantOf(s.weights);
  setPill(q("state"), !s.running ? "START A MEASUREMENT" : !s.weights ? "COLLECTING" : s.confident ? "STEADY" : "LOW CONFIDENCE",
    !s.running ? "" : !s.weights ? "info" : s.confident ? "good" : "warn");
  METHODS.forEach(m => {
    const ch = host.querySelector(`.ch[data-m="${m}"]`), mm = s.methods?.[m];
    const wv = w[m] ?? 0;
    ch.style.setProperty("--w", s.scores ? wv : .3);
    ch.classList.toggle("dominant", m === dom);
    ch.querySelector(".ch-bar i").style.width = `${Math.round(wv * 100)}%`;
    ch.querySelector(".ch-bar").setAttribute("aria-valuenow", String(Math.round(wv * 100)));
    ch.querySelector('[data-r="bpm"]').textContent = mm ? fmt(mm.bpm, 1) : "--";
    ch.querySelector('[data-r="w"]').textContent = s.scores ? pct(wv) : "--";
    ch.querySelector('[data-r="q"]').textContent = mm ? fmt(mm.quality, 2) : "--";
    const tags = [];
    if (mm) {
      if (m === dom) tags.push(["lead", "SELECTED"]);
      if (mm.quality < thr) tags.push(["lowq", "WEAK SIGNAL"]);
      if ((mm.artifact || 0) > ART_TAG) tags.push(["art", "MOTION"]);
      if (truth && Math.abs(mm.bpm - truth) > 5) tags.push(["art", "WRONG"]);
    }
    ch.querySelector('[data-r="tags"]').innerHTML = tags.map(([c, t]) => `<span class="tag ${c}">${t}</span>`).join("");
    host.querySelectorAll(`[data-route="${m}"]`).forEach(p => { p.style.stroke = C[m]; p.style.strokeWidth = 1 + wv * 12; p.style.strokeOpacity = .15 + wv * .7; });
    host.querySelectorAll(`[data-dash="${m}"]`).forEach(p => { p.style.stroke = "#fff"; p.style.strokeWidth = 1.2; p.style.strokeOpacity = s.weights && m === dom ? .8 : 0; });
    drawTrace(ch.querySelector('[data-r="wave"]'), s.method_traces?.[m], C[m], { width: 1.1, pad: 3 });
    drawSpec(ch.querySelector('[data-r="spec"]'), s.spectrum?.f, s.method_spectra?.[m], C[m], { peak: mm ? mm.bpm : null, peakColor: C[m], width: 1.1 });
  });
  const tb = q("tbpm");
  tb.innerHTML = `${haveBpm() ? fmt(s.bpm, 1) : "--"}<small>BPM</small>`;
  tb.classList.toggle("low", haveBpm() && !s.confident);
  q("tp").textContent = haveBpm() ? pct(s.p_correct) : "--";
  q("td").textContent = dom ? `${MNAME[dom]} ${pct(w[dom])}` : "--";
  drawSpec(q("fspec"), s.spectrum?.f, s.spectrum?.p, css("--lime"), { peak: s.spectrum?.peak, width: 1.4 });
}

function drawHistory() {
  const cv = $("#c-hist"), f = fit(cv); if (!f) return;
  const { ctx, w, h } = f, C = MCOL(), pad = 16, pw = w - 90;
  ctx.strokeStyle = css("--grid"); ctx.lineWidth = 1;
  [0, .25, .5, .75, 1].forEach(v => { const y = Math.round(pad + (1 - v) * (h - 2 * pad)) + .5; ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(pw, y); ctx.stroke(); });
  if (wHistory.length < 2) {
    ctx.fillStyle = css("--ink-3"); ctx.font = "11px 'IBM Plex Mono', monospace"; ctx.textAlign = "center";
    ctx.fillText(state.running ? "COLLECTING SIGNAL" : "START A MEASUREMENT", pw / 2, h / 2); return;
  }
  const t1 = wHistory[wHistory.length - 1].t, t0 = t1 - 60;
  const X = t => (t - t0) / 60 * pw, Y = v => pad + (1 - v) * (h - 2 * pad);
  let base = wHistory.map(() => 0);
  METHODS.forEach(m => {
    const top = wHistory.map((e, i) => base[i] + (e.w[m] || 0));
    ctx.beginPath();
    wHistory.forEach((e, i) => i ? ctx.lineTo(X(e.t), Y(top[i])) : ctx.moveTo(X(e.t), Y(top[i])));
    for (let i = wHistory.length - 1; i >= 0; i--) ctx.lineTo(X(wHistory[i].t), Y(base[i]));
    ctx.closePath(); ctx.fillStyle = C[m] + "3a"; ctx.fill();
    ctx.beginPath(); wHistory.forEach((e, i) => i ? ctx.lineTo(X(e.t), Y(top[i])) : ctx.moveTo(X(e.t), Y(top[i])));
    ctx.strokeStyle = C[m]; ctx.lineWidth = 1.2; ctx.stroke();
    const last = wHistory[wHistory.length - 1], mid = (base[base.length - 1] + top[top.length - 1]) / 2;
    ctx.fillStyle = C[m]; ctx.font = "11px 'IBM Plex Mono', monospace"; ctx.textAlign = "left";
    ctx.fillText(`${MNAME[m]} ${pct(last.w[m])}`, pw + 10, Math.max(pad + 6, Math.min(h - pad, Y(mid) + 4)));
    base = top;
  });
  // Selection strip: which method TRACE picked at each read-out.
  wHistory.forEach((e, i) => {
    if (!e.sel || i === 0) return;
    ctx.fillStyle = C[e.sel];
    ctx.fillRect(X(wHistory[i - 1].t), h - pad + 3, Math.max(1, X(e.t) - X(wHistory[i - 1].t)), 5);
  });
  ctx.fillStyle = css("--ink-3"); ctx.font = "10px 'IBM Plex Mono', monospace"; ctx.textAlign = "left"; ctx.fillText("SELECTED", pw + 10, h - pad + 9);
  ctx.textAlign = "left"; ctx.fillText("-60 S", 0, h - 2); ctx.textAlign = "right"; ctx.fillText("NOW", pw, h - 2);
}


/* ================================================================== simulator panel */
// Mean cheek colour the simulator renders for each skin type (CLAUDE.md 11.1).
const SKIN_RGB = { 1: [214, 183, 168], 2: [201, 167, 143], 3: [177, 139, 104], 4: [149, 109, 69], 5: [119, 80, 43], 6: [91, 56, 27] };
const ROMAN = ["", "I", "II", "III", "IV", "V", "VI"];
const MOTION = [["Still", 0.1], ["Calm", 0.3], ["Natural", 0.5], ["Talking", 1.2], ["Restless", 2.5]];
const GLOW = [["Off", 0], ["Normal", 0.002], ["Strong", 0.008]];
const BASE_SIM = { motion: 0.3, light: 1, flicker_hz: 0, flicker_depth: 0.03, screen_light: 0.002, bpm: 72 };
const PRESETS = [
  ["Ideal", { ...BASE_SIM, motion: 0.1 }],
  ["Talking", { ...BASE_SIM, motion: 1.2 }],
  ["Dim room", { ...BASE_SIM, light: 0.35 }],
  ["Flickering lamp", { ...BASE_SIM, flicker_hz: 1.5 }],
  ["Screen glow", { ...BASE_SIM, screen_light: 0.008 }],
  ["Fast heart", { bpm: 120 }],
];
let simSettings = { fitzpatrick: 2, pulse: 1, ...BASE_SIM };
let simTimer = null, simEditUntil = 0, lastFlicker = 1.5;

function pushSim(change) {
  simSettings = { ...simSettings, ...change };
  simEditUntil = performance.now() + 1500; // do not let a stale server echo undo a fresh change
  $$(".sim-host").forEach(syncSimPanel);
  clearTimeout(simTimer);
  simTimer = setTimeout(() => { send({ cmd: "sim", params: simSettings }); simTimer = null; }, 120);
}

function buildSimPanel(host) {
  host.innerHTML = `
    <header class="card-h"><span class="label mono">SIMULATOR</span><span class="mono muted">CHANGES APPLY LIVE. THE TRUE RATE IS ALWAYS KNOWN.</span></header>
    <div class="sim-grid">
      <div class="ctl"><span class="label mono">SKIN TYPE <b class="mono" data-v="fz"></b></span>
        <div class="swatches" role="radiogroup" aria-label="Skin type">${[1, 2, 3, 4, 5, 6].map(k =>
          `<button type="button" role="radio" data-fz="${k}" style="--sw:rgb(${SKIN_RGB[k].join(",")})" aria-label="Fitzpatrick ${ROMAN[k]}"><i></i><span class="mono">${ROMAN[k]}</span></button>`).join("")}</div></div>
      <div class="ctl"><span class="label mono">TRUE HEART RATE <b class="mono" data-v="bpm"></b></span>
        <input type="range" min="45" max="150" step="1" data-k="bpm" aria-label="True heart rate"></div>
      <div class="ctl"><span class="label mono">HEAD MOTION</span>
        <div class="seg small" data-seg="motion" role="radiogroup" aria-label="Head motion">${MOTION.map(([n, v]) => `<button type="button" role="radio" data-val="${v}">${n}</button>`).join("")}</div></div>
      <div class="ctl"><span class="label mono">LIGHT LEVEL <b class="mono" data-v="light"></b></span>
        <input type="range" min="0.25" max="1.45" step="0.05" data-k="light" aria-label="Light level"></div>
      <div class="ctl"><span class="label mono">FLICKERING LAMP <b class="mono" data-v="flicker"></b></span>
        <div class="row"><div class="seg small" data-seg="flick" role="radiogroup" aria-label="Flickering lamp"><button type="button" role="radio" data-val="0">Off</button><button type="button" role="radio" data-val="1">On</button></div>
        <input type="range" min="50" max="150" step="1" data-k="flicker_rate" aria-label="Flicker rate per minute"></div></div>
      <div class="ctl"><span class="label mono">SCREEN GLOW</span>
        <div class="seg small" data-seg="screen_light" role="radiogroup" aria-label="Screen glow">${GLOW.map(([n, v]) => `<button type="button" role="radio" data-val="${v}">${n}</button>`).join("")}</div></div>
      <div class="ctl"><span class="label mono">WHAT THE CAMERA SEES</span>
        <div class="seg small" data-seg="pulse" role="radiogroup" aria-label="Living face or photo"><button type="button" role="radio" data-val="1">Living face</button><button type="button" role="radio" data-val="0">Photo (no pulse)</button></div></div>
    </div>
    <div class="presets"><span class="label mono">PRESETS</span>${PRESETS.map(([n], i) => `<button type="button" class="btn ghost small" data-preset="${i}">${n}</button>`).join("")}</div>`;
  host.querySelectorAll("[data-fz]").forEach(b => b.addEventListener("click", () => pushSim({ fitzpatrick: +b.dataset.fz })));
  host.querySelector('[data-k="bpm"]').addEventListener("input", e => pushSim({ bpm: +e.target.value }));
  host.querySelector('[data-k="light"]').addEventListener("input", e => pushSim({ light: +e.target.value }));
  host.querySelector('[data-k="flicker_rate"]').addEventListener("input", e => pushSim({ flicker_hz: +e.target.value / 60 }));
  host.querySelectorAll('[data-seg="motion"] button').forEach(b => b.addEventListener("click", () => pushSim({ motion: +b.dataset.val })));
  host.querySelectorAll('[data-seg="screen_light"] button').forEach(b => b.addEventListener("click", () => pushSim({ screen_light: +b.dataset.val })));
  host.querySelectorAll('[data-seg="pulse"] button').forEach(b => b.addEventListener("click", () => pushSim({ pulse: +b.dataset.val })));
  host.querySelectorAll('[data-seg="flick"] button').forEach(b => b.addEventListener("click", () =>
    pushSim({ flicker_hz: +b.dataset.val ? lastFlicker : 0 })));
  host.querySelectorAll("[data-preset]").forEach(b => b.addEventListener("click", () => pushSim(PRESETS[+b.dataset.preset][1])));
  host.dataset.built = "1";
  syncSimPanel(host);
}

function syncSimPanel(host) {
  if (!host.dataset.built) return;
  const s = simSettings, near = (a, b) => Math.abs(a - b) < 1e-6;
  if (s.flicker_hz > 0) lastFlicker = s.flicker_hz;
  host.querySelectorAll("[data-fz]").forEach(b => b.setAttribute("aria-checked", String(+b.dataset.fz === s.fitzpatrick)));
  const setR = (k, v) => { const el = host.querySelector(`[data-k="${k}"]`); if (el && document.activeElement !== el) el.value = v; };
  setR("bpm", s.bpm); setR("light", s.light); setR("flicker_rate", Math.round(lastFlicker * 60));
  host.querySelector('[data-v="fz"]').textContent = `FITZPATRICK ${ROMAN[s.fitzpatrick]}`;
  host.querySelector('[data-v="bpm"]').textContent = `${Math.round(s.bpm)} BPM`;
  host.querySelector('[data-v="light"]').textContent = `${Math.round(s.light * 100)}%`;
  host.querySelector('[data-v="flicker"]').textContent = s.flicker_hz > 0 ? `${Math.round(s.flicker_hz * 60)} / MIN` : "OFF";
  host.querySelector('[data-k="flicker_rate"]').disabled = !(s.flicker_hz > 0);
  host.querySelectorAll('[data-seg="motion"] button').forEach(b => b.setAttribute("aria-checked", String(near(+b.dataset.val, s.motion))));
  host.querySelectorAll('[data-seg="screen_light"] button').forEach(b => b.setAttribute("aria-checked", String(near(+b.dataset.val, s.screen_light))));
  host.querySelectorAll('[data-seg="pulse"] button').forEach(b => b.setAttribute("aria-checked", String((+b.dataset.val === 1) === ((s.pulse ?? 1) >= 0.5))));
  host.querySelectorAll('[data-seg="flick"] button').forEach(b => b.setAttribute("aria-checked", String((+b.dataset.val === 1) === (s.flicker_hz > 0))));
}

function renderSimPanel() {
  const on = !!(state.running && state.source === "sim");
  // Follow the server's settings unless the presenter has just changed one.
  if (on && state.sim && performance.now() > simEditUntil) simSettings = { ...simSettings, ...state.sim };
  $$(".sim-host").forEach(host => {
    host.hidden = !on;
    if (on && !host.dataset.built) buildSimPanel(host);
    else if (on) syncSimPanel(host);
  });
}

/* ================================================================== scenarios: the results hub */
// Everything here is read from /api/results (app/results.py). Three sources,
// each against its own reference; the page never recomputes a number.
// Layout: one card per source on top (TRACE against the POS baseline, click
// to open), then that source's result card and its details in reading order.
const SOURCES = [
  { key: "simulated", name: "Simulated faces", unit: "RUNS", tag: "HELD-OUT TEST", tagClass: "good",
    blurb: "Exact true heart rate; skin, motion and light varied on purpose" },
  { key: "ubfc", name: "Public dataset", unit: "SUBJECTS", tag: "TUNING DATA", tagClass: "warn",
    blurb: "UBFC-rPPG, finger pulse oximeter; people sitting still" },
  { key: "volunteers", name: "Our volunteers", unit: "PEOPLE", tag: "REAL PEOPLE", tagClass: "good",
    blurb: "Our webcam and a smartwatch, recorded on the Collect screen" },
];
let hub = null, hubTab = localGet("res-tab") || "simulated", hubKey = "", scnSkin = "all";
async function loadHub() {
  try { hub = await (await fetch("/api/results", { cache: "no-store" })).json(); } catch { hub = null; }
  hubKey = ""; renderAll();
}
function hubDirty() {
  const k = [hubTab, scnSkin, !!hub, !!(state.running && state.source === "sim"), document.documentElement.dataset.theme].join("|");
  if (k === hubKey) return false;
  hubKey = k; return true;
}
const COLS = ["green", "chrom", "pos", "trace"];
const COLNAME = { green: "GREEN", chrom: "CHROM", pos: "POS", trace: "TRACE" };
function maeCells(mae) {
  if (!mae) return COLS.map(() => "<td>--</td>").join("");
  const best = Math.min(...COLS.map(m => mae[m] ?? Infinity));
  return COLS.map(m => `<td class="${mae[m] === best ? "best" : ""}">${fmt(mae[m], 1)}</td>`).join("");
}
function setHubTab(k) { hubTab = k; localSet("res-tab", k); hubKey = ""; renderScenarios(); }
function renderSources() {
  const C = MCOL();
  $("#res-sources").innerHTML = SOURCES.map(src => {
    const s = hub?.[src.key] || {}, on = src.key === hubTab;
    if (!s.available) return `<button type="button" role="tab" class="src-card empty" aria-selected="${on}" data-tab="${src.key}">
      <span class="src-top"><b>${src.name}</b></span><span class="src-blurb">${src.blurb}</span>
      <span class="src-none mono">NOT YET COLLECTED</span></button>`;
    const m = s.overall.mae, d = m.pos - m.trace;
    const verdict = Math.abs(d) < 0.05 ? "TIED WITH POS" : d > 0 ? `${fmt(d, 1)} BPM BETTER THAN POS` : `${fmt(-d, 1)} BPM BEHIND POS`;
    return `<button type="button" role="tab" class="src-card" aria-selected="${on}" data-tab="${src.key}">
      <span class="src-top"><b>${src.name}</b><span class="pill small ${src.tagClass}">${src.tag}</span></span>
      <span class="src-blurb">${src.blurb}</span>
      <span class="src-nums">
        <span class="src-trace"><span class="mono lbl">TRACE</span><span class="mono big-n">${fmt(m.trace, 1)}</span></span>
        <span class="src-base" style="--c:${C.pos}"><span class="mono lbl">POS</span><span class="mono mid-n">${fmt(m.pos, 1)}</span></span>
        <span class="src-unit mono">BPM MEAN ERROR</span>
      </span>
      <span class="src-foot mono"><span class="${d > 0.05 ? "good" : d < -0.05 ? "warn" : ""}">${verdict}</span><span>${s.subjects} ${src.unit} / ${s.readings.toLocaleString()} READINGS</span></span>
    </button>`;
  }).join("");
  $$("#res-sources [data-tab]").forEach(b => b.addEventListener("click", () => setHubTab(b.dataset.tab)));
}
function resultCard(s, src) {
  const O = s.overall, C = MCOL(), mx = Math.max(...COLS.map(m => O.mae[m])) * 1.05;
  return `<article class="card span-12 result-card">
    <header class="card-h"><span class="label mono">${src.name.toUpperCase()} / MEAN ERROR IN BPM, LOWER IS BETTER</span>
      <span class="btn-row">${src.key === "volunteers" ? `<a class="btn ghost small" href="/api/collect/study.csv" download title="Every watch reading with each method's read-out; volunteer codes only, never names"><svg><use href="#i-download"/></svg>Watch readings (CSV)</a>` : ""}<a class="btn ghost small" href="/api/results" download="trace-rppg-results.json" title="Every source's results, as shown on this screen"><svg><use href="#i-download"/></svg>All results (JSON)</a></span></header>
    <p class="mono muted against">AGAINST: ${esc(s.reference).toUpperCase()}</p>
    <div class="result-grid">
      <div class="wbars">${COLS.map(m => wbar(COLNAME[m], O.mae[m], mx, m === "trace" ? css("--lime") : C[m], fmt(O.mae[m], 1), m === "trace" ? "trace" : "")).join("")}</div>
      <dl class="kv">
        <div><dt class="mono">TRACE WITHIN 5 BPM</dt><dd class="mono">${pct(O.within5?.trace)}</dd></div>
        <div><dt class="mono">POS WITHIN 5 BPM</dt><dd class="mono">${pct(O.within5?.pos)}</dd></div>
        <div><dt class="mono">TRACE MARKED CONFIDENT</dt><dd class="mono">${pct(O.confident)}</dd></div>
        <div><dt class="mono">ERROR WHEN CONFIDENT</dt><dd class="mono">${O.mae_confident == null ? "--" : fmt(O.mae_confident, 1) + " BPM"}</dd></div>
        ${O.mae_flagged == null ? "" : `<div><dt class="mono">ERROR WHEN FLAGGED</dt><dd class="mono">${fmt(O.mae_flagged, 1)} BPM</dd></div>`}
      </dl>
    </div>
    ${s.note ? `<p class="foot">${esc(s.note)}</p>` : ""}
  </article>`;
}
function sectionTitle(text, sub) {
  return `<div class="span-12 res-section"><h3>${text}</h3>${sub ? `<p>${sub}</p>` : ""}</div>`;
}
function renderScenarios() {
  if (!hub) { $("#res-body").innerHTML = `<div class="card"><div class="empty-state small"><p>Loading results.</p></div></div>`; return; }
  renderSources();
  const src = SOURCES.find(x => x.key === hubTab) || SOURCES[0], s = hub[src.key] || {};
  const body = $("#res-body");
  if (!s.available) {
    body.innerHTML = `<div class="card"><div class="empty-state"><div><svg><use href="#i-grid"/></svg><p class="t">No ${src.name.toLowerCase()} results yet.</p><p class="mono how-to"></p></div></div></div>`;
    body.querySelector(".how-to").textContent = s.how_to || "";
    return;
  }
  const bd = t => (s.breakdowns || []).find(b => b.title === t);
  let html = `<div class="bento">` + resultCard(s, src);
  if (src.key === "simulated") {
    html += sectionTitle("Which method wins where", "Each condition can be recreated live: start a simulated volunteer, then press Try it.") + simulatedSection(s);
  } else if (src.key === "ubfc") {
    html += sectionTitle("Subject by subject", "Error per recording against the finger oximeter. Best of the four in green.") + splitBreakdown(bd("BY SUBJECT"));
  } else {
    if (hub.learned?.available) html += sectionTitle("Classical vs learned", "Would machine learning do better? The same watch readings, scored the same way.") + learnedCard(hub.learned);
    html += sectionTitle("Where it works and where it struggles", "Real volunteers grouped by skin type, motion, lighting and age.");
    for (const t of ["BY SKIN TYPE", "BY MOTION", "BY LIGHTING", "BY AGE GROUP"]) if (bd(t)) html += breakdownCard(bd(t), "span-6");
    if (bd("BY VOLUNTEER")) html += sectionTitle("Volunteer by volunteer", "Codes only; names stay on the Collect screen. SELECTED shows how often TRACE chose green, CHROM and POS.") + breakdownCard(bd("BY VOLUNTEER"));
  }
  body.innerHTML = html + "</div>";
  body.querySelectorAll("[data-try]").forEach(b => b.addEventListener("click", () => tryScenario(+b.dataset.try)));
  body.querySelectorAll("[data-skin]").forEach(b => b.addEventListener("click", () => { scnSkin = b.dataset.skin; hubKey = ""; renderScenarios(); }));
}
// Classical against learned on the same watch readings (app/results.py: learned()).
function kindColor(r) {
  const C = MCOL();
  return r.kind === "classical" ? C[r.key] : r.kind === "trace" ? css("--lime") : r.kind === "learned" ? css("--amber")
    : r.kind === "neural" ? css("--violet") : css("--ink-3");
}
function learnedCard(L) {
  const mx = Math.max(...L.rows.map(r => r.mae)) * 1.05;
  return `<article class="card span-12">
    <header class="card-h"><span class="label mono">SAME ${L.n_readings} WATCH READINGS, ${L.n_people} PEOPLE / MEAN ERROR IN BPM</span><span class="mono muted">LOWER IS BETTER</span></header>
    <div class="table-scroll"><table class="data learned"><thead><tr><th>METHOD</th><th>KIND</th><th class="barcol"></th><th>ERROR</th><th>WITHIN 5 BPM</th><th>WHAT IT IS</th></tr></thead><tbody>${
      L.rows.map(r => `<tr class="${r.kind}"><td><span class="who" style="--c:${kindColor(r)}"><i></i>${esc(r.label)}</span></td><td class="mono kind">${r.kind.toUpperCase()}</td>
        <td class="barcol"><span class="minibar" style="--c:${kindColor(r)};--w:${Math.min(100, r.mae / mx * 100).toFixed(1)}%"></span></td>
        <td class="mono">${fmt(r.mae, 2)}</td><td class="mono">${pct(r.within5)}</td><td class="how">${esc(r.note)}</td></tr>`).join("")}</tbody></table></div>
    <p class="foot">Option 1, a pretrained deep network (FactorizePhys), reads the same face videos. Option 2, a small learned model, chooses among green, CHROM and POS; it was trained only on UBFC-rPPG and simulated faces, never on these volunteers. Neither changes what TRACE reports. The oracle is not a method: it peeks at the watch, so it shows the best any chooser could do with these three methods.</p>
  </article>`;
}
function breakdownCard(b, span = "span-12") {
  const selCol = b.rows.some(r => r.selected) && span === "span-12";
  return `<article class="card ${span}"><header class="card-h"><span class="label mono">${b.title}</span></header>
    <div class="table-scroll"><table class="data"><thead><tr><th>${b.title.replace("BY ", "")}</th><th>READINGS</th>${b.rows.some(r => r.people) ? "<th>PEOPLE</th>" : ""}${COLS.map(m => `<th>${COLNAME[m]}</th>`).join("")}<th>TRACE WITHIN 5</th>${selCol ? "<th>SELECTED G / C / P (%)</th>" : ""}</tr></thead><tbody>${
      b.rows.map(r => `<tr><td>${esc(r.label)}</td><td>${r.n}</td>${b.rows.some(x => x.people) ? `<td>${r.people ?? "--"}</td>` : ""}${maeCells(r.mae)}<td>${pct(r.within5?.trace)}</td>${selCol ? `<td>${r.selected ? METHODS.map(m => fmt(r.selected[m] * 100)).join(" / ") : "--"}</td>` : ""}</tr>`).join("")}</tbody></table></div></article>`;
}
// A long table (UBFC subjects) split into two side-by-side halves.
function splitBreakdown(b) {
  if (!b) return "";
  const half = Math.ceil(b.rows.length / 2);
  return breakdownCard({ ...b, rows: b.rows.slice(0, half) }, "span-6") + breakdownCard({ ...b, rows: b.rows.slice(half) }, "span-6");
}
function simulatedSection(s) {
  const C = MCOL(), canTry = state.running && state.source === "sim";
  const skins = ["all", 1, 2, 3, 4, 5, 6];
  const rows = s.scenarios.map((sc, i) => {
    const a = scnSkin === "all" ? sc.all : sc.by_skin[scnSkin];
    const top = METHODS.reduce((x, m) => a.dominant[m] > a.dominant[x] ? m : x, "green");
    return `<tr><td>${sc.label}</td><td class="how">${sc.how}</td>${maeCells(a.mae)}
      <td><span class="who" style="--c:${C[top]}"><i></i>${MNAME[top]} ${pct(a.dominant[top])}</span></td><td>${pct(a.confident)}</td>
      <td><button type="button" class="btn ghost small" data-try="${i}" ${canTry ? "" : "disabled"} title="${canTry ? "Apply to the live volunteer" : "Start a simulated volunteer first"}">Try it</button></td></tr>`;
  }).join("");
  const heat = v => `rgba(255, 107, 120, ${Math.min(0.85, v / 30).toFixed(2)})`;
  const skinRows = ((s.breakdowns || []).find(b => b.title === "BY SKIN TYPE") || {}).rows || [];
  return `<article class="card span-12">
      <header class="card-h"><span class="label mono">CONDITIONS / MEAN ERROR IN BPM</span>
        <div class="seg small">${skins.map(k => `<button type="button" data-skin="${k}" aria-checked="${String(k) === String(scnSkin)}">${k === "all" ? "All skin" : ROMAN[k]}</button>`).join("")}</div></header>
      <div class="table-scroll"><table class="data scn"><thead><tr><th>CONDITION</th><th>HOW TO CAUSE IT</th>${COLS.map(m => `<th>${COLNAME[m]}</th>`).join("")}<th>SELECTED MOST</th><th>CONFIDENT</th><th></th></tr></thead><tbody>${rows}</tbody></table></div>
      <p class="foot">${s.seeds} volunteers x ${s.seconds} s per skin type and condition, one reading every 2.5 s. Best of the four in green.</p>
    </article>
    ${sectionTitle("Every skin tone", "TRACE's error for each skin type (Fitzpatrick I to VI) in each condition, and the overall comparison per skin type.")}
    <article class="card span-7">
      <header class="card-h"><span class="label mono">TRACE ERROR BY SKIN TYPE AND CONDITION / BPM</span></header>
      <div class="table-scroll"><table class="data heat"><thead><tr><th>CONDITION</th>${[1, 2, 3, 4, 5, 6].map(k => `<th>${ROMAN[k]}</th>`).join("")}</tr></thead><tbody>${
        s.scenarios.map(sc => `<tr><td>${sc.label}</td>${[1, 2, 3, 4, 5, 6].map(k => { const v = sc.by_skin[k].mae.trace; return `<td style="background:${heat(v)}">${fmt(v, 1)}</td>`; }).join("")}</tr>`).join("")}</tbody></table></div>
      <p class="foot">Redder cells are worse.</p>
    </article>
    <article class="card span-5">
      <header class="card-h"><span class="label mono">BY SKIN TYPE / ALL CONDITIONS</span></header>
      <div class="table-scroll"><table class="data"><thead><tr><th>TYPE</th>${COLS.map(m => `<th>${COLNAME[m]}</th>`).join("")}<th>TRACE W5</th></tr></thead><tbody>${
        skinRows.map(r => `<tr><td>${esc(r.label.replace("Type ", ""))}</td>${maeCells(r.mae)}<td>${pct(r.within5?.trace)}</td></tr>`).join("")}</tbody></table></div>
    </article>`;
}
function tryScenario(i) {
  const sc = hub.simulated.scenarios[i];
  pushSim({ ...BASE_SIM, ...sc.settings, ...(scnSkin !== "all" ? { fitzpatrick: +scnSkin } : {}) });
  go("methods");
}

/* ================================================================== how it works */
function renderSignal() {
  const s = state, st = s.stages || {};
  drawTrace($("#c-s1"), st.raw, css("--ink-2"), { width: 1.3, grid: true });
  drawTrace($("#c-s2"), st.detrended, css("--m-green"), { width: 1.4, grid: true, sym: true });
  drawTrace($("#c-s3"), st.filtered, css("--coral"), { width: 1.6, grid: true, sym: true, glow: true });
  drawSpec($("#c-s4"), s.spectrum?.f, s.spectrum?.p, css("--violet"), { axis: true, peak: s.spectrum?.peak, width: 1.6 });
  const b = $("#s5-bpm");
  b.textContent = haveBpm() ? fmt(s.bpm) : "--";
  b.className = "big mono" + (!haveBpm() ? " none" : s.confident ? "" : " low");
  $("#s5-f").textContent = s.spectrum?.peak ? `f_peak = ${fmt(s.spectrum.peak / 60, 3)} Hz` : "";
}

/* ================================================================== what's next: liveness */
function renderLiveness() {
  const s = state, L = s.liveness, pill = $("#live-verdict");
  if (!s.running) { setPill(pill, "START A MEASUREMENT", ""); $("#live-share").textContent = "--"; $("#live-dial").style.setProperty("--share", 0); return; }
  if (!L) { setPill(pill, "COLLECTING SIGNAL", "info"); return; }
  const v = { pulse: ["PULSE FOUND: LIVING FACE", "good"], none: ["NO PULSE: PHOTO OR SCREEN?", "warn"], checking: ["CHECKING", "info"] }[L.verdict];
  setPill(pill, v[0], v[1]);
  $("#live-share").textContent = pct(L.share);
  $("#live-dial").style.setProperty("--share", L.share);
  $("#live-dial").dataset.verdict = L.verdict;
}

/* ================================================================== what's next: heart rhythm */
let hrvEmptyFor = null;
function updateHrvRing() {
  const el = state.hrv_elapsed, need = state.hrv_needed || 120;
  $("#hrv-ring").setAttribute("stroke-dasharray", `${el == null ? 0 : Math.min(100, el / need * 100).toFixed(1)} 100`);
  $("#hrv-time").textContent = el == null ? "0:00" : `${Math.floor(el / 60)}:${String(Math.floor(el % 60)).padStart(2, "0")}`;
  $("#hrv-done").disabled = el == null || el < 30;
  $("#hrv-go").disabled = !state.running;
  setPill($("#hrv-state"), hrv && !hrv.error ? "ANALYSED" : el != null ? (el >= need ? "LF/HF READY" : "RECORDING") : state.running ? "READY" : "NO MEASUREMENT",
    hrv && !hrv.error ? "good" : el != null ? (el >= need ? "good" : "coral") : "");
  if (!hrv && hrvEmptyFor !== !!state.running) renderHrv();
}
$("#hrv-go").addEventListener("click", () => { hrv = null; renderHrv(); send({ cmd: "hrv_start" }); });
$("#hrv-done").addEventListener("click", () => send({ cmd: "hrv_finish" }));
function renderHrv() {
  const out = $("#hrv-out");
  hrvEmptyFor = hrv ? null : !!state.running;
  if (!hrv) { out.innerHTML = ""; return; }
  if (hrv.error) { out.innerHTML = `<div class="card"><p class="foot"></p></div>`; out.querySelector("p").textContent = hrv.error; return; }
  const f = (v, d = 0) => v == null ? "--" : (+v).toFixed(d);
  out.innerHTML = `
    <div class="bento">
    <article class="card span-12">
      <header class="card-h"><span class="label mono">HEART RHYTHM / ${f(hrv.seconds)} S / ${hrv.rr_ms.length + 1} BEATS</span><span class="pill small ${hrv.valid ? "good" : "warn"}">${hrv.valid ? "LF/HF VALID" : "UNDER 2 MIN"}</span></header>
      <div class="stat-grid six">
        <div class="stat"><span class="label mono">MEAN HR</span><b>${f(hrv.mean_hr)}<small>BPM</small></b></div>
        <div class="stat"><span class="label mono">SDNN</span><b>${f(hrv.sdnn)}<small>MS</small></b></div>
        <div class="stat"><span class="label mono">RMSSD</span><b>${f(hrv.rmssd)}<small>MS</small></b></div>
        <div class="stat"><span class="label mono">LF/HF</span><b>${hrv.valid ? f(hrv.lf_hf, 2) : "--"}</b></div>
        <div class="stat"><span class="label mono">BREATHING</span><b>${hrv.valid && hrv.resp_bpm ? f(hrv.resp_bpm) : "--"}<small>/MIN</small></b></div>
        <div class="stat"><span class="label mono">PACED</span><b>${hrvPaced ? "6<small>/MIN</small>" : "NO"}</b></div>
      </div>
      <p class="indicator"></p>
      ${hrv.valid ? "" : `<p class="foot">Under two minutes: beat statistics only. LF/HF and breathing rate are withheld.</p>`}
    </article>
    <article class="card span-7 chart-card"><header class="card-h"><span class="label mono">BEAT-TO-BEAT HEART RATE</span><span class="mono muted">60 000 / GAP BETWEEN BEATS (MS)</span></header>
      <canvas class="chart" id="c-tach" style="--h:170px" aria-label="Heart rate computed from each gap between beats, over time"></canvas>
      <p class="foot">The rate rises when breathing in and falls when breathing out (respiratory sinus arrhythmia). With paced breathing the wave should follow the 10 s circle.</p></article>
    <article class="card span-5 chart-card fourier"><header class="card-h"><span class="label mono">SECOND FFT / LF AND HF</span></header>
      ${hrv.psd_f ? `<canvas class="chart" id="c-psd" style="--h:170px" aria-label="Spectrum of the beat intervals with LF and HF bands"></canvas>` : `<p class="foot">Needs a longer recording.</p>`}
      <p class="foot">HF (0.15 to 0.4 Hz) follows breathing. LF (0.04 to 0.15 Hz) follows blood-pressure control. 6 breaths a minute is 0.1 Hz, inside LF.</p></article>
    </div>`;
  out.querySelector(".indicator").textContent = hrv.indicator;
  drawHrvCharts();
}
function drawHrvCharts() {
  if (!hrv || !hrv.rr_ms) return;
  const t = $("#c-tach");
  if (t && hrv.rr_t && hrv.rr_t.length > 1) {
    const f = fit(t);
    if (f) {
      const { ctx, w, h } = f, xs = hrv.rr_t, ys = hrv.rr_ms.map(v => 60000 / v), pad = 14;
      let lo = Math.min(...ys), hi = Math.max(...ys); if (hi - lo < 4) { lo -= 2; hi += 2; }
      const X = v => (v - xs[0]) / (xs[xs.length - 1] - xs[0]) * (w - 40) + 36, Y = v => h - pad - (v - lo) / (hi - lo) * (h - 2 * pad);
      ctx.strokeStyle = css("--grid"); ctx.fillStyle = css("--ink-3"); ctx.font = "10px 'IBM Plex Mono', monospace"; ctx.textAlign = "right";
      [lo, (lo + hi) / 2, hi].forEach(v => { const y = Math.round(Y(v)) + .5; ctx.beginPath(); ctx.moveTo(36, y); ctx.lineTo(w, y); ctx.stroke(); ctx.fillText(Math.round(v), 30, y + 3); });
      ctx.strokeStyle = css("--coral"); ctx.lineWidth = 1.6; ctx.beginPath();
      xs.forEach((x, i) => i ? ctx.lineTo(X(x), Y(ys[i])) : ctx.moveTo(X(x), Y(ys[i]))); ctx.stroke();
      ctx.fillStyle = css("--coral"); xs.forEach((x, i) => { ctx.beginPath(); ctx.arc(X(x), Y(ys[i]), 1.8, 0, 7); ctx.fill(); });
    }
  }
  const c = $("#c-psd"); if (!c || !hrv.psd_f) return;
  const fc = fit(c); if (!fc) return;
  const { ctx, w, h } = fc, fmax = 0.5, pmax = Math.max(...hrv.psd_p) || 1, pad = 18;
  const x = v => v / fmax * w;
  const band = (a, b, col, lab) => { ctx.fillStyle = col; ctx.fillRect(x(a), 4, x(b) - x(a), h - pad - 4); ctx.fillStyle = css("--ink-2"); ctx.font = "10px 'IBM Plex Mono', monospace"; ctx.textAlign = "left"; ctx.fillText(lab, x(a) + 4, 16); };
  band(0.04, 0.15, css("--violet-soft"), "LF"); band(0.15, 0.40, css("--coral-soft"), "HF");
  ctx.strokeStyle = css("--violet"); ctx.lineWidth = 1.6; ctx.beginPath();
  hrv.psd_f.forEach((v, i) => { const py = h - pad - hrv.psd_p[i] / pmax * (h - pad - 22); i ? ctx.lineTo(x(v), py) : ctx.moveTo(x(v), py); });
  ctx.stroke();
  ctx.fillStyle = css("--ink-3"); ctx.textAlign = "center";
  [0.1, 0.2, 0.3, 0.4].forEach(v => ctx.fillText(`${v} HZ`, x(v), h - 4));
}

/* ================================================================== what's next: guided breathing */
let hrvPaced = false, paceTimer = null;
function setPacing(on) {
  hrvPaced = on;
  const b = $("#pace-btn");
  b.setAttribute("aria-pressed", String(on));
  b.querySelector("span").textContent = on ? "Stop pacing" : "Start pacing";
  setPill($("#pace-state"), on ? "BREATHE WITH THE CIRCLE" : "OFF", on ? "coral" : "");
  $("#pacer").classList.toggle("on", on);
  clearInterval(paceTimer);
  if (!on) { $("#pace-text").textContent = "6 / MIN"; $("#pace-circle").style.setProperty("--s", "0.55"); return; }
  const t0 = performance.now();
  paceTimer = setInterval(() => {
    const ph = ((performance.now() - t0) / 1000) % 10, inhale = ph < 5;
    $("#pace-text").textContent = `${inhale ? "IN" : "OUT"} ${Math.ceil(inhale ? 5 - ph : 10 - ph)}`;
    $("#pace-circle").style.setProperty("--s", (inhale ? 0.55 + 0.45 * (ph / 5) : 1 - 0.45 * ((ph - 5) / 5)).toFixed(3));
  }, 100);
}
$("#pace-btn").addEventListener("click", () => setPacing(!hrvPaced));

/* ================================================================== what's next: applications */
const USES = [
  ["done", "i-video", "Telehealth check-in", "Pulse during a video call, no device at home.", "HEART RATE"],
  ["done", "i-gauge", "Stress and relaxation", "Variability falls under stress and rises with rest.", "HRV"],
  ["done", "i-wind", "Breathing coach", "Shows paced breathing working, beat by beat.", "BEAT TIMING"],
  ["focus", "i-face", "Real face check", "Spot photos, masks and deepfakes: no blood, no pulse.", "PULSE PRESENCE"],
  ["pend", "i-car", "Driver fatigue", "A dashboard camera watching for drowsiness.", "HR + HRV"],
  ["pend", "i-baby", "Newborn care", "Monitoring without sensors on fragile skin.", "HR + BREATHING"],
  ["pend", "i-activity", "Fitness recovery", "How fast the heart settles after exercise.", "BEAT TIMING"],
  ["pend", "i-moon", "Sleep and elder care", "Overnight vitals with no wearable.", "HR + BREATHING"],
  ["pend", "i-pulse", "Rhythm screening", "Irregular beats as an early hint, for clinicians.", "BEAT TIMING"],
];
function renderUses() {
  const box = $("#uses");
  if (box.children.length) return;
  const tag = { done: ["lead", "IN THIS APP"], focus: ["ft", "PROTOTYPE"], pend: ["", "FUTURE"] };
  box.innerHTML = USES.map(([st, icon, title, line, sig]) => `
    <div class="use ${st}">
      <div class="use-top"><span class="use-icon"><svg><use href="#${icon}"/></svg></span><span class="tag ${tag[st][0]}">${tag[st][1]}</span></div>
      <h4>${title}</h4><p>${line}</p><span class="mono sig">${sig}</span>
    </div>`).join("");
}

/* ================================================================== floating camera (picture in picture) */
// Screens that already show the camera do not need the floating copy.
const HAS_CAMERA = new Set(["measure", "collect"]);
let pipClosed = false, pipWasRunning = false;
const pip = $("#pip"), pipImg = $("#pip-img");
function pipPlace(x, y) {
  const r = pip.getBoundingClientRect(), m = 12;
  const bottomBar = window.innerWidth <= 760 ? 76 : 0; // keep clear of the phone navigation bar
  x = Math.min(Math.max(m, x), window.innerWidth - r.width - m);
  y = Math.min(Math.max(m, y), window.innerHeight - r.height - m - bottomBar);
  pip.style.left = `${x}px`; pip.style.top = `${y}px`; pip.style.right = "auto"; pip.style.bottom = "auto";
  return [x, y];
}
function renderPip() {
  const s = state, running = !!s.running;
  if (running && !pipWasRunning) pipClosed = false; // a new session brings it back
  pipWasRunning = running;
  const show = running && !HAS_CAMERA.has(view) && !pipClosed;
  if (show && pip.hidden) {
    pip.hidden = false;
    pipImg.src = `/video.mjpg?pip=${Date.now()}`;
    let saved = null;
    try { saved = JSON.parse(localStorage.getItem("pip-pos") || "null"); } catch { /* storage unavailable */ }
    requestAnimationFrame(() => {
      const r = pip.getBoundingClientRect();
      pipPlace(saved ? saved[0] : window.innerWidth - r.width - 20, saved ? saved[1] : window.innerHeight - r.height - (window.innerWidth <= 760 ? 88 : 20));
    });
  } else if (!show && !pip.hidden) {
    pip.hidden = true;
    pipImg.removeAttribute("src"); // stop the stream while hidden
  }
  $("#pip-show").hidden = !(running && pipClosed && !HAS_CAMERA.has(view));
  if (show) {
    $("#pip-label").textContent = s.source === "sim" ? "SIMULATED" : "WEBCAM";
    $("#pip-bpm").textContent = haveBpm() ? `${fmt(s.bpm)} BPM${s.confident ? "" : "?"}` : "--";
    $("#pip-bpm").classList.toggle("low", haveBpm() && !s.confident);
  }
}
$("#pip-close").addEventListener("click", e => { e.stopPropagation(); pipClosed = true; renderPip(); });
$("#pip-show").addEventListener("click", () => { pipClosed = false; renderPip(); });
(() => {
  let drag = null;
  const bar = $("#pip-bar");
  bar.addEventListener("pointerdown", e => {
    if (e.target.closest("button")) return;
    const r = pip.getBoundingClientRect();
    drag = { dx: e.clientX - r.left, dy: e.clientY - r.top };
    try { bar.setPointerCapture(e.pointerId); } catch { /* capture unavailable: move still tracks the bar */ }
    pip.classList.add("dragging");
  });
  bar.addEventListener("pointermove", e => { if (drag) pipPlace(e.clientX - drag.dx, e.clientY - drag.dy); });
  const end = () => {
    if (!drag) return;
    drag = null;
    pip.classList.remove("dragging");
    const r = pip.getBoundingClientRect();
    try { localStorage.setItem("pip-pos", JSON.stringify([r.left, r.top])); } catch { /* storage unavailable */ }
  };
  bar.addEventListener("pointerup", end);
  bar.addEventListener("pointercancel", end);
  window.addEventListener("resize", () => { if (!pip.hidden) { const r = pip.getBoundingClientRect(); pipPlace(r.left, r.top); } });
})();

/* ================================================================== how it works: the slide deck */
const slides = $$("#stage .slide");
let slideAt = Math.min(slides.length - 1, Math.max(0, +(localGet("deck-slide") || 0)));
function showSlide(i) {
  slideAt = Math.min(slides.length - 1, Math.max(0, i));
  localSet("deck-slide", String(slideAt));
  slides.forEach((s, k) => {
    const on = k === slideAt;
    if (on && !s.classList.contains("on")) { s.classList.remove("on"); void s.offsetWidth; } // restart the drawing
    s.classList.toggle("on", on);
    s.setAttribute("aria-hidden", String(!on));
  });
  $$("#deck-dots button").forEach((b, k) => b.setAttribute("aria-current", k === slideAt ? "step" : "false"));
  $("#deck-count").textContent = `${slideAt + 1} / ${slides.length}`;
  $("#deck-prev").disabled = slideAt === 0;
  $("#deck-next").disabled = slideAt === slides.length - 1;
}
$("#deck-dots").innerHTML = slides.map((s, k) => `<li><button type="button" aria-label="Slide ${k + 1}: ${esc0(s.getAttribute("aria-label"))}"></button></li>`).join("");
function esc0(s) { return String(s || "").replace(/"/g, "&quot;"); }
$$("#deck-dots button").forEach((b, k) => b.addEventListener("click", () => showSlide(k)));
$("#deck-prev").addEventListener("click", () => showSlide(slideAt - 1));
$("#deck-next").addEventListener("click", () => showSlide(slideAt + 1));
function toggleFull() {
  const d = $("#deck");
  if (document.fullscreenElement) document.exitFullscreen();
  else if (d.requestFullscreen) d.requestFullscreen().catch(() => {});
}
$("#deck-full").addEventListener("click", toggleFull);
document.addEventListener("fullscreenchange", () => {
  const full = document.fullscreenElement === $("#deck");
  $("#deck").classList.toggle("full", full);
  $("#deck-full span").textContent = full ? "Exit" : "Present";
});
// Keyboard and presentation clickers (they send arrows or Page Up / Page Down).
document.addEventListener("keydown", e => {
  if (view !== "signal" || e.altKey || e.ctrlKey || e.metaKey) return;
  const el = e.target instanceof Element ? e.target : null; // clickers can send keys to the document itself
  if (el && el.closest("input, textarea, select, summary")) return;
  const next = ["ArrowRight", "PageDown"].includes(e.key) || (e.key === " " && !(el && el.closest("button")));
  const prev = ["ArrowLeft", "PageUp"].includes(e.key);
  if (next) { e.preventDefault(); showSlide(slideAt + 1); }
  else if (prev) { e.preventDefault(); showSlide(slideAt - 1); }
  else if (e.key === "Home") showSlide(0);
  else if (e.key === "End") showSlide(slides.length - 1);
  else if (e.key === "f" || e.key === "F") toggleFull();
});
function renderDeckTables() {
  const sim = hub?.simulated;
  const mot = $("#deck-motion"), skin = $("#deck-skin");
  if (!sim?.available) { if (mot) mot.innerHTML = ""; if (skin) skin.innerHTML = ""; return; }
  if (mot) {
    const pick = id => sim.scenarios.find(s => s.id === id);
    mot.innerHTML = [["still", "Still"], ["talking", "Talking"], ["restless", "Restless"]].map(([id, name]) => {
      const s = pick(id); if (!s) return "";
      return `<div class="ev"><b>${name}</b><span class="mono">simulated</span><em class="mono">GREEN ${fmt(s.all.mae.green, 1)}  /  TRACE ${fmt(s.all.mae.trace, 1)} BPM error</em></div>`;
    }).join("");
  }
  if (skin) {
    const rows = (sim.breakdowns.find(b => b.title === "BY SKIN TYPE") || {}).rows || [];
    skin.innerHTML = `<div class="skin-row">${rows.map(r => `<div><span class="mono">${esc(r.label.replace("Type ", ""))}</span><b class="mono">${fmt(r.mae.trace, 1)}</b></div>`).join("")}</div>
      <em class="mono">TRACE ERROR IN BPM BY SKIN TYPE, SIMULATED VOLUNTEERS</em>`;
  }
}
function renderDeckLearned() {
  const box = $("#deck-learned");
  if (!box) return;
  const L = hub?.learned;
  if (!L?.available) { box.innerHTML = `<div class="ev"><b>Results</b><span class="mono">volunteers</span><em class="mono muted">COMING SOON</em></div>`; return; }
  const pick = k => L.rows.find(r => r.key === k);
  const line = (keys, name, ref) => {
    const rs = keys.map(pick).filter(Boolean);
    return `<div class="ev"><b>${name}</b><span class="mono">${ref}</span><em class="mono">${rs.map(r => `${esc(r.label.replace(" (neural)", "").replace(" (ceiling)", "").toUpperCase())} ${fmt(r.mae, 1)}`).join("  /  ")} BPM</em></div>`;
  };
  box.innerHTML = line(["pos", "trace"], "Classical", "POS is the baseline")
    + line(["factorizephys"], "Option 1", "deep network")
    + line(["ml", "oracle"], "Option 2", "learned chooser, ceiling")
    + `<em class="mono evidence-foot">MEAN ERROR VS SMARTWATCH, ${L.n_readings} READINGS, ${L.n_people} PEOPLE</em>`;
}
function renderDeckEvidence() {
  renderDeckTables();
  renderDeckLearned();
  const box = $("#deck-evidence");
  if (!box) return;
  const rows = [["simulated", "Simulated faces", "exact truth"], ["ubfc", "Public dataset", "clip-on sensor"], ["volunteers", "Our volunteers", "smartwatch"]];
  box.innerHTML = rows.map(([k, name, ref]) => {
    const s = hub?.[k];
    if (!s?.available) return `<div class="ev"><b>${name}</b><span class="mono">${ref}</span><em class="mono muted">COMING SOON</em></div>`;
    const m = s.overall.mae, best = ["green", "chrom", "pos"].reduce((a, x) => m[x] < m[a] ? x : a, "green");
    return `<div class="ev"><b>${name}</b><span class="mono">${ref}</span><em class="mono">TRACE ${fmt(m.trace, 1)} vs ${MNAME[best]} ${fmt(m[best], 1)} BPM, ${s.readings.toLocaleString()} readings</em></div>`;
  }).join("");
}
showSlide(slideAt);

/* ================================================================== landing */
// Decorative only: a stylised pulse line over the landing photo. No number is
// shown, so nothing here can be mistaken for a measurement.
(function landing() {
  const pts = [];
  for (let x = 0; x <= 400; x += 2) {
    const ph = (x % 100) / 100;
    const y = Math.exp(-((ph - 0.22) ** 2) / 0.004) + 0.35 * Math.exp(-((ph - 0.5) ** 2) / 0.01);
    pts.push(`${x},${(52 - y * 40).toFixed(1)}`);
  }
  $("#land-wave").setAttribute("d", "M" + pts.join(" L"));
})();

/* ================================================================== boot */
let resizeTimer = null;
window.addEventListener("resize", () => { clearTimeout(resizeTimer); resizeTimer = setTimeout(() => { moveIndicator(); renderAll(); drawHrvCharts(); }, 120); });
fetch("/static/lab/scenarios.json", { cache: "no-store" }).then(r => r.json()).then(d => { scenarios = d; renderAll(); }).catch(() => {});
go("measure"); connect(); renderHrv();
