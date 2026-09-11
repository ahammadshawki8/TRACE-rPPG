"use strict";
/* TRACE live: one guided path through seven screens. */

const T = {
  en: {
    tagline: "contactless pulse", theme: "Theme",
    steps: ["Welcome", "Setup", "Pulse", "Methods", "Compression", "Rhythm", "Summary"],
    next: ["Start", "Continue", "Compare methods", "Open the compression lab", "Measure heart rhythm", "See the summary", "Start over"],
    "welcome.title": "See your heartbeat in a video of your face",
    "welcome.lede": "Each heartbeat pushes blood into your face and changes its colour by less than one percent. A camera can see it. The Fourier transform can find the rhythm in it.",
    "welcome.cam": "Use my camera", "welcome.camsub": "Sit facing a window or lamp.",
    "welcome.sim2": "Simulated volunteer, lighter skin", "welcome.simsub": "Fitzpatrick type II. The true heart rate is known.",
    "welcome.sim5": "Simulated volunteer, darker skin", "welcome.simsub5": "Fitzpatrick type V. The true heart rate is known.",
    "welcome.p1": "The video stays on this computer. This page receives only numbers and a small preview.",
    "welcome.p2": "No trained model is used. Every number comes from a convolution or a Fourier transform.",
    "welcome.p3": "This is a research and wellness tool, not a medical device. It does not diagnose anything.",
    "setup.title": "Let us check the picture", "setup.waiting": "Starting the video",
    "check.face": "Face in view", "fix.face": "Move so your whole face fits inside the frame.",
    "check.light": "Enough light on your face", "fix.light": "Face a window or lamp. Avoid a bright light behind you.",
    "check.still": "Holding fairly still", "fix.still": "Rest your head. Small movements are fine.",
    "setup.note": "The red box follows your face. The green boxes are the forehead and cheeks, where the pulse is strongest.",
    "live.title": "Your pulse, from colour alone",
    "how.summary": "How this works",
    "how.p1": "The average colour of your forehead and cheeks is measured thirty times a second. Slow lighting drift is removed by convolution with a moving average, and a bandpass filter keeps only 42 to 240 beats per minute.",
    "how.p2": "The Fourier transform then winds the signal around a circle at every candidate rate. Noise cancels itself out; the real rhythm piles up. The tallest peak in the spectrum is your heart rate.",
    unit: "beats per minute", confidence: "Confidence",
    "chart.raw": "Skin colour over the last 10 seconds", "chart.pulse": "After filtering: the pulse",
    "chart.spec": "Its spectrum. The peak is your heart rate.",
    "duel.title": "Four ways to read the same face",
    "duel.lede": "Now turn your head slowly or talk. Motion changes brightness; blood changes colour balance. The green channel cannot tell them apart. TRACE watches how much to trust each method and shifts its weight.",
    "m.green": "Green only", "m.greenw": "One colour channel, 2008", "m.chromw": "Colour difference, 2013",
    "m.posw": "Plane orthogonal to skin, 2017", "m.tracew": "All three, weighted by trust",
    "duel.motion": "Make the volunteer move more", "duel.still": "Make the volunteer sit still",
    "lab.title": "What a video call does to the pulse", simulated: "simulated",
    "lab.lede": "Video calls compress colour hardest, and colour is where the pulse lives. Slide the bitrate down and watch the error on lighter and darker skin.",
    "hrv.title": "The rhythm between beats",
    "hrv.lede": "A healthy heart is not a metronome. Taking a second Fourier transform of the gaps between beats shows two rhythms: one tied to blood pressure control, and one that is your breathing.",
    "hrv.need": "Needs at least two minutes of steady video. Five is the clinical standard.",
    "hrv.start": "Start the reading", "hrv.finish": "Finish and analyse", "hrv.empty": "Results appear here when the reading is finished.",
    "sum.title": "What we measured",
    "sum.caveat": "These are research and wellness indicators, not a medical diagnosis. Accuracy is lower on darker skin and on compressed video, which is exactly what this project measures.",
    "sum.export": "Save results as a file", back: "Back",
    collecting: s => `Collecting signal: ${s} s more`,
    low: "Low confidence. Hold still and keep your face lit.", steady: "Reading is steady.",
    fixfirst: "Fix the items marked in amber to continue.", allgood: "All checks pass.",
    hold: "Hold still", truth: v => `Simulator's true rate: ${v} BPM`, high: "high", lowword: "low",
    weightsTitle: "How much TRACE trusts each method right now",
    rateLabel: v => `Bitrate: ${v}`, lossless: "lossless",
    thLighter: "Lighter skin (I to III)", thDarker: "Darker skin (IV to VI)", thGap: "Gap", thMethod: "Method",
    labNote: n => `Mean absolute error in beats per minute, H.264, from the simulated pilot (${n} volunteers). Not yet measured on real people.`,
    thumbLight: v => `Lighter skin at ${v}`, thumbDark: v => `Darker skin at ${v}`,
    kept: (a, b) => `Pulse fidelity after compression (1 means intact, 0 means gone): ${a} on lighter skin, ${b} on darker skin.`,
    hrvRunning: s => `Recording: ${s}. Keep still and breathe normally.`,
    hrvShort: "Under two minutes: heart rate and beat statistics only, no LF/HF.",
    stat: { hr: "Average heart rate", sdnn: "SDNN", rmssd: "RMSSD", lfhf: "LF/HF", resp: "Breathing rate", beats: "Beats used" },
    tach: "Gaps between beats (ms)", psd: "Second spectrum: LF band (teal) and HF band (red)",
    sum: { hr: "Heart rate (TRACE)", conf: "Confidence", best: "Method trusted most", lfhf: "Heart rhythm LF/HF", resp: "Breathing rate", none: "Not measured" },
    camError: "No camera found. Go back and choose a simulated volunteer, or connect a webcam.",
    disconnected: "Lost contact with the local server. Is app/server.py still running?",
  },
  bn: {
    tagline: "স্পর্শহীন নাড়ি", theme: "থিম",
    steps: ["স্বাগতম", "প্রস্তুতি", "নাড়ি", "পদ্ধতি", "Compression", "ছন্দ", "সারাংশ"],
    next: ["শুরু করুন", "এগিয়ে যান", "পদ্ধতি তুলনা করুন", "compression ল্যাব খুলুন", "হৃৎছন্দ মাপুন", "সারাংশ দেখুন", "আবার শুরু করুন"],
    "welcome.title": "আপনার মুখের ভিডিওতে হৃৎস্পন্দন দেখুন",
    "welcome.lede": "প্রতিটি হৃৎস্পন্দন মুখে রক্ত পাঠায় এবং ত্বকের রঙ এক শতাংশেরও কম বদলায়। ক্যামেরা তা ধরতে পারে। Fourier transform সেই রঙের মধ্যে ছন্দটা খুঁজে বের করে।",
    "welcome.cam": "আমার ক্যামেরা ব্যবহার করুন", "welcome.camsub": "জানালা বা বাতির দিকে মুখ করে বসুন।",
    "welcome.sim2": "সিমুলেটেড স্বেচ্ছাসেবী, হালকা ত্বক", "welcome.simsub": "Fitzpatrick টাইপ II। আসল হার্ট রেট জানা আছে।",
    "welcome.sim5": "সিমুলেটেড স্বেচ্ছাসেবী, গাঢ় ত্বক", "welcome.simsub5": "Fitzpatrick টাইপ V। আসল হার্ট রেট জানা আছে।",
    "welcome.p1": "ভিডিও এই কম্পিউটারেই থাকে। এই পেজ শুধু সংখ্যা আর একটি ছোট প্রিভিউ পায়।",
    "welcome.p2": "কোনো trained model নেই। প্রতিটি সংখ্যা আসে একটি convolution বা Fourier transform থেকে।",
    "welcome.p3": "এটি গবেষণা ও সুস্থতার একটি টুল, চিকিৎসা যন্ত্র নয়। এটি কোনো রোগ নির্ণয় করে না।",
    "setup.title": "ছবিটা ঠিক আছে কিনা দেখে নিই", "setup.waiting": "ভিডিও চালু হচ্ছে",
    "check.face": "মুখ ফ্রেমের মধ্যে", "fix.face": "এমনভাবে বসুন যাতে পুরো মুখ ফ্রেমে থাকে।",
    "check.light": "মুখে যথেষ্ট আলো", "fix.light": "জানালা বা বাতির দিকে মুখ করুন। পেছনে উজ্জ্বল আলো রাখবেন না।",
    "check.still": "মোটামুটি স্থির", "fix.still": "মাথা স্থির রাখুন। একটু নড়াচড়া চলবে।",
    "setup.note": "লাল বাক্সটি আপনার মুখ অনুসরণ করে। সবুজ বাক্সগুলো কপাল আর গাল, যেখানে নাড়ির সংকেত সবচেয়ে শক্তিশালী।",
    "live.title": "শুধু রঙ থেকে আপনার নাড়ি",
    "how.summary": "কীভাবে কাজ করে",
    "how.p1": "প্রতি সেকেন্ডে ত্রিশবার আপনার কপাল ও গালের গড় রঙ মাপা হয়। moving average দিয়ে convolution করে ধীর আলোর পরিবর্তন সরানো হয়, আর একটি bandpass filter শুধু মিনিটে ৪২ থেকে ২৪০ স্পন্দন রাখে।",
    "how.p2": "তারপর Fourier transform সংকেতটিকে প্রতিটি সম্ভাব্য হারে একটি বৃত্তের চারপাশে পেঁচায়। noise নিজেই কাটাকাটি হয়ে যায়; আসল ছন্দ জমা হয়। spectrum-এর সবচেয়ে উঁচু চূড়াটিই আপনার হার্ট রেট।",
    unit: "স্পন্দন প্রতি মিনিট", confidence: "আস্থা",
    "chart.raw": "গত ১০ সেকেন্ডে ত্বকের রঙ", "chart.pulse": "filter-এর পরে: নাড়ি",
    "chart.spec": "এর spectrum। চূড়াটিই আপনার হার্ট রেট।",
    "duel.title": "একই মুখ পড়ার চারটি উপায়",
    "duel.lede": "এবার আস্তে মাথা ঘোরান বা কথা বলুন। নড়াচড়া উজ্জ্বলতা বদলায়; রক্ত রঙের ভারসাম্য বদলায়। green channel এই দুটো আলাদা করতে পারে না। TRACE প্রতিটি পদ্ধতিকে কতটা বিশ্বাস করা যায় তা দেখে ওজন সরিয়ে দেয়।",
    "m.green": "শুধু সবুজ", "m.greenw": "একটি রঙের চ্যানেল, ২০০৮", "m.chromw": "রঙের পার্থক্য, ২০১৩",
    "m.posw": "ত্বকের লম্ব সমতল, ২০১৭", "m.tracew": "তিনটিই, আস্থা অনুযায়ী ওজন",
    "duel.motion": "স্বেচ্ছাসেবীকে বেশি নড়াচড়া করান", "duel.still": "স্বেচ্ছাসেবীকে স্থির বসান",
    "lab.title": "ভিডিও কল নাড়ির সংকেতের কী করে", simulated: "সিমুলেটেড",
    "lab.lede": "ভিডিও কল রঙকে সবচেয়ে বেশি compress করে, আর নাড়ির সংকেত থাকে ঠিক রঙেই। bitrate কমিয়ে দেখুন হালকা ও গাঢ় ত্বকে ভুল কতটা বাড়ে।",
    "hrv.title": "স্পন্দনের মাঝের ছন্দ",
    "hrv.lede": "সুস্থ হৃৎপিণ্ড মেট্রোনোমের মতো বাজে না। স্পন্দনের মাঝের ফাঁকগুলোর উপর দ্বিতীয়বার Fourier transform নিলে দুটি ছন্দ দেখা যায়: একটি রক্তচাপ নিয়ন্ত্রণের, আরেকটি আপনার শ্বাস-প্রশ্বাস।",
    "hrv.need": "অন্তত দুই মিনিট স্থির ভিডিও লাগে। ক্লিনিক্যাল মান পাঁচ মিনিট।",
    "hrv.start": "রিডিং শুরু করুন", "hrv.finish": "শেষ করে বিশ্লেষণ করুন", "hrv.empty": "রিডিং শেষ হলে ফলাফল এখানে দেখা যাবে।",
    "sum.title": "আমরা যা মাপলাম",
    "sum.caveat": "এগুলো গবেষণা ও সুস্থতার সূচক, রোগ নির্ণয় নয়। গাঢ় ত্বকে এবং compressed ভিডিওতে নির্ভুলতা কম, আর এই প্রজেক্ট ঠিক সেটাই মাপে।",
    "sum.export": "ফলাফল ফাইল হিসেবে সংরক্ষণ করুন", back: "পেছনে",
    collecting: s => `সংকেত সংগ্রহ হচ্ছে: আর ${s} সেকেন্ড`,
    low: "আস্থা কম। স্থির থাকুন এবং মুখে আলো রাখুন।", steady: "রিডিং স্থির।",
    fixfirst: "এগোতে হলে হলুদ চিহ্নিত বিষয়গুলো ঠিক করুন।", allgood: "সব ঠিক আছে।",
    hold: "স্থির থাকুন", truth: v => `সিমুলেটরের আসল হার: ${v} BPM`, high: "উচ্চ", lowword: "কম",
    weightsTitle: "TRACE এই মুহূর্তে প্রতিটি পদ্ধতিকে কতটা বিশ্বাস করছে",
    rateLabel: v => `Bitrate: ${v}`, lossless: "lossless",
    thLighter: "হালকা ত্বক (I থেকে III)", thDarker: "গাঢ় ত্বক (IV থেকে VI)", thGap: "পার্থক্য", thMethod: "পদ্ধতি",
    labNote: n => `গড় পরম ভুল (BPM), H.264, সিমুলেটেড পাইলট (${n} জন স্বেচ্ছাসেবী)। বাস্তব মানুষের উপর এখনো মাপা হয়নি।`,
    thumbLight: v => `হালকা ত্বক, ${v}`, thumbDark: v => `গাঢ় ত্বক, ${v}`,
    kept: (a, b) => `compression-এর পরে নাড়ির সংকেত কতটা অক্ষত (১ মানে পুরোটা, ০ মানে কিছুই নেই): হালকা ত্বকে ${a}, গাঢ় ত্বকে ${b}।`,
    hrvRunning: s => `রেকর্ড হচ্ছে: ${s}। স্থির থাকুন এবং স্বাভাবিকভাবে শ্বাস নিন।`,
    hrvShort: "দুই মিনিটের কম: শুধু হার্ট রেট ও স্পন্দনের পরিসংখ্যান, LF/HF নয়।",
    stat: { hr: "গড় হার্ট রেট", sdnn: "SDNN", rmssd: "RMSSD", lfhf: "LF/HF", resp: "শ্বাসের হার", beats: "ব্যবহৃত স্পন্দন" },
    tach: "স্পন্দনের মাঝের ফাঁক (ms)", psd: "দ্বিতীয় spectrum: LF band (সবুজাভ) এবং HF band (লাল)",
    sum: { hr: "হার্ট রেট (TRACE)", conf: "আস্থা", best: "সবচেয়ে বিশ্বস্ত পদ্ধতি", lfhf: "হৃৎছন্দ LF/HF", resp: "শ্বাসের হার", none: "মাপা হয়নি" },
    camError: "কোনো ক্যামেরা পাওয়া যায়নি। পেছনে গিয়ে সিমুলেটেড স্বেচ্ছাসেবী বেছে নিন, অথবা webcam লাগান।",
    disconnected: "লোকাল সার্ভারের সাথে যোগাযোগ বিচ্ছিন্ন। app/server.py কি এখনো চলছে?",
  },
};

