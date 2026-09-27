"use strict";
/* TRACE Pulse: the live app.
   Displays what the Python pipeline produces; it never recomputes pipeline
   math. Live values arrive over /ws (app/engine.py). The evaluation numbers
   come from /static/lab/results.json (scripts/build_dashboard_data.py). */

const METHODS = ["green", "chrom", "pos"];
const MNAME = { green: "GREEN", chrom: "CHROM", pos: "POS" };
const TITLES = { measure: "Measure", methods: "Methods", signal: "How it works", hrv: "Heart rhythm", summary: "Summary" };
const ART_TAG = 0.25; // artifact share at a method's peak above which the card is tagged

const $ = s => document.querySelector(s);
const $$ = s => Array.from(document.querySelectorAll(s));
function localGet(k) { try { return localStorage.getItem(k); } catch { return null; } }
function localSet(k, v) { try { localStorage.setItem(k, v); } catch { /* storage unavailable */ } }

let view = "measure", state = {}, ws = null, simSource = null, results = null, hrv = null;
let lastT = null, lastReading = null;
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
  $$(".nav button").forEach(b => b.classList.toggle("active", b.dataset.view === v));
  $("#view-title").textContent = TITLES[v];
  $("#ctx-view").textContent = TITLES[v].toUpperCase();
  moveIndicator(); renderAll();
  window.scrollTo({ top: 0 });
}
$$(".nav button").forEach(b => b.addEventListener("click", () => go(b.dataset.view)));
$$("[data-goto]").forEach(c => {
  c.addEventListener("click", () => go(c.dataset.goto));
  c.addEventListener("keydown", e => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); go(c.dataset.goto); } });
});

/* ================================================================== server link */
function connect() {
  ws = new WebSocket(`ws://${location.host}/ws`);
  ws.onmessage = ev => {
    const msg = JSON.parse(ev.data);
    if (msg.type === "state") { state = msg.state || {}; onState(); }
    if (msg.type === "hrv") { hrv = msg.result; renderHrv(); }
  };
  ws.onclose = () => { setPill($("#pill-live"), "OFFLINE", "warn"); setTimeout(connect, 1500); };
}
function send(o) { if (ws && ws.readyState === 1) ws.send(JSON.stringify(o)); }

function startSource(motion) {
  const v = document.querySelector('input[name="source"]:checked').value;
  simSource = v.startsWith("sim") ? { fitzpatrick: v === "sim5" ? 5 : 2, motion: motion ?? 0.3 } : null;
  send(simSource ? { cmd: "start", source: "sim", options: simSource } : { cmd: "start", source: "webcam" });
  $$("img.feed").forEach(img => { img.src = `/video.mjpg?${Date.now()}`; });
  wHistory.length = 0;
}
$("#start").addEventListener("click", () => { startSource(); lastReading = null; hrv = null; renderHrv(); });
$("#stop").addEventListener("click", () => send({ cmd: "stop" }));
$("#more-motion").addEventListener("click", () => startSource(1.6));
$("#less-motion").addEventListener("click", () => startSource(0.2));
$("#new-session").addEventListener("click", () => {
  send({ cmd: "stop" }); lastReading = null; hrv = null; wHistory.length = 0;
  $$("img.feed").forEach(img => img.removeAttribute("src"));
  renderHrv(); go("measure");
});

/* ================================================================== live state */
function onState() {
  const s = state;
  if (s.running && s.t != null && s.t !== lastT) {
    lastT = s.t;
    if (s.weights) { wHistory.push({ t: s.t, w: { ...s.weights } }); while (wHistory.length && wHistory[0].t < s.t - 60) wHistory.shift(); }
    if (haveBpm()) lastReading = { bpm: s.bpm, quality: s.quality, p_correct: s.p_correct ?? null, confident: s.confident,
      weights: s.weights, methods: s.methods, truth: s.true_bpm || null, source: s.source, fitzpatrick: s.fitzpatrick || null,
      session_s: s.t, at: new Date().toISOString() };
  }
  if (s.error) setPill($("#pill-live"), "ERROR", "warn");
  else setPill($("#pill-live"), s.running ? "LIVE" : "IDLE", s.running ? "good" : "");
  const src = $("#pill-source");
  src.hidden = !s.running;
  if (s.running) {
    const sim = s.source === "sim";
    src.textContent = sim ? `SIMULATED / ${s.fitzpatrick === 5 ? "DARKER" : "LIGHTER"} SKIN` : "WEBCAM";
    src.className = "pill " + (sim ? "sim" : "info");
  }
  $("#pill-timer").hidden = !s.running;
  $("#pill-timer span").textContent = mmss(s.t);
  $("#stop").hidden = !s.running;
  // A page reload while the engine is running must reattach the preview.
  if (s.running) $$("img.feed").forEach(img => { if (!img.getAttribute("src")) img.src = `/video.mjpg?${Date.now()}`; });
  $$(".cam-empty").forEach(el => {
    el.hidden = !!s.running;
    el.textContent = s.error ? (s.error.includes("camera") ? "NO CAMERA FOUND. CHOOSE A SIMULATED VOLUNTEER." : s.error) : "STARTING";
  });
  renderAll();
}

