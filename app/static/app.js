"use strict";
/* TRACE Research Console.
   Displays what the Python pipeline produces; it never recomputes pipeline
   math. Live values arrive over /ws (app/engine.py). Experiment evidence comes
   from /static/lab/results.json (scripts/build_dashboard_data.py) and the
   compression thumbnails from /api/lab (scripts/build_app_assets.py). */

/* ================================================================== text */
const T = {
  en: {
    views: { overview: "Research session", setup: "Instrument setup", live: "Live pulse", methods: "Method fusion",
             compression: "Compression lab", hrv: "Heart-rate variability", experiments: "Experiments", results: "Session results" },
    stages: ["INIT", "SETUP", "CAPTURE", "METHODS", "COMPRESSION", "HRV", "RESULTS"],
    next: { overview: "Begin session", overviewRunning: "Instrument setup", setup: "Begin capture", live: "Method fusion",
            methods: "Compression lab", compression: "HRV session", hrv: "View results", results: "New session", experiments: "Return to session" },
    "nav.overview": "Overview", "nav.live": "Live Pulse", "nav.methods": "Methods", "nav.compression": "Compression",
    "nav.hrv": "HRV", "nav.experiments": "Experiments", "nav.results": "Results", "nav.collapse": "Collapse",
    "nav.theme": "Theme", "nav.about": "Privacy", back: "Back",
    "about.title": "About this console",
    "about.p1": "Video is processed on this computer. The page receives only numbers and a small preview.",
    "about.p2": "No trained model is in the estimation path. Every number comes from a convolution or a Fourier transform.",
    "about.p3": "A research and wellness tool, not a medical device. It does not diagnose anything.",
    "about.close": "Close",
    "hero.idle": "Heart rate from the colour of a face, measured three ways and fused.",
    "src.sim2": "Simulated volunteer", "src.sim5": "Simulated volunteer", "src.cam": "Webcam",
    "fix.face": "Fit your whole face inside the frame.", "fix.light": "Face a window or lamp. Avoid bright light behind you.",
    "fix.still": "Rest your head. Small movements are fine.",
    "how.summary": "How this works",
    "how.p1": "The mean colour of the forehead and cheeks is sampled thirty times a second. Slow lighting drift is removed by convolution with a moving average, and a windowed-sinc FIR bandpass keeps 42 to 240 beats per minute.",
    "how.p2": "The Fourier transform measures how much of each candidate rhythm the signal holds. Green, CHROM and POS each produce a spectrum; TRACE weights them by spectral quality, suppresses frequencies a pulse-blind reference says are motion, and reads the heart rate from the fused peak.",
    "hrv.need": "LF/HF needs at least two minutes of steady video. Five is the clinical standard.",
    "hrv.start": "Start reading", "hrv.finish": "Finish and analyse",
    "res.export": "Export data", "res.new": "New session",
    fusionNote: "TRACE never commits to one method. In every 20 s window each method's spectrum is scored by its own quality, masked where a pulse-blind reference sees motion, and added with that weight. The heart rate is read from the sum.",
    status: {
      disconnected: "LOST CONTACT WITH THE LOCAL SERVER. IS app/server.py RUNNING?",
      camError: "NO CAMERA FOUND. CHOOSE A SIMULATED VOLUNTEER OR CONNECT A WEBCAM.",
      pick: "CHOOSE A SOURCE, THEN BEGIN THE SESSION",
      fix: "RESOLVE THE CHECKS MARKED IN AMBER TO CONTINUE", ready: "SESSION READY",
      collecting: s => `COLLECTING SIGNAL: ${s} S UNTIL FIRST READING`,
      low: "LOW CONFIDENCE: HOLD STILL AND KEEP THE FACE LIT", steady: "SIGNAL LOCKED",
      hrv: s => `RECORDING ${s}. KEEP STILL, BREATHE NORMALLY`, noSession: "NO ACTIVE SESSION",
    },
    evNone: "No events yet",
    tiers: "complete",
    hrvEmpty: "Start a reading. Results appear here when it is analysed.",
    hrvShort: "Under two minutes: heart rate and beat statistics only. LF/HF is withheld.",
    noThumbs: "Frame thumbnails were rendered for H.264 only.",
    noSessionHrv: "Start a session first. HRV uses the live signal.",
  },
  bn: {
    views: { overview: "গবেষণা সেশন", setup: "যন্ত্র প্রস্তুতি", live: "লাইভ নাড়ি", methods: "পদ্ধতির মিশ্রণ",
             compression: "Compression ল্যাব", hrv: "হৃৎছন্দের পরিবর্তনশীলতা", experiments: "পরীক্ষা", results: "সেশনের ফলাফল" },
    stages: ["INIT", "SETUP", "CAPTURE", "METHODS", "COMPRESSION", "HRV", "RESULTS"],
    next: { overview: "সেশন শুরু করুন", overviewRunning: "যন্ত্র প্রস্তুতি", setup: "রেকর্ড শুরু করুন", live: "পদ্ধতির মিশ্রণ",
            methods: "Compression ল্যাব", compression: "HRV সেশন", hrv: "ফলাফল দেখুন", results: "নতুন সেশন", experiments: "সেশনে ফিরুন" },
    "nav.overview": "সারসংক্ষেপ", "nav.live": "লাইভ নাড়ি", "nav.methods": "পদ্ধতি", "nav.compression": "Compression",
    "nav.hrv": "HRV", "nav.experiments": "পরীক্ষা", "nav.results": "ফলাফল", "nav.collapse": "ছোট করুন",
    "nav.theme": "থিম", "nav.about": "গোপনীয়তা", back: "পেছনে",
    "about.title": "এই কনসোল সম্পর্কে",
    "about.p1": "ভিডিও এই কম্পিউটারেই প্রক্রিয়া হয়। পেজটি শুধু সংখ্যা আর একটি ছোট প্রিভিউ পায়।",
    "about.p2": "মাপার পথে কোনো trained model নেই। প্রতিটি সংখ্যা আসে convolution বা Fourier transform থেকে।",
    "about.p3": "এটি গবেষণা ও সুস্থতার টুল, চিকিৎসা যন্ত্র নয়। এটি কোনো রোগ নির্ণয় করে না।",
    "about.close": "বন্ধ করুন",
    "hero.idle": "মুখের রঙ থেকে হার্ট রেট, তিনভাবে মাপা এবং মেশানো।",
    "src.sim2": "সিমুলেটেড স্বেচ্ছাসেবী", "src.sim5": "সিমুলেটেড স্বেচ্ছাসেবী", "src.cam": "Webcam",
    "fix.face": "পুরো মুখ ফ্রেমের মধ্যে রাখুন।", "fix.light": "জানালা বা বাতির দিকে মুখ করুন। পেছনে উজ্জ্বল আলো রাখবেন না।",
    "fix.still": "মাথা স্থির রাখুন। একটু নড়াচড়া চলবে।",
    "how.summary": "কীভাবে কাজ করে",
    "how.p1": "প্রতি সেকেন্ডে ত্রিশবার কপাল ও গালের গড় রঙ মাপা হয়। moving average দিয়ে convolution করে ধীর আলোর পরিবর্তন সরানো হয়, আর একটি FIR bandpass শুধু মিনিটে ৪২ থেকে ২৪০ স্পন্দন রাখে।",
    "how.p2": "Fourier transform দেখায় সংকেতে প্রতিটি সম্ভাব্য ছন্দ কতটা আছে। Green, CHROM ও POS প্রত্যেকে একটি spectrum দেয়; TRACE সেগুলোকে গুণমান অনুযায়ী ওজন দেয়, নড়াচড়ার frequency চাপা দেয়, এবং মেশানো চূড়া থেকে হার্ট রেট পড়ে।",
    "hrv.need": "LF/HF-এর জন্য অন্তত দুই মিনিট স্থির ভিডিও লাগে। ক্লিনিক্যাল মান পাঁচ মিনিট।",
    "hrv.start": "রিডিং শুরু করুন", "hrv.finish": "শেষ করে বিশ্লেষণ করুন",
    "res.export": "ডেটা সংরক্ষণ", "res.new": "নতুন সেশন",
    fusionNote: "TRACE কখনো একটি পদ্ধতিতে আটকে থাকে না। প্রতিটি ২০ সেকেন্ডের window-এ প্রতিটি পদ্ধতির spectrum তার নিজের গুণমান দিয়ে মাপা হয়, নড়াচড়ার জায়গায় চাপা দেওয়া হয়, এবং সেই ওজনে যোগ করা হয়। হার্ট রেট পড়া হয় যোগফল থেকে।",
    evNone: "এখনো কোনো ঘটনা নেই",
    hrvEmpty: "রিডিং শুরু করুন। বিশ্লেষণের পরে ফলাফল এখানে আসবে।",
    hrvShort: "দুই মিনিটের কম: শুধু হার্ট রেট ও স্পন্দনের পরিসংখ্যান। LF/HF দেখানো হয়নি।",
    noThumbs: "ফ্রেমের ছবি শুধু H.264-এর জন্য তৈরি।",
    noSessionHrv: "আগে একটি সেশন শুরু করুন। HRV লাইভ সংকেত ব্যবহার করে।",
  },
};