const $ = s => document.querySelector(s);
const $$ = s => Array.from(document.querySelectorAll(s));
let lang = localGet("lang") || "en";
let step = 0, maxStep = 0;
let state = {}, lab = null, hrv = null, readings = [];
let ws = null, simSource = null, hrvTimer = null, readySince = null;
const L = () => T[lang];

function localGet(k) { try { return localStorage.getItem(k); } catch { return null; } }
function localSet(k, v) { try { localStorage.setItem(k, v); } catch { /* storage unavailable */ } }

/* --------------------------------------------------------------- language */
function applyLang() {
  document.documentElement.lang = lang;
  $$("[data-i18n]").forEach(el => { const v = L()[el.dataset.i18n]; if (typeof v === "string") el.textContent = v; });
  $("#lang").textContent = lang === "en" ? "বাংলা" : "English";
  $("#weights").setAttribute("aria-label", L().weightsTitle);
  renderStepper(); renderActions(); renderLab(); renderHrv(); renderSummary();
}
$("#lang").addEventListener("click", () => { lang = lang === "en" ? "bn" : "en"; localSet("lang", lang); applyLang(); });

/* --------------------------------------------------------------- theme */
function applyTheme(t) { if (t) document.documentElement.dataset.theme = t; else delete document.documentElement.dataset.theme; }
applyTheme(localGet("theme"));
$("#theme").addEventListener("click", () => {
  const dark = matchMedia("(prefers-color-scheme: dark)").matches;
  const cur = document.documentElement.dataset.theme || (dark ? "dark" : "light");
  const nxt = cur === "dark" ? "light" : "dark";
  applyTheme(nxt); localSet("theme", nxt); drawAll();
});