function renderAll() {
  if (view === "measure") renderMeasure();
  if (view === "methods") { renderFusion(); drawHistory(); renderEval(); }
  if (view === "signal") renderSignal();
  if (view === "hrv") updateHrvRing();
  if (view === "summary") renderSummary();
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

  const b = $("#live-bpm");
  b.textContent = have ? fmt(s.bpm) : "--";
  b.className = "big mono" + (!have ? " none" : s.confident ? "" : " low");
  setPill($("#live-state"), !have ? "COLLECTING" : s.confident ? "STEADY" : "LOW CONFIDENCE", !have ? "info" : s.confident ? "good" : "warn");
  const ring = $("#ring-fg");
  ring.setAttribute("stroke-dasharray", `${(have && s.p_correct != null ? s.p_correct * 100 : 0).toFixed(1)} 100`);
  ring.classList.toggle("low", have && !s.confident);
  $("#live-p").textContent = have ? pct(s.p_correct) : `${fmt(Math.max(0, (s.needed_s || 8) - (s.buffered_s || 0)))} S TO GO`;
  $("#live-p").className = "mono " + (have ? (s.confident ? "good" : "warn") : "");
  $("#live-q").textContent = have ? fmt(s.quality, 2) : "--";
  $("#live-truth-wrap").hidden = !s.true_bpm;
  if (s.true_bpm) $("#live-truth").textContent = `${fmt(s.true_bpm, 1)} BPM`;

  const w = s.weights;
  $("#mini-weights").innerHTML = METHODS.map(m => wbar(MNAME[m], w ? w[m] : 0, 1, C[m], w ? pct(w[m]) : "--")).join("");
  $("#tm-src").textContent = s.source === "sim" ? "SIMULATED" : "WEBCAM";
  $("#tm-buf").textContent = `${fmt(s.buffered_s, 1)} S`;
  $("#tm-motion").textContent = s.motion_px != null ? `${fmt(s.motion_px, 1)} PX` : "--";
  drawTrace($("#c-pulse"), s.trace?.pulse, css("--coral"), { width: 1.8, glow: true, grid: true, head: true, sym: true });
  $("#pulse-best").textContent = s.trace?.best ? `FROM ${MNAME[s.trace.best]}, THE MOST TRUSTED METHOD` : "";
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
          <div class="ch-meta"><span class="w">WEIGHT <b data-r="w">--</b></span><span>QUALITY <b data-r="q">--</b></span><span class="ch-tags" data-r="tags"></span></div>
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
          <div><dt>MOST TRUSTED</dt><dd data-r="td">--</dd></div>
        </dl>
        <canvas data-r="fspec" aria-label="Fused spectrum"></canvas>
      </div>
    </div>
    <p class="fusion-note">Each method gives its own spectrum. TRACE scores every spectrum by how sharp its peak is, suppresses frequencies that a motion reference flags, and adds the three with those scores as weights. The weights are recomputed every half second.</p>`;
  host.dataset.built = "1";
}
function renderFusion() {
  const s = state, C = MCOL(), thr = s.params?.confidence ?? 0.24, truth = s.true_bpm;
  const host = $(".fusion-host");
  if (!host.dataset.built) buildFusion(host);
  const q = r => host.querySelector(`[data-r="${r}"]`);
  const w = s.weights || {}, dom = dominantOf(s.weights);
  setPill(q("state"), !s.running ? "START A MEASUREMENT" : !s.weights ? "COLLECTING" : s.confident ? "STEADY" : "LOW CONFIDENCE",
    !s.running ? "" : !s.weights ? "info" : s.confident ? "good" : "warn");
  METHODS.forEach(m => {
    const ch = host.querySelector(`.ch[data-m="${m}"]`), mm = s.methods?.[m];
    const wv = w[m] ?? 0;
    ch.style.setProperty("--w", s.weights ? wv : .3);
    ch.classList.toggle("dominant", m === dom);
    ch.querySelector(".ch-bar i").style.width = `${Math.round(wv * 100)}%`;
    ch.querySelector(".ch-bar").setAttribute("aria-valuenow", String(Math.round(wv * 100)));
    ch.querySelector('[data-r="bpm"]').textContent = mm ? fmt(mm.bpm, 1) : "--";
    ch.querySelector('[data-r="w"]').textContent = s.weights ? pct(wv) : "--";
    ch.querySelector('[data-r="q"]').textContent = mm ? fmt(mm.quality, 2) : "--";
    const tags = [];
    if (mm) {
      if (m === dom) tags.push(["lead", "MOST TRUSTED"]);
      if (mm.quality < thr) tags.push(["lowq", "WEAK SIGNAL"]);
      if ((mm.artifact || 0) > ART_TAG) tags.push(["art", "MOTION"]);
      if (truth && Math.abs(mm.bpm - truth) > 5) tags.push(["art", "WRONG"]);
    }
    ch.querySelector('[data-r="tags"]').innerHTML = tags.map(([c, t]) => `<span class="tag ${c}">${t}</span>`).join("");
    host.querySelectorAll(`[data-route="${m}"]`).forEach(p => { p.style.stroke = C[m]; p.style.strokeWidth = 1 + wv * 12; p.style.strokeOpacity = .15 + wv * .7; });
    host.querySelectorAll(`[data-dash="${m}"]`).forEach(p => { p.style.stroke = "#fff"; p.style.strokeWidth = 1.2; p.style.strokeOpacity = s.weights ? wv * .5 : 0; });
    drawTrace(ch.querySelector('[data-r="wave"]'), s.method_traces?.[m], C[m], { width: 1.1, pad: 3 });
    drawSpec(ch.querySelector('[data-r="spec"]'), s.spectrum?.f, s.method_spectra?.[m], C[m], { peak: mm ? mm.bpm : null, peakColor: C[m], width: 1.1 });
  });
  const tb = q("tbpm");
  tb.innerHTML = `${haveBpm() ? fmt(s.bpm, 1) : "--"}<small>BPM</small>`;
  tb.classList.toggle("low", haveBpm() && !s.confident);
  q("tp").textContent = haveBpm() ? pct(s.p_correct) : "--";
  q("td").textContent = dom ? `${MNAME[dom]} ${pct(w[dom])}` : "--";
  drawSpec(q("fspec"), s.spectrum?.f, s.spectrum?.p, css("--lime"), { peak: s.spectrum?.peak, width: 1.4 });
  $("#sim-motion").hidden = !(s.running && s.source === "sim");
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
  ctx.fillStyle = css("--ink-3"); ctx.textAlign = "left"; ctx.fillText("-60 S", 0, h - 2); ctx.textAlign = "right"; ctx.fillText("NOW", pw, h - 2);
}

function renderEval() {
  if (!results) return;
  const S = results.selection_all, C = MCOL(), mx = Math.max(S.mae.green, S.mae.chrom, S.mae.pos, S.mae.trace) * 1.05;
  $("#eval-bars").innerHTML =
    METHODS.map(m => wbar(MNAME[m], S.mae[m], mx, C[m], fmt(S.mae[m], 1))).join("") +
    wbar("TRACE", S.mae.trace, mx, css("--lime"), fmt(S.mae.trace, 1), "trace");
  $("#eval-foot").textContent = `Average error in BPM over ${S.windows.toLocaleString()} measurements from ${results.n_subjects} simulated volunteers. Lower is better.`;
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

/* ================================================================== heart rhythm */
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
  if (!hrv) {
    out.innerHTML = `<div class="empty-state wide"><div><svg><use href="#i-waves"/></svg><p></p></div></div>`;
    out.querySelector("p").textContent = state.running ? "Press Start recording, sit still for two minutes, then analyse." : "Start a measurement first. Heart rhythm uses the live signal.";
    return;
  }
  if (hrv.error) { out.innerHTML = `<div class="card wide"><p class="foot"></p></div>`; out.querySelector("p").textContent = hrv.error; return; }
  const f = (v, d = 0) => v == null ? "--" : (+v).toFixed(d);
  out.innerHTML = `
    <article class="card wide">
      <header class="card-h"><span class="label mono">BEAT STATISTICS / ${f(hrv.seconds)} S</span><span class="pill small ${hrv.valid ? "good" : "warn"}">${hrv.valid ? "LF/HF VALID" : "UNDER 2 MIN"}</span></header>
      <div class="stat-grid">
        <div class="stat"><span class="label mono">MEAN HR</span><b>${f(hrv.mean_hr)}<small>BPM</small></b></div>
        <div class="stat"><span class="label mono">SDNN</span><b>${f(hrv.sdnn)}<small>MS</small></b></div>
        <div class="stat"><span class="label mono">RMSSD</span><b>${f(hrv.rmssd)}<small>MS</small></b></div>
        <div class="stat"><span class="label mono">LF/HF</span><b>${hrv.valid ? f(hrv.lf_hf, 2) : "--"}</b></div>
        <div class="stat"><span class="label mono">BREATHING</span><b>${hrv.valid && hrv.resp_bpm ? f(hrv.resp_bpm) : "--"}<small>/MIN</small></b></div>
        <div class="stat"><span class="label mono">BEATS</span><b>${hrv.rr_ms.length + 1}</b></div>
      </div>
    </article>
    <article class="card chart-card"><header class="card-h"><span class="label mono">TIME BETWEEN BEATS / MS</span></header><canvas class="chart" id="c-tach" style="--h:150px" aria-label="Intervals between beats"></canvas></article>
    <article class="card chart-card fourier"><header class="card-h"><span class="label mono">SECOND FFT / LF AND HF</span></header>${hrv.psd_f ? `<canvas class="chart" id="c-psd" style="--h:150px" aria-label="Spectrum of the beat intervals with LF and HF bands"></canvas>` : `<p class="foot">Needs a longer recording.</p>`}</article>
    <article class="card wide"><p class="indicator"></p>${hrv.valid ? "" : `<p class="foot">Under two minutes: beat statistics only. LF/HF is withheld.</p>`}</article>`;
  out.querySelector(".indicator").textContent = hrv.indicator;
  drawHrvCharts();
}
function drawHrvCharts() {
  if (!hrv || !hrv.rr_ms) return;
  const t = $("#c-tach"); if (t) drawTrace(t, hrv.rr_ms, css("--coral"), { width: 1.5, grid: true, head: true });
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

/* ================================================================== summary */
function renderSummary() {
  const r = lastReading, C = MCOL();
  const b = $("#res-bpm");
  b.textContent = r ? fmt(r.bpm) : "--";
  b.className = "big mono" + (!r ? " none" : r.confident ? "" : " low");
  setPill($("#res-state"), !r ? "NO READING" : r.confident ? "STEADY" : "LOW CONFIDENCE", !r ? "" : r.confident ? "good" : "warn");
  const dom = r ? dominantOf(r.weights) : null;
  const stats = [["CONFIDENCE", r ? pct(r.p_correct) : "--"], ["MOST TRUSTED", dom ? `${MNAME[dom]} ${pct(r.weights[dom])}` : "--"]];
  if (r?.truth) stats.push(["TRUE RATE / ERROR", `${fmt(r.truth, 1)} / ${fmt(Math.abs(r.bpm - r.truth), 1)}`]);
  if (hrv && !hrv.error) stats.push(["SDNN / RMSSD", `${fmt(hrv.sdnn)} / ${fmt(hrv.rmssd)} MS`]);
  $("#res-stats").innerHTML = stats.map(([k, v]) => `<div><span class="label mono">${k}</span><b class="mono">${v}</b></div>`).join("");
  $("#res-weights").innerHTML = r?.weights ? METHODS.map(m => wbar(MNAME[m], r.weights[m], 1, C[m], pct(r.weights[m]))).join("") : `<p class="foot">No reading yet.</p>`;
  $("#res-methods").innerHTML = r?.methods ? METHODS.map(m => `<div><dt class="mono">${MNAME[m]}</dt><dd class="mono">${fmt(r.methods[m].bpm, 1)} BPM</dd></div>`).join("") +
    `<div><dt class="mono">TRACE</dt><dd class="mono good">${fmt(r.bpm, 1)} BPM</dd></div>` : `<div><dt class="mono">--</dt><dd class="mono">NO READING</dd></div>`;
  const notes = [];
  if (r?.source === "sim") notes.push("Simulated volunteer: the skin is rendered, so the true rate is known.");
  if (r && !r.confident) notes.push("The last reading was below the confidence threshold.");
  notes.push("An academic project, not a medical device. It does not diagnose anything.");
  $("#res-warns").innerHTML = notes.map(t => `<li><svg><use href="#i-alert"/></svg><span>${t}</span></li>`).join("");
}
$("#export").addEventListener("click", () => {
  const blob = new Blob([JSON.stringify({ reading: lastReading, heart_rhythm: hrv, weight_history: wHistory,
    fusion_params: state.params || null, note: "Academic project, not a medical diagnosis.", exported: new Date().toISOString() }, null, 2)],
    { type: "application/json" });
  const a = document.createElement("a"); a.href = URL.createObjectURL(blob); a.download = "trace-measurement.json"; a.click();
  setTimeout(() => URL.revokeObjectURL(a.href), 1000);
});

/* ================================================================== boot */
let resizeTimer = null;
window.addEventListener("resize", () => { clearTimeout(resizeTimer); resizeTimer = setTimeout(() => { moveIndicator(); renderAll(); drawHrvCharts(); }, 120); });
fetch("/static/lab/results.json", { cache: "no-store" }).then(r => r.json()).then(d => { results = d; renderAll(); }).catch(() => {});
go("measure"); connect(); renderHrv();