/* Research tiers, from CLAUDE.md section 2 and 13 (measured values only). */
const TIERS = [
  { id: "T0", name: "Mathematics", st: "done", checks: "12/12", d: "Synthetic pulses with known answers verify detrending, the FIR bandpass, the FFT and the sub-harmonic defence.", m: "72.07 BPM through 4x drift at 0 dB SNR. Convolution theorem agrees to 4.3e-16." },
  { id: "T1", name: "Ground truth", st: "done", checks: "8/8", d: "Dataset loaders, reference heart rate from contact PPG, face-video simulator.", m: "Reference HR within 1.26 BPM from 48 to 124 BPM." },
  { id: "T2", name: "Face tracking", st: "done", checks: "6/6", d: "Haar initialisation, phase-correlation tracking, forehead and cheek skin traces.", m: "Tracking error at most 0.13 px. Still-video green MAE 0.08 to 0.11 BPM." },
  { id: "T3", name: "Green / CHROM / POS", st: "done", checks: "7/7", d: "Three classical extraction methods plus an ICA baseline.", m: "Simulated MAE I-III / IV-VI: POS 8.7 / 18.8, CHROM 10.5 / 24.7 BPM." },
  { id: "T4", name: "TRACE fusion", st: "focus", checks: "8/8", d: "Quality-weighted spectral fusion with a pulse-blind artifact mask. Current focus: proving the dynamic selection.", m: "Held-out MAE: TRACE v2 9.75, POS 11.81, POS + mask 7.26 BPM." },
  { id: "T5", name: "Compression harness", st: "done", checks: "8/8", d: "H.264, H.265 and VP9 at five bitrates with a bit-exact lossless control.", m: "FFV1 control bit-identical. Achieved bitrate 0.89x to 1.09x of target." },
  { id: "T6", name: "Neural baselines", st: "done", checks: "9/9", d: "PhysNet and FactorizePhys, pretrained, inference only, outside the pipeline.", m: "Clean light-skin video: PhysNet 0.75, FactorizePhys 0.85 BPM." },
  { id: "T7", name: "Grid and statistics", st: "done", checks: "pilot", d: "Every subject x condition x method, mixed-model interaction test.", m: "36 subjects x 23 conditions x 11 methods, 63,072 rows (simulated)." },
  { id: "T9", name: "HRV / LF-HF", st: "done", checks: "11/11", d: "Beat timing, RR cleaning, SDNN, RMSSD, and a second FFT for LF/HF.", m: "Clean video: SDNN MAE 0.68 ms, RMSSD 2.38 ms. Fragile with motion." },
  { id: "T10", name: "Live console", st: "done", checks: "live", d: "This console: the same pipeline, the same frozen parameters, running on a live source.", m: "Replay: 77.2 BPM vs true 77.0 with green down-weighted to 0.09." },
  { id: "R1", name: "Real data (UBFC)", st: "pend", checks: "pending", d: "Run every acceptance script and the grid on UBFC-rPPG.", m: "Needs the 73 GB dataset on another drive." },
  { id: "T8", name: "Own recordings", st: "pend", checks: "pending", d: "Recorded participants with a pulse oximeter for darker skin types.", m: "Needs participants and approval." },
];

const METHODS = ["green", "chrom", "pos"];
const MNAME = { green: "GREEN", chrom: "CHROM", pos: "POS" };
const STAGES = ["overview", "setup", "live", "methods", "compression", "hrv", "results"];
const ART_TAG = 0.25; // artifact share at a method's peak above which the card is tagged

const $ = s => document.querySelector(s);
const $$ = s => Array.from(document.querySelectorAll(s));
function localGet(k) { try { return localStorage.getItem(k); } catch { return null; } }
function localSet(k, v) { try { localStorage.setItem(k, v); } catch { /* storage unavailable */ } }

let lang = localGet("lang") || "en";
const L = () => ({ ...T.en, ...T[lang], status: { ...T.en.status, ...(T[lang].status || {}) } });
let view = "overview", lastStage = "overview", maxStage = 0;
let state = {}, prev = {}, ws = null, simSource = null, readySince = null;
let results = null, lab = null, hrv = null;
let codec = "h264", rateIdx = 0, labVisited = false, xCodec = "h264", tierOpen = "T4";
const wHistory = [];    // {t, w: {green, chrom, pos}}
const events = [];      // {t, kind, text, cls}
let readings = [];
let session = freshSession();

function freshSession() {
  return { started: null, captured: false, tracked: false, extracted: false, fused: false, locked: false,
           ticks: 0, confidentTicks: 0, shifts: 0, dominant: null, pendingDom: null, artifactOn: false, complete: false, lastT: null };
}

/* ================================================================== helpers */
const fmt = (v, d = 0) => (v == null || !isFinite(v)) ? "--" : (+v).toFixed(d);
const pct = v => (v == null || !isFinite(v)) ? "--" : `${Math.round(v * 100)}%`;
function mmss(s) { s = Math.max(0, Math.floor(s || 0)); return `${String(Math.floor(s / 60)).padStart(2, "0")}:${String(s % 60).padStart(2, "0")}`; }
function css(name) { return getComputedStyle(document.documentElement).getPropertyValue(name).trim(); }
const MCOL = () => ({ green: css("--m-green"), chrom: css("--m-chrom"), pos: css("--m-pos") });
function dominantOf(w) { if (!w) return null; let best = null; for (const k of METHODS) if (w[k] != null && (best == null || w[k] > w[best])) best = k; return best; }
function setPill(el, text, cls) { if (!el) return; el.className = el.className.replace(/\b(good|warn|info|coral)\b/g, "").trim() + (cls ? " " + cls : ""); const s = el.querySelector("span:last-child"); if (s && el.querySelector(".dot")) s.textContent = text; else el.textContent = text; }
function haveBpm() { return typeof state.bpm === "number"; }

/* ================================================================== language, theme, rail */
function applyLang() {
  document.documentElement.lang = lang;
  const D = L();
  $$("[data-i18n]").forEach(el => { const v = D[el.dataset.i18n]; if (typeof v === "string") el.textContent = v; });
  $("#lang-label").textContent = lang === "en" ? "বাংলা" : "English";
  renderStages(); renderView(); renderAll(true);
}
$("#lang").addEventListener("click", () => { lang = lang === "en" ? "bn" : "en"; localSet("lang", lang); applyLang(); });

function applyTheme(t) { document.documentElement.dataset.theme = t === "light" ? "light" : "dark"; }
applyTheme(localGet("theme"));
$("#theme").addEventListener("click", () => {
  const nxt = document.documentElement.dataset.theme === "light" ? "dark" : "light";
  applyTheme(nxt); localSet("theme", nxt); renderAll(true);
});

if (localGet("rail") === "open") document.body.classList.add("rail-open");
$("#expand").addEventListener("click", () => {
  const open = document.body.classList.toggle("rail-open");
  localSet("rail", open ? "open" : "closed");
  $("#expand").setAttribute("aria-label", open ? "Collapse navigation" : "Expand navigation");
  setTimeout(() => { moveIndicator(); renderAll(); }, 320);
});

const about = $("#about");
function toggleAbout(open) { about.hidden = !open; $("#about-btn").setAttribute("aria-expanded", String(open)); if (open) $("#about-close").focus(); }
$("#about-btn").addEventListener("click", () => toggleAbout(about.hidden));
$("#about-close").addEventListener("click", () => toggleAbout(false));
document.addEventListener("keydown", e => { if (e.key === "Escape" && !about.hidden) toggleAbout(false); });

/* ================================================================== navigation */
function moveIndicator() {
  const b = $(`.nav button[data-view="${view}"]`) || $(`.nav button[data-view="${navFor(view)}"]`);
  const ind = $("#nav-indicator");
  if (!b) { ind.style.opacity = 0; return; }
  ind.style.opacity = 1; ind.style.transform = `translateY(${b.offsetTop}px)`;
}
function navFor(v) { return v === "setup" ? "live" : v; }

function go(v, opts = {}) {
  view = v;
  const si = STAGES.indexOf(v);
  // Only the guided flow (Next) advances completion; jumping via the rail does not.
  if (si >= 0) { lastStage = v; if (opts.flow) maxStage = Math.max(maxStage, si); }
  $$(".view").forEach(s => s.classList.toggle("active", s.dataset.view === v));
  $$(".nav button").forEach(b => b.classList.toggle("active", b.dataset.view === navFor(v)));
  if (v === "compression") labVisited = true;
  renderView(); renderStages(); moveIndicator(); renderAll(true);
  if (!opts.keepScroll) window.scrollTo({ top: 0 });
  $("#view-title").setAttribute("tabindex", "-1");
  if (opts.focus !== false) $("#view-title").focus({ preventScroll: true });
}
$$(".nav button").forEach(b => b.addEventListener("click", () => go(b.dataset.view)));
$$("[data-goto]").forEach(c => {
  c.addEventListener("click", () => go(c.dataset.goto));
  c.addEventListener("keydown", e => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); go(c.dataset.goto); } });
});

function renderView() {
  $("#view-title").textContent = L().views[view];
  $("#ctx-view").textContent = view.toUpperCase();
  renderActions();
}

function renderStages() {
  const ol = $("#stages");
  ol.innerHTML = "";
  const cur = STAGES.indexOf(view);
  L().stages.forEach((name, i) => {
    const li = document.createElement("li");
    // Completed = every stage before the furthest one reached; current = where we are.
    li.className = i === cur ? "current" : i < maxStage || (i === maxStage && cur > maxStage) ? "done" : "";
    const b = document.createElement("button");
    b.type = "button"; b.disabled = i > maxStage;
    b.innerHTML = `<span class="n">${String(i + 1).padStart(2, "0")}</span><span class="lbl"></span>`;
    b.querySelector(".lbl").textContent = name;
    if (i === cur) b.setAttribute("aria-current", "step");
    b.addEventListener("click", () => go(STAGES[i]));
    li.appendChild(b); ol.appendChild(li);
  });
}