/* --------------------------------------------------------------- steps */
function renderStepper() {
  const ol = $("#stepper");
  ol.innerHTML = "";
  L().steps.forEach((name, i) => {
    const li = document.createElement("li");
    const b = document.createElement("button");
    b.type = "button";
    b.className = i === step ? "current" : i < step || i <= maxStep ? "done" : "";
    b.disabled = i > maxStep;
    b.innerHTML = `<span class="n">${i + 1}</span><span class="label"></span>`;
    b.querySelector(".label").textContent = name;
    if (i === step) b.setAttribute("aria-current", "step");
    b.addEventListener("click", () => go(i));
    li.appendChild(b); ol.appendChild(li);
  });
}

function go(n) {
  step = Math.max(0, Math.min(6, n));
  maxStep = Math.max(maxStep, step);
  $$(".screen").forEach(s => s.classList.toggle("active", +s.dataset.step === step));
  $("#sim-motion").hidden = !simSource;
  if (step === 4) loadLab();
  if (step === 6) renderSummary();
  renderStepper(); renderActions(); drawAll();
  window.scrollTo({ top: 0 });
  const h = $(`.screen[data-step="${step}"] h1`);
  if (h) { h.setAttribute("tabindex", "-1"); h.focus({ preventScroll: true }); }
}

function canAdvance() {
  if (step === 1) return !!(readySince && performance.now() - readySince > 1500);
  return true;
}

function renderActions() {
  $("#next").textContent = L().next[step];
  $("#back").hidden = step === 0;
  $("#next").disabled = !canAdvance();
}

$("#next").addEventListener("click", () => {
  if (step === 0) { startSource(); go(1); return; }
  if (step === 2) snapshotReading();
  if (step === 6) { send({ cmd: "stop" }); readings = []; hrv = null; maxStep = 0; go(0); return; }
  go(step + 1);
});
$("#back").addEventListener("click", () => go(step - 1));
document.addEventListener("keydown", e => {
  if (e.target.matches("input, textarea, select")) return;
  if (e.key === "ArrowRight" && !$("#next").disabled) $("#next").click();
  if (e.key === "ArrowLeft" && step > 0) go(step - 1);
});

/* --------------------------------------------------------------- server link */
function connect() {
  ws = new WebSocket(`ws://${location.host}/ws`);
  ws.onmessage = ev => {
    const msg = JSON.parse(ev.data);
    if (msg.type === "state") { state = msg.state || {}; onState(); }
    if (msg.type === "hrv") { hrv = msg.result; renderHrv(); }
  };
  ws.onclose = () => { $("#status").textContent = L().disconnected; setTimeout(connect, 1500); };
}
function send(o) { if (ws && ws.readyState === 1) ws.send(JSON.stringify(o)); }