function canAdvance() {
  if (view === "setup") return !!(readySince && performance.now() - readySince > 1500);
  return true;
}
function renderActions() {
  const N = L().next;
  const label = view === "overview" && state.running ? N.overviewRunning : N[view];
  $("#next-label").textContent = label;
  $("#next").disabled = !canAdvance();
  $("#back").hidden = view === "overview";
}
$("#next").addEventListener("click", () => {
  const F = { flow: true };
  switch (view) {
    case "overview": if (!state.running) startSource(); go("setup", F); break;
    case "setup": go("live", F); break;
    case "live": snapshotReading(); go("methods", F); break;
    case "methods": snapshotReading(); go("compression", F); break;
    case "compression": go("hrv", F); break;
    case "hrv": go("results", F); break;
    case "results": newSession(); break;
    default: go(lastStage);
  }
});
$("#back").addEventListener("click", () => {
  const i = STAGES.indexOf(view);
  go(i > 0 ? STAGES[i - 1] : lastStage);
});
document.addEventListener("keydown", e => {
  if (e.target.matches("input, textarea, select") || e.altKey || e.ctrlKey || e.metaKey) return;
  if (e.key === "ArrowRight" && !$("#next").disabled) $("#next").click();
  if (e.key === "ArrowLeft" && !$("#back").hidden) $("#back").click();
});

/* ================================================================== server link */
function connect() {
  ws = new WebSocket(`ws://${location.host}/ws`);
  ws.onmessage = ev => {
    const msg = JSON.parse(ev.data);
    if (msg.type === "state") { prev = state; state = msg.state || {}; onState(); }
    if (msg.type === "hrv") { hrv = msg.result; renderHrv(); }
  };
  ws.onclose = () => { $("#status").textContent = L().status.disconnected; setTimeout(connect, 1500); };
}
function send(o) { if (ws && ws.readyState === 1) ws.send(JSON.stringify(o)); }

function startSource(motion) {
  const v = document.querySelector('input[name="source"]:checked').value;
  simSource = v.startsWith("sim") ? { fitzpatrick: v === "sim5" ? 5 : 2, motion: motion ?? 0.3 } : null;
  send(simSource ? { cmd: "start", source: "sim", options: simSource } : { cmd: "start", source: "webcam" });
  $$("img.feed").forEach(img => { img.src = `/video.mjpg?${Date.now()}`; });
  wHistory.length = 0; events.length = 0; session = freshSession(); session.started = Date.now();
  renderEvents();
}
$("#more-motion").addEventListener("click", () => { startSource(1.6); logEvent("SOURCE", "Volunteer set to restless", "info"); });
$("#less-motion").addEventListener("click", () => { startSource(0.2); logEvent("SOURCE", "Volunteer set to calm", "info"); });

function newSession() {
  send({ cmd: "stop" });
  readings = []; hrv = null; maxStage = 0; lastStage = "overview"; labVisited = false;
  wHistory.length = 0; events.length = 0; session = freshSession();
  $$("img.feed").forEach(img => img.removeAttribute("src"));
  renderEvents(); renderHrv(); go("overview");
}

/* ================================================================== live state */
function onState() {
  const s = state;
  const fresh = s.t != null && s.t !== session.lastT;
  if (fresh && s.running) { session.lastT = s.t; trackSession(); }

  // context pills
  if (s.error) setPill($("#pill-live"), "ERROR", "warn");
  else setPill($("#pill-live"), s.running ? "LIVE" : "IDLE", s.running ? "good" : "");
  const src = $("#pill-source");
  src.hidden = !s.running;
  if (s.running) {
    const sim = s.source === "sim";
    src.textContent = sim ? `SIMULATED PILOT / TYPE ${s.fitzpatrick === 5 ? "V" : "II"}` : "REAL RECORDING / WEBCAM";
    src.className = "pill " + (sim ? "sim" : "info");
  }
  $("#pill-timer").hidden = !s.running;
  $("#pill-timer span").textContent = mmss(s.t);

  // setup gate
  const checks = s.checks || {};
  const allOk = s.running && checks.face && checks.light && checks.still;
  if (allOk && !readySince) readySince = performance.now();
  if (!allOk) readySince = null;

  // A page reload while the engine is running must reattach the preview.
  if (s.running) $$("img.feed").forEach(img => { if (!img.getAttribute("src")) img.src = `/video.mjpg?${Date.now()}`; });
  $$(".cam-empty").forEach(el => {
    el.hidden = !!s.running;
    el.textContent = s.error ? (s.error.includes("camera") ? L().status.camError : s.error) : "NO SOURCE";
  });

  renderStatus();
  renderActions();
  renderAll();
}

function trackSession() {
  const s = state;
  session.captured = true;
  if (s.checks && s.checks.face) session.tracked = true;
  if ((s.buffered_s || 0) > 0) session.extracted = session.extracted || (s.buffered_s >= (s.needed_s || 8));
  if (s.weights) session.fused = true;
  if (haveBpm()) { session.ticks++; if (s.confident) session.confidentTicks++; }
  if (s.weights) wHistory.push({ t: s.t, w: { ...s.weights } });
  while (wHistory.length && wHistory[0].t < s.t - 60) wHistory.shift();

  // status events, all derived from values the engine reported
  if (haveBpm() && s.confident && !session.locked) { session.locked = true; logEvent("SIGNAL LOCKED", `TRACE ${fmt(s.bpm, 1)} BPM, P ${pct(s.p_correct)}`, "good"); }
  if (haveBpm() && !s.confident && session.locked) { session.locked = false; logEvent("LOW CONFIDENCE", `quality ${fmt(s.quality, 2)} below ${fmt(s.params?.confidence, 2)}`, "warn"); }
  const dom = dominantOf(s.weights);
  if (dom) {
    if (!session.dominant) session.dominant = dom;
    else if (dom !== session.dominant) {
      if (session.pendingDom === dom) {
        logEvent("METHOD SHIFT", `${MNAME[session.dominant]} to ${MNAME[dom]} (${pct(s.weights[dom])})`, "info");
        session.dominant = dom; session.pendingDom = null; session.shifts++;
      } else session.pendingDom = dom;
    } else session.pendingDom = null;
  }
  const art = METHODS.filter(k => (s.methods?.[k]?.artifact || 0) > ART_TAG);
  if (art.length && !session.artifactOn) logEvent("ARTIFACT", `${art.map(k => MNAME[k]).join(", ")} peak shares ${art.map(k => fmt(s.methods[k].artifact, 2)).join(", ")}`, "warn");
  session.artifactOn = art.length > 0;
  if (haveBpm() && s.confident && !session.complete) { session.complete = true; logEvent("PIPELINE COMPLETE", "All nine stages produced output", "good"); }
}

function logEvent(kind, text, cls) {
  events.unshift({ t: state.t || 0, kind, text, cls });
  if (events.length > 30) events.pop();
  renderEvents();
}
function renderEvents() {
  const ol = $("#events");
  if (!events.length) { ol.innerHTML = `<li class="muted mono">${L().evNone}</li>`; return; }
  ol.innerHTML = "";
  events.slice(0, 12).forEach(e => {
    const li = document.createElement("li");
    li.innerHTML = `<span class="t">${mmss(e.t)}</span><span class="pill small ${e.cls || ""}"></span><span class="d"></span>`;
    li.children[1].textContent = e.kind; li.children[2].textContent = e.text;
    ol.appendChild(li);
  });
}

function renderStatus() {
  const s = state, S = L().status;
  let msg = "";
  if (s.error) msg = s.error.includes("camera") ? S.camError : s.error.toUpperCase();
  else if (view === "overview" && !s.running) msg = S.pick;
  else if (view === "setup") {
    const ok = s.running && s.checks?.face && s.checks?.light && s.checks?.still;
    msg = !s.running ? S.noSession : ok ? S.ready : S.fix;
  } else if (["live", "methods", "overview"].includes(view) && s.running) {
    if (!haveBpm()) msg = S.collecting(Math.max(0, Math.ceil((s.needed_s || 8) - (s.buffered_s || 0))));
    else msg = s.confident ? S.steady : S.low;
  } else if (view === "hrv" && s.hrv_elapsed != null && !hrv) msg = S.hrv(mmss(s.hrv_elapsed));
  $("#status").textContent = msg;
}

function snapshotReading() {
  if (!haveBpm()) return;
  readings.push({ bpm: state.bpm, quality: state.quality, p_correct: state.p_correct ?? null, confident: state.confident,
    weights: state.weights, methods: state.methods, truth: state.true_bpm || null, source: state.source,
    fitzpatrick: state.fitzpatrick || null, session_s: state.t, at: new Date().toISOString() });
}

/* ================================================================== render dispatch */
// Static views (compression, experiments) depend only on these inputs, not on
// the live stream, so they are rebuilt when a key changes rather than at 4 Hz.
const built = {};
function staticKey(v) {
  return [v, lang, document.documentElement.dataset.theme, codec, rateIdx, xCodec, tierOpen, !!results, !!lab,
          document.body.classList.contains("rail-open"), window.innerWidth].join("|");
}
function renderAll(force) {
  renderHero(); renderPipeline(); renderFusion();
  if (view === "setup") renderSetup();
  if (view === "live") renderLive();
  if (view === "methods") drawHistory();
  for (const v of ["compression", "overview", "experiments"]) {
    if (view !== v) continue;
    const k = staticKey(v);
    if (!force && built[v] === k) continue;
    built[v] = k;
    if (v === "experiments") renderExperiments();
    else { renderLab(); if (v === "overview") { renderEvidence(); renderTierStrip(); } }
  }
  if (view === "hrv") updateHrvRing();
  if (view === "results") renderResults();
}