function startSource(motion) {
  const v = document.querySelector('input[name="source"]:checked').value;
  simSource = v.startsWith("sim") ? { fitzpatrick: v === "sim5" ? 5 : 2, motion: motion ?? 0.3 } : null;
  send(simSource ? { cmd: "start", source: "sim", options: simSource } : { cmd: "start", source: "webcam" });
  $$("img.feed").forEach(img => { img.src = `/video.mjpg?${Date.now()}`; });
}
$("#more-motion").addEventListener("click", () => startSource(1.6));
$("#less-motion").addEventListener("click", () => startSource(0.2));

/* --------------------------------------------------------------- live state */
function onState() {
  const s = state;
  const running = !!s.running;
  $$(".camera .empty").forEach(el => { el.hidden = running; if (s.error) el.textContent = s.error.includes("camera") ? L().camError : s.error; });

  const checks = s.checks || {};
  $$("#checks li").forEach(li => {
    const ok = !!checks[li.dataset.check];
    li.classList.toggle("ok", ok); li.classList.toggle("bad", running && !ok);
    li.querySelector(".mark").textContent = ok ? "" : running ? "!" : "";
    li.querySelector(".fix").hidden = ok;
  });
  const allOk = running && checks.face && checks.light && checks.still;
  if (allOk && !readySince) readySince = performance.now();
  if (!allOk) readySince = null;

  // read-out
  const bpmEl = $("#bpm");
  const have = typeof s.bpm === "number";
  if (!have) {
    bpmEl.textContent = "--"; bpmEl.className = "bpm dim";
  } else if (!s.confident) {
    bpmEl.innerHTML = `<span class="hold">${L().hold}</span>`; bpmEl.className = "bpm";
  } else {
    bpmEl.textContent = Math.round(s.bpm); bpmEl.className = "bpm";
  }
  // The meter is scaled so the frozen confidence threshold sits at its middle.
  const thr = s.params && s.params.confidence ? s.params.confidence : 0.35;
  const q = have ? Math.max(0, Math.min(1, s.quality / (2 * thr))) : 0;
  $("#meter i").style.width = `${Math.round(q * 100)}%`;
  $("#meter").classList.toggle("low", have && !s.confident);
  $("#conf-text").textContent = have ? (s.confident ? L().high : L().lowword) : "";
  $("#truth").textContent = s.true_bpm ? L().truth(Math.round(s.true_bpm)) : "";

  // duel
  const m = s.methods || {};
  const setV = (id, v, off) => { const el = $(id); el.textContent = v == null ? "--" : Math.round(v); el.classList.toggle("off", !!off); };
  const truthOr = s.true_bpm || s.bpm;
  setV("#v-green", s.naive_green, truthOr && s.naive_green && Math.abs(s.naive_green - truthOr) > 5);
  setV("#v-chrom", m.chrom && m.chrom.bpm, truthOr && m.chrom && Math.abs(m.chrom.bpm - truthOr) > 5);
  setV("#v-pos", m.pos && m.pos.bpm, truthOr && m.pos && Math.abs(m.pos.bpm - truthOr) > 5);
  setV("#v-trace", have ? s.bpm : null, s.true_bpm && have && Math.abs(s.bpm - s.true_bpm) > 5);
  renderWeights(s.weights || {});

  // status line
  let msg = "";
  if (s.error) msg = s.error.includes("camera") ? L().camError : s.error;
  else if (step === 1) msg = allOk ? L().allgood : running ? L().fixfirst : "";
  else if (step >= 2 && step <= 3 && running) {
    if (!have) msg = L().collecting(Math.max(0, Math.ceil((s.needed_s || 8) - (s.buffered_s || 0))));
    else msg = s.confident ? L().steady : L().low;
  } else if (step === 5 && s.hrv_elapsed != null && !hrv) msg = L().hrvRunning(fmtTime(s.hrv_elapsed));
  $("#status").textContent = msg;

  if (step === 5) updateRing();
  renderActions();
  drawAll();
}

function renderWeights(w) {
  const box = $("#weights");
  const names = { green: L()["m.green"], chrom: "CHROM", pos: "POS" };
  box.innerHTML = "";
  for (const k of ["green", "chrom", "pos"]) {
    const v = w[k] || 0;
    const row = document.createElement("div");
    row.className = "row";
    row.innerHTML = `<span></span><span class="bar"><i style="width:${Math.round(v * 100)}%"></i></span><span class="pct">${Math.round(v * 100)}%</span>`;
    row.firstChild.textContent = names[k];
    box.appendChild(row);
  }
}

function snapshotReading() {
  if (typeof state.bpm === "number") readings.push({ bpm: state.bpm, quality: state.quality, confident: state.confident,
    weights: state.weights, truth: state.true_bpm || null, at: new Date().toISOString() });
}

/* --------------------------------------------------------------- charts */
function css(name) { return getComputedStyle(document.documentElement).getPropertyValue(name).trim(); }
function fit(cv) {
  const dpr = window.devicePixelRatio || 1, w = cv.clientWidth, h = +cv.getAttribute("height");
  if (!w) return null;
  if (cv.width !== Math.round(w * dpr)) { cv.width = Math.round(w * dpr); cv.height = Math.round(h * dpr); cv.style.height = h + "px"; }
  const ctx = cv.getContext("2d"); ctx.setTransform(dpr, 0, 0, dpr, 0, 0); ctx.clearRect(0, 0, w, h);
  return { ctx, w, h };
}
function line(cv, ys, color, width) {
  const f = fit(cv); if (!f || !ys || ys.length < 2) return;
  const { ctx, w, h } = f;
  let lo = Math.min(...ys), hi = Math.max(...ys); if (hi - lo < 1e-9) { hi += 1; lo -= 1; }
  ctx.strokeStyle = css("--rule"); ctx.lineWidth = 1; ctx.beginPath(); ctx.moveTo(0, h / 2); ctx.lineTo(w, h / 2); ctx.stroke();
  ctx.strokeStyle = color; ctx.lineWidth = width; ctx.lineJoin = "round"; ctx.beginPath();
  ys.forEach((y, i) => { const px = i / (ys.length - 1) * w, py = h - 6 - (y - lo) / (hi - lo) * (h - 12); i ? ctx.lineTo(px, py) : ctx.moveTo(px, py); });
  ctx.stroke();
}
function spectrum(cv, sp) {
  const f = fit(cv); if (!f || !sp || !sp.f) return;
  const { ctx, w, h } = f, pad = 18;
  const x = v => (v - sp.f[0]) / (sp.f[sp.f.length - 1] - sp.f[0]) * w;
  ctx.fillStyle = css("--pulse-soft"); ctx.strokeStyle = css("--pulse"); ctx.lineWidth = 2;
  ctx.beginPath(); ctx.moveTo(0, h - pad);
  sp.f.forEach((v, i) => ctx.lineTo(x(v), h - pad - sp.p[i] * (h - pad - 8)));
  ctx.lineTo(w, h - pad); ctx.closePath(); ctx.fill();
  ctx.beginPath(); sp.f.forEach((v, i) => { const py = h - pad - sp.p[i] * (h - pad - 8); i ? ctx.lineTo(x(v), py) : ctx.moveTo(x(v), py); }); ctx.stroke();
  ctx.fillStyle = css("--ink-3"); ctx.font = "11px Archivo, system-ui, sans-serif"; ctx.textAlign = "center";
  [60, 90, 120, 150, 180, 210].forEach(b => { if (b >= sp.f[0] && b <= sp.f[sp.f.length - 1]) ctx.fillText(b, x(b), h - 4); });
  if (sp.peak) {
    ctx.strokeStyle = css("--ink"); ctx.lineWidth = 1; ctx.setLineDash([3, 3]);
    ctx.beginPath(); ctx.moveTo(x(sp.peak), 4); ctx.lineTo(x(sp.peak), h - pad); ctx.stroke(); ctx.setLineDash([]);
    ctx.fillStyle = css("--ink"); ctx.textAlign = x(sp.peak) > w - 60 ? "right" : "left";
    ctx.fillText(`${Math.round(sp.peak)} BPM`, x(sp.peak) + (ctx.textAlign === "left" ? 6 : -6), 14);
  }
}
function drawAll() {
  if (step === 2 && state.trace) {
    line($("#c-raw"), state.trace.raw, css("--ink-3"), 1.5);
    line($("#c-pulse"), state.trace.pulse, css("--pulse"), 2);
    spectrum($("#c-spec"), state.spectrum);
  }
  if (step === 5 && hrv && hrv.rr_ms) drawHrvCharts();
}
window.addEventListener("resize", drawAll);