/* ================================================================== charts (display only) */
function fit(cv) {
  const dpr = window.devicePixelRatio || 1, w = cv.clientWidth, h = cv.clientHeight;
  if (!w || !h) return null;
  if (cv.width !== Math.round(w * dpr) || cv.height !== Math.round(h * dpr)) { cv.width = Math.round(w * dpr); cv.height = Math.round(h * dpr); }
  const ctx = cv.getContext("2d"); ctx.setTransform(dpr, 0, 0, dpr, 0, 0); ctx.clearRect(0, 0, w, h);
  return { ctx, w, h };
}
function drawTrace(cv, ys, color, o = {}) {
  const f = fit(cv); if (!f) return;
  const { ctx, w, h } = f, pad = o.pad ?? 8;
  if (o.grid) {
    ctx.strokeStyle = css("--grid"); ctx.lineWidth = 1;
    for (let i = 1; i < 4; i++) { const y = Math.round(h * i / 4) + .5; ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(w, y); ctx.stroke(); }
  }
  if (!ys || ys.length < 2) return;
  let lo = Infinity, hi = -Infinity;
  for (const v of ys) { if (v < lo) lo = v; if (v > hi) hi = v; }
  if (o.sym) { const m = Math.max(Math.abs(lo), Math.abs(hi)) || 1; lo = -m; hi = m; }
  if (hi - lo < 1e-9) { hi += 1; lo -= 1; }
  const X = i => i / (ys.length - 1) * w, Y = v => h - pad - (v - lo) / (hi - lo) * (h - 2 * pad);
  ctx.beginPath(); ys.forEach((v, i) => i ? ctx.lineTo(X(i), Y(v)) : ctx.moveTo(X(i), Y(v)));
  if (o.fill) {
    const g = ctx.createLinearGradient(0, 0, 0, h); g.addColorStop(0, o.fill); g.addColorStop(1, "transparent");
    ctx.save(); ctx.lineTo(w, h); ctx.lineTo(0, h); ctx.closePath(); ctx.fillStyle = g; ctx.fill(); ctx.restore();
    ctx.beginPath(); ys.forEach((v, i) => i ? ctx.lineTo(X(i), Y(v)) : ctx.moveTo(X(i), Y(v)));
  }
  ctx.strokeStyle = color; ctx.lineWidth = o.width || 1.5; ctx.lineJoin = "round";
  if (o.glow) { ctx.shadowColor = color; ctx.shadowBlur = 8; }
  ctx.stroke(); ctx.shadowBlur = 0;
  if (o.head) { const x = X(ys.length - 1), y = Y(ys[ys.length - 1]); ctx.fillStyle = color; ctx.beginPath(); ctx.arc(x - 2, y, 2.5, 0, 7); ctx.fill(); }
}
function drawSpec(cv, f, p, color, o = {}) {
  const c = fit(cv); if (!c || !f || !p || f.length < 2) return;
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

/* ================================================================== overview hero */
function renderHero() {
  const s = state, live = !!s.running;
  $("#hero-idle").hidden = live; $("#hero-live").hidden = !live;
  const st = $("#hero-state");
  if (!live) { setPill(st, s.error ? "ERROR" : "IDLE", s.error ? "warn" : ""); }
  else if (!haveBpm()) setPill(st, "COLLECTING", "info");
  else setPill(st, s.confident ? "SIGNAL LOCKED" : "LOW CONFIDENCE", s.confident ? "good" : "warn");
  if (live) {
    const b = $("#hero-bpm");
    b.textContent = haveBpm() ? fmt(s.bpm) : "--";
    b.className = "big mono" + (!haveBpm() ? " none" : s.confident ? "" : " low");
    $("#hero-conf").textContent = haveBpm() ? `${pct(s.p_correct)}` : "--";
    const d = dominantOf(s.weights);
    $("#hero-dom").textContent = d ? `${MNAME[d]} ${pct(s.weights[d])}` : "--";
    $("#hero-signal").textContent = !haveBpm() ? `BUFFER ${fmt(s.buffered_s)} S` : s.confident ? "STABLE" : "LOW CONFIDENCE";
    $("#hero-truth-wrap").hidden = !s.true_bpm;
    if (s.true_bpm) $("#hero-truth").textContent = `${fmt(s.true_bpm, 1)} BPM` + (haveBpm() ? ` / ERR ${fmt(Math.abs(s.bpm - s.true_bpm), 1)}` : "");
  }
  if (view === "overview") drawTrace($("#c-hero"), s.trace?.pulse, css("--coral"), { width: 1.6, fill: css("--coral") + "30", sym: true, pad: 16 });
}

/* ================================================================== pipeline progression */
const PIPE = [["01", "Capture"], ["02", "Track"], ["03", "Extract RGB"], ["04", "Detrend"], ["05", "Filter"], ["06", "Spectrum"], ["07", "Method quality"], ["08", "TRACE fusion"], ["09", "Estimate"]];
let pipeLast = [];
function pipeStates() {
  const s = state;
  if (!s.running) return PIPE.map(() => ["locked", "LOCKED"]);
  const buf = (s.buffered_s || 0), need = s.needed_s || 8, have = haveBpm();
  const face = !!s.checks?.face;
  const out = [];
  out.push(["complete", "COMPLETE"]);
  out.push(face ? ["complete", "COMPLETE"] : ["low", "NO FACE"]);
  out.push(buf > 0 ? ["complete", "COMPLETE"] : face ? ["processing", "PROCESSING"] : ["locked", "LOCKED"]);
  const bufState = have ? ["complete", "COMPLETE"] : buf > 0 ? ["processing", `${Math.min(99, Math.round(buf / need * 100))}%`] : ["locked", "LOCKED"];
  out.push(bufState, bufState);
  out.push(s.spectrum ? ["complete", "COMPLETE"] : ["locked", "LOCKED"]);
  out.push(s.methods ? ["complete", "COMPLETE"] : ["locked", "LOCKED"]);
  out.push(s.weights ? ["complete", "COMPLETE"] : ["locked", "LOCKED"]);
  out.push(!have ? ["locked", "LOCKED"] : s.confident ? ["complete", "COMPLETE"] : ["low", "LOW SIGNAL"]);
  return out;
}
function renderPipeline() {
  const ol = $("#pipeline"), sts = pipeStates();
  if (!ol.children.length) ol.innerHTML = PIPE.map(([n, l]) => `<li><span class="pn">${n}</span><span class="pl">${l}</span><span class="ps"></span></li>`).join("");
  sts.forEach(([cls, txt], i) => {
    const li = ol.children[i];
    if (pipeLast[i] !== "complete" && cls === "complete") { li.classList.remove("sweep"); void li.offsetWidth; li.classList.add("sweep"); }
    li.classList.remove("complete", "processing", "low", "locked"); li.classList.add(cls);
    li.querySelector(".ps").textContent = txt;
  });
  pipeLast = sts.map(x => x[0]);
  const done = sts.filter(x => x[0] === "complete").length;
  setPill($("#pipe-state"), done === 9 ? "PIPELINE COMPLETE" : state.running ? `${done}/9` : "LOCKED", done === 9 ? "good" : state.running ? "info" : "");
}

/* ================================================================== TRACE fusion module */
function buildFusion(host) {
  const mode = host.dataset.fusion;
  host.innerHTML = `
    <div class="fusion-h">
      <span class="label mono">${mode === "full" ? "TRACE FUSION / METHOD DUEL" : "TRACE FUSION"}</span>
      <span class="legend mono" data-r="params"></span>
      <span class="pill small" data-r="state">WAITING</span>
    </div>
    <div class="fusion" data-mode="${mode}">
      <div class="channels">${METHODS.map(m => `
        <div class="ch" data-m="${m}">
          <span class="ch-name"><i></i>${MNAME[m]}</span>
          <span class="ch-bpm mono"><span data-r="bpm">--</span><small>BPM</small></span>
          <div class="ch-bar" role="meter" aria-label="${MNAME[m]} weight" aria-valuemin="0" aria-valuemax="100"><i></i></div>
          <div class="ch-meta"><span class="w">WEIGHT <b data-r="w">--</b></span><span>QUALITY <b data-r="q">--</b></span><span>ARTIFACT <b data-r="a">--</b></span><span class="ch-tags" data-r="tags"></span></div>
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
          <div><dt>P(WITHIN 5 BPM)</dt><dd data-r="tp">--</dd></div>
          <div><dt>FUSED QUALITY</dt><dd data-r="tq">--</dd></div>
          <div><dt>TOP CONTRIBUTION</dt><dd data-r="td">--</dd></div>
        </dl>
        <canvas data-r="fspec" aria-label="Fused spectrum"></canvas>
      </div>
    </div>
    ${mode === "full" ? `<p class="fusion-note">${L().fusionNote}</p>` : ""}`;
  host.dataset.built = lang;
}
function renderFusion() {
  const s = state, C = MCOL(), thr = s.params?.confidence ?? 0.24;
  const truth = s.true_bpm;
  $$(".fusion-host").forEach(host => {
    if (host.dataset.built !== lang) buildFusion(host);
    const q = r => host.querySelector(`[data-r="${r}"]`);
    q("params").textContent = s.params ? `GAMMA ${fmt(s.params.gamma, 1)} / MASK K ${fmt(s.params.mask_k, 0)} / GATE ${fmt(thr, 2)}` : "";
    const w = s.weights || {}, dom = dominantOf(s.weights);
    setPill(q("state"), !s.running ? "WAITING" : !s.weights ? "COLLECTING" : s.confident ? "SIGNAL LOCKED" : "LOW CONFIDENCE",
      !s.running ? "" : !s.weights ? "info" : s.confident ? "good" : "warn");
    const visible = host.offsetParent !== null;
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
      ch.querySelector('[data-r="a"]').textContent = mm && mm.artifact != null ? fmt(mm.artifact, 2) : "--";
      const tags = [];
      if (mm) {
        if (m === dom) tags.push(["lead", "TOP WEIGHT"]);
        if (mm.quality < thr) tags.push(["lowq", "LOW QUALITY"]);
        if ((mm.artifact || 0) > ART_TAG) tags.push(["art", "ARTIFACT"]);
        if (truth && Math.abs(mm.bpm - truth) > 5) tags.push(["art", "OFF TRUTH"]);
      }
      ch.querySelector('[data-r="tags"]').innerHTML = tags.map(([c, t]) => `<span class="tag ${c}">${t}</span>`).join("");
      // routes: stroke width and opacity follow the live weight
      host.querySelectorAll(`[data-route="${m}"]`).forEach(p => { p.style.stroke = C[m]; p.style.strokeWidth = 1 + wv * 12; p.style.strokeOpacity = .15 + wv * .7; });
      host.querySelectorAll(`[data-dash="${m}"]`).forEach(p => { p.style.stroke = "#fff"; p.style.strokeWidth = 1.2; p.style.strokeOpacity = s.weights ? wv * .5 : 0; });
      if (visible && host.dataset.fusion === "full") {
        drawTrace(ch.querySelector('[data-r="wave"]'), s.method_traces?.[m], C[m], { width: 1.1, pad: 3 });
        drawSpec(ch.querySelector('[data-r="spec"]'), s.spectrum?.f, s.method_spectra?.[m], C[m], { peak: mm ? mm.bpm : null, peakColor: C[m], width: 1.1 });
      }
    });
    const tb = q("tbpm");
    tb.innerHTML = `${haveBpm() ? fmt(s.bpm, 1) : "--"}<small>BPM</small>`;
    tb.classList.toggle("low", haveBpm() && !s.confident);
    q("tp").textContent = haveBpm() ? pct(s.p_correct) : "--";
    q("tq").textContent = haveBpm() ? `${fmt(s.quality, 2)} / ${fmt(thr, 2)}` : "--";
    q("td").textContent = dom ? `${MNAME[dom]} ${pct(w[dom])}` : "--";
    if (visible && host.dataset.fusion === "full") drawSpec(q("fspec"), s.spectrum?.f, s.spectrum?.p, css("--lime"), { peak: s.spectrum?.peak, width: 1.4 });
  });
}

/* ================================================================== setup */
function renderSetup() {
  const s = state, checks = s.checks || {};
  const vals = { face: s.running ? (checks.face ? "LOCKED" : "SEARCHING") : "--", light: s.luminance != null ? `${fmt(s.luminance)} / 255` : "--", still: s.motion_px != null ? `${fmt(s.motion_px, 1)} PX` : "--" };
  $$("#checks li").forEach(li => {
    const k = li.dataset.check, ok = !!checks[k];
    li.classList.toggle("ok", !!s.running && ok); li.classList.toggle("bad", !!s.running && !ok);
    li.querySelector(".val").textContent = vals[k];
    li.querySelector(".st").textContent = !s.running ? "CHECKING" : ok ? "READY" : "ATTENTION";
    li.querySelector(".fix").hidden = !!s.running && ok;
  });
  const held = readySince ? Math.min(1, (performance.now() - readySince) / 1500) : 0;
  $("#ready-fill").style.width = `${Math.round(held * 100)}%`;
  const ready = held >= 1;
  setPill($("#ready-pill"), !s.running ? "CHECKING" : ready ? "SESSION READY" : readySince ? "HOLDING" : "NEEDS ATTENTION", !s.running ? "" : ready ? "good" : readySince ? "info" : "warn");
  $("#ready-text").textContent = !s.running ? "WAITING FOR SOURCE" : ready ? "SESSION READY: BEGIN CAPTURE" : readySince ? "ALL CHECKS PASS, HOLD FOR 1.5 S" : "ONE OR MORE CHECKS NEED ATTENTION";
}

/* ================================================================== live */
function renderLive() {
  const s = state, have = haveBpm();
  const b = $("#live-bpm");
  b.textContent = have ? fmt(s.bpm) : "--";
  b.className = "big mono" + (!have ? " none" : s.confident ? "" : " low");
  setPill($("#live-state"), !s.running ? "IDLE" : !have ? "COLLECTING" : s.confident ? "SIGNAL LOCKED" : "LOW CONFIDENCE", !s.running ? "" : !have ? "info" : s.confident ? "good" : "warn");
  const p = have && s.p_correct != null ? s.p_correct : 0;
  const ring = $("#ring-fg");
  ring.setAttribute("stroke-dasharray", `${(p * 100).toFixed(1)} 100`);
  ring.classList.toggle("low", have && !s.confident);
  $("#live-p").textContent = have ? pct(s.p_correct) : "--";
  $("#live-p").className = "mono " + (have ? (s.confident ? "good" : "warn") : "");
  $("#live-q").textContent = have ? `${fmt(s.quality, 3)} (GATE ${fmt(s.params?.confidence, 2)})` : "--";
  $("#live-buf").textContent = s.running ? `${fmt(s.buffered_s, 1)} S` : "--";
  $("#live-truth-wrap").hidden = !s.true_bpm;
  if (s.true_bpm) $("#live-truth").textContent = `${fmt(s.true_bpm, 1)} BPM`;
  $("#tm-face").textContent = s.running ? (s.checks?.face ? "LOCKED" : "SEARCHING") : "--";
  $("#tm-lum").textContent = s.luminance != null ? fmt(s.luminance) : "--";
  $("#tm-motion").textContent = s.motion_px != null ? `${fmt(s.motion_px, 2)} PX` : "--";
  $("#tm-src").textContent = s.running ? (s.source === "sim" ? "SIMULATED" : "WEBCAM") : "--";

  const on = { raw: (s.buffered_s || 0) > 0, detrend: !!s.trace, bandpass: !!s.trace, fft: !!s.spectrum, trace: !!s.weights, bpm: have };
  $$("#flow li").forEach(li => {
    const k = li.dataset.f;
    li.classList.toggle("on", !!on[k] && !(k === "bpm" && !s.confident));
    li.classList.toggle("lowsig", k === "bpm" && have && !s.confident);
  });
  drawTrace($("#c-raw"), s.trace?.raw, css("--ink-2"), { width: 1.2, grid: true });
  drawTrace($("#c-pulse"), s.trace?.pulse, css("--coral"), { width: 1.8, glow: true, grid: true, head: true, sym: true });
  $("#pulse-best").textContent = s.trace?.best ? `WAVEFORM FROM ${MNAME[s.trace.best]} (TOP WEIGHT)` : "--";
  drawSpec($("#c-spec"), s.spectrum?.f, s.spectrum?.p, css("--violet"), { axis: true, peak: s.spectrum?.peak, width: 1.6 });
  $("#spec-peak").textContent = s.spectrum ? `PEAK ${fmt(s.spectrum.peak, 1)} BPM` : "PEAK --";
}

/* ================================================================== contribution timeline */
function drawHistory() {
  const cv = $("#c-hist"), f = fit(cv); if (!f) return;
  const { ctx, w, h } = f, C = MCOL(), pad = 16;
  ctx.strokeStyle = css("--grid"); ctx.lineWidth = 1;
  [0, .25, .5, .75, 1].forEach(v => { const y = Math.round(pad + (1 - v) * (h - 2 * pad)) + .5; ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(w - 70, y); ctx.stroke(); });
  $("#hist-legend").innerHTML = METHODS.map(m => `<span><i style="background:${C[m]}"></i>${MNAME[m]}</span>`).join("");
  if (wHistory.length < 2) {
    ctx.fillStyle = css("--ink-3"); ctx.font = "11px 'IBM Plex Mono', monospace"; ctx.textAlign = "center";
    ctx.fillText(state.running ? "WAITING FOR FUSION WEIGHTS" : "NO ACTIVE SESSION", (w - 70) / 2, h / 2); return;
  }
  const t1 = wHistory[wHistory.length - 1].t, t0 = t1 - 60, pw = w - 70;
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
    ctx.fillText(`${MNAME[m]} ${pct(last.w[m])}`, pw + 8, Math.max(pad + 6, Math.min(h - pad, Y(mid) + 4)));
    base = top;
  });
  ctx.strokeStyle = css("--ink-3"); ctx.setLineDash([2, 4]);
  events.filter(e => e.kind === "METHOD SHIFT" && e.t >= t0).forEach(e => { ctx.beginPath(); ctx.moveTo(X(e.t) + .5, pad); ctx.lineTo(X(e.t) + .5, h - pad); ctx.stroke(); });
  ctx.setLineDash([]);
  ctx.fillStyle = css("--ink-3"); ctx.textAlign = "left"; ctx.fillText("-60 S", 0, h - 2); ctx.textAlign = "right"; ctx.fillText("NOW", pw, h - 2);
}

/* ================================================================== compression lab */
function rateLabel(r) { return r === "lossless" ? "LOSSLESS" : `${r} KBPS`; }
function codecLabel(c) { return { h264: "H.264", h265: "H.265", vp9: "VP9" }[c] || c.toUpperCase(); }
function buildCodecSeg(el, onPick, cur) {
  el.innerHTML = "";
  (results?.codecs || ["h264", "h265", "vp9"]).forEach(c => {
    const b = document.createElement("button"); b.type = "button"; b.setAttribute("role", "radio");
    b.textContent = codecLabel(c); b.setAttribute("aria-checked", String(c === cur()));
    b.addEventListener("click", () => { onPick(c); });
    el.appendChild(b);
  });
}
function meterHTML(label, v, dark) {
  const n = Math.max(0, Math.min(20, Math.round((v ?? 0) * 20)));
  return `<div class="meter ${dark ? "dark" : ""}"><div class="mh"><span>${label}</span><b>${v == null ? "--" : v.toFixed(2)}</b></div>
    <div class="cells">${Array.from({ length: 20 }, (_, i) => `<span class="${i < n ? "on" : ""}"></span>`).join("")}</div></div>`;
}
function renderLab() {
  if (!results) return;
  const rates = results.rates, r = rates[rateIdx];
  const cell = results.compression[codec]?.[r];
  // overview mini card
  $("#cm-cond").textContent = `${codecLabel(codec)} / ${rateLabel(r)}`;
  if (cell) {
    const tr = cell.methods.trace?.mae, po = cell.methods.pos?.mae;
    $("#cm-integrity").innerHTML = (cell.fidelity ? meterHTML("PULSE FIDELITY / TYPE II", cell.fidelity.II) + meterHTML("PULSE FIDELITY / TYPE VI", cell.fidelity.VI, true) : "") +
      `<div class="wb trace" style="--c:var(--lime)"><span class="n"><i></i>TRACE</span><span class="b"><i style="width:${Math.min(100, tr / 30 * 100)}%"></i></span><span class="v">${fmt(tr, 1)} BPM</span></div>
       <div class="wb" style="--c:var(--m-pos)"><span class="n"><i></i>POS</span><span class="b"><i style="width:${Math.min(100, po / 30 * 100)}%"></i></span><span class="v">${fmt(po, 1)} BPM</span></div>`;
  }
  if (view !== "compression") return;

  buildCodecSeg($("#codec-seg"), c => { codec = c; renderLab(); }, () => codec);
  const slider = $("#rate");
  slider.max = rates.length - 1; slider.value = rateIdx;
  slider.style.setProperty("--fill", `${rateIdx / (rates.length - 1) * 100}%`);
  slider.setAttribute("aria-valuetext", rateLabel(r));
  $("#rate-ticks").innerHTML = rates.map((k, i) => `<span class="${i === rateIdx ? "on" : ""}">${k === "lossless" ? "LOSSLESS" : k}</span>`).join("");
  $("#lab-n").textContent = `${results.n_subjects} SUBJECTS / ${codecLabel(codec)}`;
  drawLab();
  if (!cell) return;
  $("#lab-integrity").innerHTML = cell.fidelity ? meterHTML("LIGHTER SKIN / TYPE II", cell.fidelity.II) + meterHTML("DARKER SKIN / TYPE VI", cell.fidelity.VI, true) : `<p class="foot">No fidelity measurement for this condition.</p>`;
  const C = MCOL(), wt = cell.weights.all;
  $("#lab-weights").innerHTML = METHODS.map(m => `<div class="wb" style="--c:${C[m]}"><span class="n"><i></i>${MNAME[m]}</span><span class="b"><i style="width:${Math.round(wt[m] * 100)}%"></i></span><span class="v">${pct(wt[m])}</span></div>`).join("");
  const sel = cell.selection;
  $("#lab-sel").textContent = `TOP WEIGHT ON A BEST-OR-TIED METHOD IN ${pct(sel.dominant_is_best)} OF ${sel.windows} WINDOWS (ALWAYS POS: ${pct(sel.fixed_is_best.pos)})`;
  const rows = ["green", "chrom", "pos", "pos_mask", "trace", "physnet", "factorizephys"].filter(m => cell.methods[m]);
  const lows = rows.map(m => cell.methods[m].mae);
  const minMae = Math.min(...lows);
  const g = (m, k) => cell.methods[m].groups?.[k];
  $("#lab-table").innerHTML = `<thead><tr><th>METHOD</th><th>ALL</th><th>I-III</th><th>IV-VI</th><th>GAP</th><th>WITHIN 5</th></tr></thead><tbody>${rows.map(m => {
    const a = g(m, "I-III"), b = g(m, "IV-VI"), mae = cell.methods[m].mae;
    const ci = x => x ? `${fmt(x.mae, 1)} <small>${fmt(x.lo, 1)}-${fmt(x.hi, 1)}</small>` : "--";
    return `<tr class="${m === "trace" ? "trace" : ""}"><td>${results.labels[m].toUpperCase()}</td><td class="${mae === minMae ? "best" : ""}">${fmt(mae, 1)}</td><td>${ci(a)}</td><td>${ci(b)}</td><td>${a && b ? (b.mae - a.mae >= 0 ? "+" : "") + fmt(b.mae - a.mae, 1) : "--"}</td><td>${pct(cell.methods[m].within5)}</td></tr>`;
  }).join("")}</tbody>`;
  const th = codec === "h264" && lab?.thumbs?.[r];
  $("#thumbs").innerHTML = th ? ["II", "V"].map(t => th[t] ? `<figure><img src="${th[t]}" alt="Simulated face, type ${t}, ${rateLabel(r)}"><figcaption>TYPE ${t} / ${rateLabel(r)}</figcaption></figure>` : "").join("")
    : `<div class="none">${L().noThumbs}</div>`;
}
$("#rate").addEventListener("input", e => { rateIdx = +e.target.value; renderLab(); });

const LAB_LINES = [
  ["green", "--m-green", false], ["chrom", "--m-chrom", false], ["pos", "--m-pos", false],
  ["pos_mask", "--ink-3", true], ["physnet", "--ink-3", true], ["factorizephys", "--ink-3", true], ["trace", "--lime", false],
];
let labHover = null;
function drawLab() {
  const cv = $("#c-lab"), f = fit(cv); if (!f || !results) return;
  const { ctx, w, h } = f, rates = results.rates, data = results.compression[codec];
  const L0 = 34, R0 = 118, T0 = 12, B0 = 26, pw = w - L0 - R0, ph = h - T0 - B0;
  let ymax = 0;
  LAB_LINES.forEach(([m]) => rates.forEach(r => { const v = data[r]?.methods[m]?.mae; if (v > ymax) ymax = v; }));
  ymax = Math.ceil((ymax + 2) / 5) * 5;
  const X = i => L0 + i / (rates.length - 1) * pw, Y = v => T0 + (1 - v / ymax) * ph;
  ctx.font = "10px 'IBM Plex Mono', monospace"; ctx.fillStyle = css("--ink-3"); ctx.strokeStyle = css("--grid"); ctx.lineWidth = 1;
  for (let v = 0; v <= ymax; v += 5) { const y = Math.round(Y(v)) + .5; ctx.beginPath(); ctx.moveTo(L0, y); ctx.lineTo(L0 + pw, y); ctx.stroke(); ctx.textAlign = "right"; ctx.fillText(v, L0 - 8, y + 3); }
  ctx.textAlign = "center";
  rates.forEach((r, i) => { ctx.fillStyle = i === rateIdx ? css("--lime") : css("--ink-3"); ctx.fillText(r === "lossless" ? "LOSSLESS" : r, X(i), h - 8); });
  ctx.save(); ctx.translate(10, T0 + ph / 2); ctx.rotate(-Math.PI / 2); ctx.fillStyle = css("--ink-3"); ctx.fillText("MAE BPM", 0, 0); ctx.restore();
  ctx.strokeStyle = css("--lime"); ctx.globalAlpha = .35; ctx.beginPath(); ctx.moveTo(X(rateIdx) + .5, T0); ctx.lineTo(X(rateIdx) + .5, T0 + ph); ctx.stroke(); ctx.globalAlpha = 1;
  const labels = [];
  LAB_LINES.forEach(([m, col, dashed]) => {
    const pts = rates.map((r, i) => [X(i), data[r]?.methods[m]?.mae]).filter(p => p[1] != null);
    if (pts.length < 2) return;
    const c = css(col);
    ctx.strokeStyle = c; ctx.lineWidth = m === "trace" ? 2.2 : 1.3; ctx.setLineDash(dashed ? [4, 4] : []);
    if (m === "trace") { ctx.shadowColor = c; ctx.shadowBlur = 6; }
    ctx.beginPath(); pts.forEach(([x, v], i) => i ? ctx.lineTo(x, Y(v)) : ctx.moveTo(x, Y(v))); ctx.stroke();
    ctx.shadowBlur = 0; ctx.setLineDash([]);
    const sel = data[rates[rateIdx]]?.methods[m]?.mae;
    if (sel != null) { ctx.fillStyle = c; ctx.beginPath(); ctx.arc(X(rateIdx), Y(sel), m === "trace" ? 4 : 3, 0, 7); ctx.fill(); }
    const last = pts[pts.length - 1];
    labels.push({ y: Y(last[1]), text: results.labels[m].toUpperCase(), c });
  });
  labels.sort((a, b) => a.y - b.y);
  for (let i = 1; i < labels.length; i++) if (labels[i].y - labels[i - 1].y < 12) labels[i].y = labels[i - 1].y + 12;
  ctx.textAlign = "left"; ctx.font = "10px 'IBM Plex Mono', monospace";
  labels.forEach(l => { ctx.fillStyle = l.c; ctx.fillText(l.text, L0 + pw + 10, l.y + 3); });
  cv._geom = { X, rates, L0, pw };
}
$("#c-lab").addEventListener("mousemove", e => {
  const cv = e.currentTarget, g = cv._geom; if (!g || !results) return;
  const rect = cv.getBoundingClientRect(), x = e.clientX - rect.left;
  const i = Math.max(0, Math.min(g.rates.length - 1, Math.round((x - g.L0) / g.pw * (g.rates.length - 1))));
  const cell = results.compression[codec][g.rates[i]]; if (!cell) return;
  const tip = $("#lab-tip");
  tip.innerHTML = `<b>${codecLabel(codec)} / ${rateLabel(g.rates[i])}</b><br>` + LAB_LINES.filter(([m]) => cell.methods[m]).map(([m, col]) =>
    `<span style="color:${css(col)}">${results.labels[m].toUpperCase()}</span> ${fmt(cell.methods[m].mae, 1)}`).join("<br>");
  tip.hidden = false;
  const left = g.X(i) + 14; tip.style.left = `${Math.min(left, rect.width - tip.offsetWidth - 4)}px`; tip.style.top = "16px";
  labHover = i;
});
$("#c-lab").addEventListener("mouseleave", () => { $("#lab-tip").hidden = true; labHover = null; });
$("#c-lab").addEventListener("click", () => { if (labHover != null) { rateIdx = labHover; renderLab(); } });

/* ================================================================== experiments */
function wbar(name, v, max, col, text, cls = "") {
  return `<div class="wb ${cls}" style="--c:${col}"><span class="n"><i></i>${name}</span><span class="b"><i style="width:${Math.max(0, Math.min(100, v / max * 100))}%"></i></span><span class="v">${text}</span></div>`;
}
function renderEvidence() {
  if (!results?.held_out) return;
  const H = results.held_out, C = MCOL();
  const rows = [["GREEN", H.green, C.green], ["CHROM", H.chrom, C.chrom], ["POS", H.pos, C.pos], ["POS + MASK", H["POS + artifact mask (no fusion)"], css("--ink-3")], ["TRACE V2", H["TRACE v2 (gamma 1.0, k 4.0)"], css("--lime")]];
  $("#ev-bars").innerHTML = rows.map(([n, v, c]) => wbar(n, v, 25, c, `${fmt(v, 2)}`, n === "TRACE V2" ? "trace" : "")).join("");
  $("#ev-foot").textContent = "MAE BPM ON A COHORT NEVER USED FOR TUNING. LOWER IS BETTER.";
}
function renderTierStrip() {
  const el = $("#tier-strip");
  el.innerHTML = TIERS.map((t, i) => `${i ? `<span class="ln ${t.st === "done" && TIERS[i - 1].st === "done" ? "done" : ""}"></span>` : ""}<span class="tn ${t.st}" title="${t.id} ${t.name}"><i></i>${t.id}</span>`).join("");
  $("#prog-count").textContent = `${TIERS.filter(t => t.st !== "pend").length}/${TIERS.length} TIERS`;
}
function renderTree() {
  const el = $("#tree");
  el.innerHTML = "";
  TIERS.forEach(t => {
    const b = document.createElement("button");
    b.type = "button"; b.className = t.st; b.setAttribute("role", "listitem"); b.setAttribute("aria-pressed", String(t.id === tierOpen));
    b.innerHTML = `<span class="tid"><i></i>${t.id}</span><span class="tname"></span><span class="tst">${t.st === "done" ? "COMPLETE" : t.st === "focus" ? "FOCUS" : "NEEDS DATA"} / ${t.checks.toUpperCase()}</span>`;
    b.querySelector(".tname").textContent = t.name;
    b.addEventListener("click", () => { tierOpen = t.id; renderTree(); });
    el.appendChild(b);
  });
  const t = TIERS.find(x => x.id === tierOpen);
  $("#tier-detail").innerHTML = t ? `<div class="td"><h3>${t.id} ${t.name}</h3><p></p><span class="m"></span></div>` : "";
  if (t) { $("#tier-detail p").textContent = t.d; $("#tier-detail .m").textContent = t.m; }
}
function renderExperiments() {
  renderTree();
  if (!results) return;
  const S = results.selection_all, C = MCOL();
  const mx = Math.max(...Object.values(S.mae)) * 1.05;
  $("#x-mae").innerHTML =
    wbar("GREEN", S.mae.green, mx, C.green, `${fmt(S.mae.green, 2)}<small>${pct(S.within5.green)}</small>`) +
    wbar("CHROM", S.mae.chrom, mx, C.chrom, `${fmt(S.mae.chrom, 2)}<small>${pct(S.within5.chrom)}</small>`) +
    wbar("POS", S.mae.pos, mx, C.pos, `${fmt(S.mae.pos, 2)}<small>${pct(S.within5.pos)}</small>`) +
    wbar("TRACE", S.mae.trace, mx, css("--lime"), `${fmt(S.mae.trace, 2)}<small>${pct(S.within5.trace)}</small>`, "trace") +
    wbar("ORACLE", S.mae.oracle, mx, css("--ink-3"), `${fmt(S.mae.oracle, 2)}<small>${pct(S.within5.oracle)}</small>`, "dashed");
  $("#x-mae-foot").textContent = `MAE BPM (WITHIN 5 BPM) OVER ${S.windows.toLocaleString()} WINDOWS, ${results.n_subjects} SUBJECTS, EVERY CONDITION. ORACLE = WHICHEVER OF THE THREE WAS CLOSEST IN EACH WINDOW, A CEILING NO REAL SYSTEM CAN REACH. TRACE ALSO MASKS ARTIFACTS, SO IN SOME CONDITIONS IT BEATS THE ORACLE.`;
  $("#x-dom").innerHTML =
    wbar("TRACE TOP", S.dominant_is_best, 1, css("--lime"), pct(S.dominant_is_best), "trace") +
    METHODS.map(m => wbar(`ALWAYS ${MNAME[m]}`, S.fixed_is_best[m], 1, C[m], pct(S.fixed_is_best[m]))).join("");
  $("#x-dom-foot").textContent = "Share of windows where the chosen method was best or within 1 BPM of best. Ranking alone does not beat always trusting POS: TRACE gains by blending the three spectra and masking artifacts, not by picking one method.";
  const H = results.held_out;
  if (H) {
    const rows = [["GREEN", H.green, C.green], ["ICA", H.ica, css("--ink-3")], ["CHROM", H.chrom, C.chrom], ["POS", H.pos, C.pos],
      ["TRACE V1", H["TRACE v1 (gamma 4.0)"], css("--ink-3")], ["V2 EQUAL W", H["TRACE v2 equal weights"], css("--ink-3")],
      ["POS + MASK", H["POS + artifact mask (no fusion)"], css("--ink-2")], ["TRACE V2", H["TRACE v2 (gamma 1.0, k 4.0)"], css("--lime")]];
    $("#x-held").innerHTML = rows.map(([n, v, c]) => wbar(n, v, 25, c, fmt(v, 2), n === "TRACE V2" ? "trace" : "")).join("");
    $("#x-held-foot").textContent = `Tuned on seeds 1000+ and 2000+, tested once. POS with the artifact mask alone (${fmt(H["POS + artifact mask (no fusion)"], 2)}) beats full TRACE (${fmt(H["TRACE v2 (gamma 1.0, k 4.0)"], 2)}): the mask carries most of the gain. Confidence gate: ${fmt(H.confident_mae, 2)} BPM on the ${pct(H.coverage)} of windows it keeps, ${fmt(H.flagged_mae, 2)} on the ones it flags.`;
  }
  buildCodecSeg($("#x-codec"), c => { xCodec = c; renderExperiments(); }, () => xCodec);
  const data = results.compression[xCodec], cols = ["green", "chrom", "pos", "pos_mask", "trace"];
  $("#x-table").innerHTML = `<thead><tr><th>CONDITION</th>${cols.map(c => `<th>${results.labels[c].toUpperCase()}</th>`).join("")}<th>ORACLE</th><th>MEAN TRACE WEIGHTS G / C / P</th><th>TOP = BEST</th></tr></thead><tbody>${
    results.rates.filter(r => data[r]).map(r => {
      const cell = data[r], vals = cols.map(c => cell.methods[c]?.mae), best = Math.min(...vals.filter(v => v != null));
      const wt = cell.weights.all;
      return `<tr class="${r === results.rates[rateIdx] && xCodec === codec ? "sel" : ""}"><td>${codecLabel(xCodec)} / ${rateLabel(r)}</td>${vals.map((v, i) => `<td class="${v === best ? "best" : ""}">${fmt(v, 1)}</td>`).join("")}
        <td>${fmt(cell.selection.mae.oracle, 1)}</td>
        <td><span class="ministack">${METHODS.map(m => `<i style="width:${wt[m] * 100}%;background:${C[m]}"></i>`).join("")}</span> ${METHODS.map(m => fmt(wt[m] * 100)).join(" / ")}</td>
        <td>${pct(cell.selection.dominant_is_best)}</td></tr>`;
    }).join("")}</tbody>`;
}

/* ================================================================== HRV */
function updateHrvRing() {
  const el = state.hrv_elapsed;
  const need = state.hrv_needed || 120;
  $("#hrv-ring").setAttribute("stroke-dasharray", `${el == null ? 0 : Math.min(100, el / need * 100).toFixed(1)} 100`);
  $("#hrv-time").textContent = el == null ? "0:00" : `${Math.floor(el / 60)}:${String(Math.floor(el % 60)).padStart(2, "0")}`;
  $("#hrv-done").disabled = el == null || el < 30;
  $("#hrv-go").disabled = !state.running;
  setPill($("#hrv-state"), hrv && !hrv.error ? "ANALYSED" : el != null ? (el >= need ? "LF/HF READY" : "RECORDING") : state.running ? "READY" : "NO SESSION",
    hrv && !hrv.error ? "good" : el != null ? (el >= need ? "good" : "coral") : "");
  if (!hrv && hrvEmptyFor !== !!state.running) renderHrv();
}
$("#hrv-go").addEventListener("click", () => { hrv = null; renderHrv(); send({ cmd: "hrv_start" }); logEvent("HRV", "Heart-rhythm capture started", "info"); });
$("#hrv-done").addEventListener("click", () => send({ cmd: "hrv_finish" }));
let hrvEmptyFor = null;
function renderHrv() {
  const out = $("#hrv-out");
  hrvEmptyFor = hrv ? null : !!state.running;
  if (!hrv) {
    out.innerHTML = `<div class="empty-state wide"><div><svg><use href="#i-waves"/></svg><p></p></div></div>`;
    out.querySelector("p").textContent = state.running ? L().hrvEmpty : L().noSessionHrv; return;
  }
  if (hrv.error) { out.innerHTML = `<div class="card wide"><p class="foot"></p></div>`; out.querySelector("p").textContent = hrv.error; return; }
  const f = (v, d = 0) => v == null ? "--" : (+v).toFixed(d);
  out.innerHTML = `
    <article class="card wide">
      <header class="card-h"><span class="label mono">BEAT STATISTICS / ${f(hrv.seconds)} S / ${String(hrv.method).toUpperCase()} WAVEFORM</span><span class="pill small ${hrv.valid ? "good" : "warn"}">${hrv.valid ? "LF/HF VALID" : "UNDER 2 MIN"}</span></header>
      <div class="stat-grid">
        <div class="stat"><span class="label mono">MEAN HR</span><b>${f(hrv.mean_hr)}<small>BPM</small></b></div>
        <div class="stat"><span class="label mono">SDNN</span><b>${f(hrv.sdnn)}<small>MS</small></b></div>
        <div class="stat"><span class="label mono">RMSSD</span><b>${f(hrv.rmssd)}<small>MS</small></b></div>
        <div class="stat"><span class="label mono">LF/HF</span><b>${hrv.valid ? f(hrv.lf_hf, 2) : "--"}</b></div>
        <div class="stat"><span class="label mono">BREATHING</span><b>${hrv.valid && hrv.resp_bpm ? f(hrv.resp_bpm) : "--"}<small>/MIN</small></b></div>
        <div class="stat"><span class="label mono">BEATS USED</span><b>${hrv.rr_ms.length + 1}</b></div>
      </div>
    </article>
    <article class="card chart-card"><header class="card-h"><span class="label mono">RR TACHOGRAM / MS</span></header><canvas class="chart" id="c-tach" style="--h:150px" aria-label="Intervals between beats"></canvas></article>
    <article class="card chart-card fourier"><header class="card-h"><span class="label mono">SECOND FFT / LF AND HF BANDS</span></header>${hrv.psd_f ? `<canvas class="chart" id="c-psd" style="--h:150px" aria-label="Power spectrum of the RR series with LF and HF bands"></canvas>` : `<p class="foot">Spectrum needs a longer capture.</p>`}</article>
    <article class="card wide"><p class="indicator"></p>${hrv.valid ? "" : `<p class="foot">${L().hrvShort}</p>`}</article>`;
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

/* ================================================================== results */
function renderResults() {
  const last = readings[readings.length - 1] || (haveBpm() ? { bpm: state.bpm, quality: state.quality, p_correct: state.p_correct, confident: state.confident,
    weights: state.weights, methods: state.methods, truth: state.true_bpm, source: state.source, fitzpatrick: state.fitzpatrick, live: true } : null);
  const b = $("#res-bpm");
  b.textContent = last ? fmt(last.bpm) : "--";
  b.className = "big mono" + (!last ? " none" : last.confident ? "" : " low");
  setPill($("#res-state"), !last ? "NO READING" : last.confident ? "EXPERIMENT COMPLETE" : "LOW CONFIDENCE", !last ? "" : last.confident ? "good" : "warn");
  const dom = last ? dominantOf(last.weights) : null;
  const stats = [
    ["CONFIDENCE", last ? pct(last.p_correct) : "--"],
    ["FUSED QUALITY", last ? fmt(last.quality, 3) : "--"],
    ["DOMINANT", dom ? `${MNAME[dom]} ${pct(last.weights[dom])}` : "--"],
  ];
  if (last?.truth) stats.push(["TRUTH / ERROR", `${fmt(last.truth, 1)} / ${fmt(Math.abs(last.bpm - last.truth), 1)}`]);
  $("#res-stats").innerHTML = stats.map(([k, v]) => `<div><span class="label mono">${k}</span><b class="mono">${v}</b></div>`).join("");
  const C = MCOL();
  $("#res-weights").innerHTML = last?.weights ? METHODS.map(m => `<div class="wb" style="--c:${C[m]}"><span class="n"><i></i>${MNAME[m]}</span><span class="b"><i style="width:${Math.round(last.weights[m] * 100)}%"></i></span><span class="v">${pct(last.weights[m])}</span></div>`).join("") : `<p class="foot">No reading yet.</p>`;
  $("#res-methods").innerHTML = last?.methods ? METHODS.map(m => `<div><dt class="mono">${MNAME[m]}</dt><dd class="mono">${fmt(last.methods[m].bpm, 1)} BPM / Q ${fmt(last.methods[m].quality, 2)}</dd></div>`).join("") +
    `<div><dt class="mono">TRACE</dt><dd class="mono good">${fmt(last.bpm, 1)} BPM</dd></div>` : `<div><dt class="mono">--</dt><dd class="mono">NO READING</dd></div>`;
  const ctxRows = [
    ["SOURCE", last ? (last.source === "sim" ? `SIMULATED / TYPE ${last.fitzpatrick === 5 ? "V" : "II"}` : "WEBCAM / REAL RECORDING") : "--"],
    ["READINGS TAKEN", String(readings.length)],
    ["WINDOWS ANALYSED", String(session.ticks)],
    ["METHOD SHIFTS", String(session.shifts)],
    ["COMPRESSION VIEWED", labVisited && results ? `${codecLabel(codec)} / ${rateLabel(results.rates[rateIdx])}` : "NOT VISITED"],
    ["HRV", hrv && !hrv.error ? `SDNN ${fmt(hrv.sdnn)} MS / RMSSD ${fmt(hrv.rmssd)} MS${hrv.valid ? ` / LF/HF ${fmt(hrv.lf_hf, 2)}` : ""}` : "NOT MEASURED"],
  ];
  $("#res-context").innerHTML = ctxRows.map(([k, v]) => `<div><dt class="mono">${k}</dt><dd class="mono">${v}</dd></div>`).join("");
  const warns = [];
  if (session.ticks) {
    const lowShare = 1 - session.confidentTicks / session.ticks;
    warns.push([lowShare > .2 ? "warn" : "ok", `${pct(lowShare)} of analysed windows were below the confidence gate.`]);
  }
  if (last?.source === "sim") warns.push(["warn", "Simulated volunteer: the skin physics is modelled, not measured."]);
  if (last?.fitzpatrick >= 4) warns.push(["warn", "Darker skin: the confidence gate has been observed to pass wrong readings (replay 73 vs true 90 BPM)."]);
  if (last && !last.confident) warns.push(["warn", "The final reading is below the confidence gate."]);
  warns.push(["warn", "Research and wellness indicator, not a medical diagnosis."]);
  $("#res-warns").innerHTML = warns.map(([c, t]) => `<li class="${c}"><svg><use href="#i-${c === "ok" ? "check" : "alert"}"/></svg><span>${t}</span></li>`).join("");
  const tl = [
    ["Capture", session.captured, session.captured ? "OK" : "--"],
    ["Tracking", session.tracked, session.tracked ? "FACE LOCKED" : "--"],
    ["Signal extraction", session.extracted, session.extracted ? "RGB BUFFERED" : "--"],
    ["TRACE fusion", session.fused, session.fused ? `${session.shifts} SHIFTS` : "--"],
    ["Result", !!last, last ? `${fmt(last.bpm)} BPM` : "--", last && !last.confident],
  ];
  $("#res-timeline").innerHTML = tl.map(([n, ok, v, warn]) => `<li class="${warn ? "warn" : ok ? "done" : ""}"><span class="tk">${ok ? `<svg><use href="#i-${warn ? "alert" : "check"}"/></svg>` : ""}</span><span>${n}</span><span class="tv">${v}</span></li>`).join("");
}
$("#export").addEventListener("click", () => {
  const blob = new Blob([JSON.stringify({
    readings, heart_rhythm: hrv, weight_history: wHistory, events,
    session: { windows: session.ticks, confident_windows: session.confidentTicks, method_shifts: session.shifts },
    fusion_params: state.params || results?.params || null,
    note: "Research and wellness indicators, not a medical diagnosis.", exported: new Date().toISOString(),
  }, null, 2)], { type: "application/json" });
  const a = document.createElement("a"); a.href = URL.createObjectURL(blob); a.download = "trace-session.json"; a.click();
  setTimeout(() => URL.revokeObjectURL(a.href), 1000);
});
$("#new-session").addEventListener("click", newSession);

/* ================================================================== boot */
let resizeTimer = null;
window.addEventListener("resize", () => { clearTimeout(resizeTimer); resizeTimer = setTimeout(() => { moveIndicator(); renderAll(true); drawHrvCharts(); }, 120); });
async function loadData() {
  try { results = await (await fetch("/static/lab/results.json", { cache: "no-store" })).json(); } catch { results = null; }
  try { const l = await (await fetch("/api/lab")).json(); lab = l.available ? l : null; } catch { lab = null; }
  renderAll(true);
}
applyLang(); go("overview", { focus: false }); connect(); loadData(); renderHrv();
setInterval(() => { if (view === "setup") { renderSetup(); renderActions(); } }, 250);