/* --------------------------------------------------------------- compression lab */
async function loadLab() {
  if (lab) return renderLab();
  try { lab = await (await fetch("/api/lab")).json(); } catch { lab = { available: false, message: "" }; }
  renderLab();
}
function rateName(k) { return k === "lossless" ? L().lossless : `${k} kbps`; }
function renderLab() {
  if (!lab) return;
  $("#lab-missing").hidden = lab.available; $("#lab-body").hidden = !lab.available;
  if (!lab.available) { $("#lab-missing").textContent = lab.message; return; }
  const rates = lab.rates;
  const slider = $("#rate");
  slider.max = rates.length - 1;
  const r = rates[+slider.value];
  $("#rate-label").textContent = L().rateLabel(rateName(r));
  $("#rate-ticks").innerHTML = rates.map(k => `<span>${k === "lossless" ? L().lossless : k}</span>`).join("");
  const rows = lab.methods.map(m => {
    const a = lab.mae[m][r]?.["I-III"], b = lab.mae[m][r]?.["IV-VI"];
    const f = v => v == null ? "--" : v.toFixed(1);
    return `<tr><td>${lab.labels[m]}</td><td>${f(a)}</td><td>${f(b)}</td><td class="gap">${a == null || b == null ? "--" : (b - a >= 0 ? "+" : "") + (b - a).toFixed(1)}</td></tr>`;
  }).join("");
  $("#lab-table").innerHTML = `<thead><tr><th>${L().thMethod}</th><th>${L().thLighter}</th><th>${L().thDarker}</th><th>${L().thGap}</th></tr></thead><tbody>${rows}</tbody>`;
  const th = lab.thumbs[r] || {};
  $("#thumbs").innerHTML = ["II", "V"].map(t => th[t] ? `<figure><img src="${th[t]}" alt=""><figcaption>${t === "II" ? L().thumbLight(rateName(r)) : L().thumbDark(rateName(r))}</figcaption></figure>` : "").join("");
  const kept = lab.kept[r];
  $("#lab-note").textContent = L().labNote(lab.n_subjects) + (kept ? " " + L().kept(kept.II.toFixed(2), kept.VI.toFixed(2)) : "");
}
$("#rate").addEventListener("input", renderLab);

/* --------------------------------------------------------------- heart rhythm */
function fmtTime(s) { s = Math.max(0, Math.floor(s)); return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`; }
function updateRing() {
  const el = state.hrv_elapsed;
  if (el == null) return;
  const need = state.hrv_needed || 120;
  const frac = Math.min(1, el / need);
  $("#ring-fg").style.strokeDashoffset = String(326.7 * (1 - frac));
  $("#ring-label").textContent = fmtTime(el);
  $("#hrv-done").disabled = el < 30;
}
$("#hrv-go").addEventListener("click", () => { hrv = null; renderHrv(); send({ cmd: "hrv_start" }); });
$("#hrv-done").addEventListener("click", () => send({ cmd: "hrv_finish" }));

function renderHrv() {
  const out = $("#hrv-out");
  if (!hrv) { out.innerHTML = `<p class="note">${L()["hrv.empty"]}</p>`; return; }
  if (hrv.error) { out.innerHTML = `<p class="caveat"></p>`; out.firstChild.textContent = hrv.error; return; }
  const S = L().stat, f = (v, d = 0) => v == null ? "--" : (+v).toFixed(d);
  out.innerHTML = `
    <div class="hrv-stats">
      <div><span>${S.hr}</span><b>${f(hrv.mean_hr)}</b></div>
      <div><span>${S.sdnn}</span><b>${f(hrv.sdnn)} ms</b></div>
      <div><span>${S.rmssd}</span><b>${f(hrv.rmssd)} ms</b></div>
      <div><span>${S.lfhf}</span><b>${hrv.valid ? f(hrv.lf_hf, 2) : "--"}</b></div>
      <div><span>${S.resp}</span><b>${hrv.valid && hrv.resp_bpm ? f(hrv.resp_bpm) + "/min" : "--"}</b></div>
      <div><span>${S.beats}</span><b>${hrv.rr_ms.length + 1}</b></div>
    </div>
    <div class="chart-block"><h3>${L().tach}</h3><canvas class="chart" id="c-tach" height="100"></canvas></div>
    ${hrv.psd_f ? `<div class="chart-block"><h3>${L().psd}</h3><canvas class="chart" id="c-psd" height="120"></canvas></div>` : ""}
    <p class="indicator"></p>
    ${hrv.valid ? "" : `<p class="note">${L().hrvShort}</p>`}`;
  out.querySelector(".indicator").textContent = hrv.indicator;
  drawHrvCharts();
}
function drawHrvCharts() {
  const t = $("#c-tach"); if (t) line(t, hrv.rr_ms, css("--ink"), 1.6);
  const c = $("#c-psd"); if (!c || !hrv.psd_f) return;
  const fc = fit(c); if (!fc) return;
  const { ctx, w, h } = fc, fmax = 0.5, pmax = Math.max(...hrv.psd_p) || 1, pad = 16;
  const x = v => v / fmax * w;
  const band = (a, b, col) => { ctx.fillStyle = col; ctx.fillRect(x(a), 4, x(b) - x(a), h - pad - 4); };
  band(0.04, 0.15, css("--good-soft")); band(0.15, 0.40, css("--pulse-soft"));
  ctx.strokeStyle = css("--ink"); ctx.lineWidth = 1.8; ctx.beginPath();
  hrv.psd_f.forEach((v, i) => { const py = h - pad - hrv.psd_p[i] / pmax * (h - pad - 8); i ? ctx.lineTo(x(v), py) : ctx.moveTo(x(v), py); });
  ctx.stroke();
  ctx.fillStyle = css("--ink-3"); ctx.font = "11px Archivo, system-ui, sans-serif"; ctx.textAlign = "center";
  [0.1, 0.2, 0.3, 0.4].forEach(v => ctx.fillText(`${v} Hz`, x(v), h - 3));
}

/* --------------------------------------------------------------- summary */
function renderSummary() {
  const S = L().sum, box = $("#summary");
  const last = readings[readings.length - 1];
  const rows = [
    [S.hr, last ? `${Math.round(last.bpm)} BPM` + (last.truth ? ` (${L().truth(Math.round(last.truth))})` : "") : S.none],
    [S.conf, last ? `${last.confident ? L().high : L().lowword} (${last.quality.toFixed(2)})` : S.none],
    [S.best, last && last.weights ? Object.entries(last.weights).sort((a, b) => b[1] - a[1])[0][0].toUpperCase() : S.none],
    [S.lfhf, hrv && hrv.valid && hrv.lf_hf != null ? hrv.lf_hf.toFixed(2) : S.none],
    [S.resp, hrv && hrv.valid && hrv.resp_bpm ? `${Math.round(hrv.resp_bpm)}/min` : S.none],
  ];
  box.innerHTML = "";
  rows.forEach(([k, v]) => { const d = document.createElement("div"); d.innerHTML = "<span></span><b></b>"; d.children[0].textContent = k; d.children[1].textContent = v; box.appendChild(d); });
}
$("#export").addEventListener("click", () => {
  const blob = new Blob([JSON.stringify({ readings, heart_rhythm: hrv, note: "Research and wellness indicators, not a medical diagnosis.",
    exported: new Date().toISOString() }, null, 2)], { type: "application/json" });
  const a = document.createElement("a"); a.href = URL.createObjectURL(blob); a.download = "trace-results.json"; a.click();
  setTimeout(() => URL.revokeObjectURL(a.href), 1000);
});

/* --------------------------------------------------------------- boot */
applyLang(); go(0); connect();
