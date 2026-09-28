"use strict";
/* TRACE rPPG: volunteer data collection.
   Records real volunteers from the webcam while the presenter types in the
   smartwatch reading. The watch measures for about 20 s and then locks. The
   presenter presses Mark (Space) the instant the watch shows its number and
   types it afterwards, so typing delay never shifts the comparison window.
   Readings are accepted at any time from 0:20 on. The server stores the skin-colour trace (no video unless chosen),
   the conditions and the readings, and scores every reading against the
   app's own read-out. Shares the helpers and the WebSocket of app.js. */

const COL = {
  data: null, study: null, selected: localGet("col-volunteer") || "", form: null, formMsg: "",
  lighting: "room light", motion: "still", duration: 90, watch: localGet("col-watch") || "", keepVideo: false,
  confirm: null, built: false, btnKey: "",
};
let colSeenLast = null;
const MIN_READ_AT = 20; // seconds: TRACE needs a full 20 s window before a reading can be compared
const PROTOCOL = [["room light", "still"], ["room light", "talking"], ["dim room", "still"], ["room light", "head movement"]];
const SEX = ["female", "male", "other", "not given"];
const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const skinOf = v => v.fitzpatrick_rated || v.fitzpatrick_self;
const who = v => v.name ? `${esc(v.name)} <span class="muted">${v.code}</span>` : v.code;

async function colLoad() {
  try {
    COL.data = await (await fetch("/api/collect", { cache: "no-store" })).json();
    COL.study = await (await fetch("/api/collect/study", { cache: "no-store" })).json();
  } catch { /* server offline: keep what we had */ }
  if (COL.selected && COL.data && !COL.data.volunteers[COL.selected]) COL.selected = "";
  colRenderStatic();
}

function colRenderStatic() {
  if (!COL.data) return;
  colStrip(); colVolunteer(); colControls(); colManage();  // study results live on Scenarios
}

/* ------------------------------------------------------------ summary strip */
function colStrip() {
  const n = Object.keys(COL.data.volunteers).length, target = 20, st = COL.study || {};
  $("#col-strip").innerHTML = `
    <div class="strip-stats">
      <div><span class="label mono">VOLUNTEERS</span><b class="mono">${n}<small> / ${target} TARGET</small></b></div>
      <div><span class="label mono">RECORDINGS</span><b class="mono">${COL.data.clips.length}</b></div>
      <div><span class="label mono">WATCH READINGS SCORED</span><b class="mono">${st.n_readings ?? 0}</b></div>
      <div class="grow"><span class="label mono">PROGRESS TO ${target} VOLUNTEERS</span><div class="bar"><i style="width:${Math.min(100, n / target * 100)}%"></i></div></div>
    </div>
    <p class="foot">Per volunteer, record four 90 s clips: still in room light, talking, still in a dim room, and slow head movement. Start the watch with the recording. Each time it shows a number, press Mark (Space) at once, type the number, then restart the watch. You read the watch; the volunteer keeps still. Only colour averages of the forehead and cheeks are stored unless the volunteer agrees to keep video.</p>`;
}

/* ------------------------------------------------------------ volunteer card */
function colVolunteer() {
  if (COL.form) return colForm();
  const box = $("#col-volunteer"), vols = COL.data.volunteers, list = Object.values(vols), v = vols[COL.selected];
  const done = COL.data.clips.filter(c => c.volunteer === COL.selected);
  box.innerHTML = `
    <header class="card-h"><span class="label mono">VOLUNTEER</span><button class="btn ghost small" type="button" id="col-new">New volunteer</button></header>
    ${list.length ? `<label class="field"><span class="label mono">SELECT</span>
      <select id="col-select"><option value="">Choose a volunteer</option>${list.map(x =>
        `<option value="${x.code}" ${x.code === COL.selected ? "selected" : ""}>${x.name ? esc(x.name) + " / " : ""}${x.code} / ${x.age_group} / type ${ROMAN[skinOf(x)]}</option>`).join("")}</select></label>`
      : `<div class="empty-state small"><p>No volunteers yet. Register the first one.</p></div>`}
    ${v ? `<dl class="kv">
        <div><dt class="mono">NAME</dt><dd class="mono">${v.name ? esc(v.name) : "--"}</dd></div>
        <div><dt class="mono">AGE GROUP</dt><dd class="mono">${v.age_group.toUpperCase()}</dd></div>
        <div><dt class="mono">SEX</dt><dd class="mono">${v.sex.toUpperCase()}</dd></div>
        <div><dt class="mono">SKIN TYPE</dt><dd class="mono"><span class="swatch-dot" style="--sw:rgb(${SKIN_RGB[skinOf(v)].join(",")})"></span>${ROMAN[v.fitzpatrick_self]} SELF${v.fitzpatrick_rated ? ` / ${ROMAN[v.fitzpatrick_rated]} RATED` : ""}</dd></div>
        <div><dt class="mono">CONSENT</dt><dd class="mono good">GIVEN ${v.consent_at.slice(0, 10)}${v.guardian_consent ? " / GUARDIAN" : ""}</dd></div>
      </dl>
      <span class="label mono">PROTOCOL</span>
      <ol class="protocol">${PROTOCOL.map(([l, m]) => {
        const ok = done.some(c => c.condition.lighting === l && c.condition.motion === m && c.completed);
        return `<li class="${ok ? "done" : ""}"><button type="button" data-cond="${l}|${m}"><svg><use href="#i-${ok ? "check" : "rec"}"/></svg>${m} / ${l}</button></li>`;
      }).join("")}</ol>
      <div class="btn-row"><button class="btn ghost small" type="button" id="col-edit">Edit details</button></div>` : ""}`;
  box.querySelector("#col-new").addEventListener("click", () => { COL.form = { mode: "new" }; COL.formMsg = ""; colVolunteer(); });
  const sel = box.querySelector("#col-select");
  if (sel) sel.addEventListener("change", e => { COL.selected = e.target.value; localSet("col-volunteer", COL.selected); colVolunteer(); colControls(); });
  box.querySelectorAll("[data-cond]").forEach(b => b.addEventListener("click", () => { [COL.lighting, COL.motion] = b.dataset.cond.split("|"); colControls(); }));
  const ed = box.querySelector("#col-edit");
  if (ed) ed.addEventListener("click", () => { COL.form = { mode: "edit", v }; COL.formMsg = ""; colVolunteer(); });
}

function colForm() {
  const box = $("#col-volunteer"), opts = COL.data.options, v = COL.form.v || {}, edit = COL.form.mode === "edit";
  const chk = (name, val) => (String(v[name] ?? "") === String(val) ? "checked" : "");
  box.innerHTML = `
    <header class="card-h"><span class="label mono">${edit ? `EDIT ${v.code}` : "NEW VOLUNTEER"}</span><button class="btn ghost small" type="button" id="col-cancel">Cancel</button></header>
    <form id="col-form" class="form">
      <label class="field"><span class="label mono">NAME OR USERNAME (OPTIONAL)</span><input name="name" maxlength="60" value="${esc(v.name)}" placeholder="shown only in this portal">
        <span class="foot">Stays on this computer. Never exported: the CSV and every analysis use the code.</span></label>
      <fieldset><legend class="label mono">AGE GROUP</legend><div class="seg small wrap">${opts.age_groups.map(a => `<label><input type="radio" name="age_group" value="${a}" required ${chk("age_group", a)}><span>${a}</span></label>`).join("")}</div></fieldset>
      <fieldset><legend class="label mono">SEX (OPTIONAL)</legend><div class="seg small wrap">${SEX.map(s => `<label><input type="radio" name="sex" value="${s}" ${edit ? chk("sex", s) : s === "not given" ? "checked" : ""}><span>${s}</span></label>`).join("")}</div></fieldset>
      <fieldset><legend class="label mono">SKIN TYPE, AS THE VOLUNTEER DESCRIBES IT</legend>
        <div class="swatches">${[1, 2, 3, 4, 5, 6].map(k => `<label><input type="radio" name="fitzpatrick_self" value="${k}" required ${chk("fitzpatrick_self", k)}><i style="--sw:rgb(${SKIN_RGB[k].join(",")})"></i><span class="mono">${ROMAN[k]}</span></label>`).join("")}</div>
        <p class="foot">I always burns, never tans. II usually burns. III sometimes burns, tans gradually. IV rarely burns, tans easily. V very rarely burns, brown skin. VI never burns, dark brown or black skin.</p></fieldset>
      <label class="field"><span class="label mono">SKIN TYPE, AS YOU RATE IT (OPTIONAL)</span>
        <select name="fitzpatrick_rated"><option value="">Not rated</option>${[1, 2, 3, 4, 5, 6].map(k => `<option value="${k}" ${v.fitzpatrick_rated === k ? "selected" : ""}>${ROMAN[k]}</option>`).join("")}</select></label>
      <div class="consent">
        <p><b>What the volunteer agrees to.</b> A webcam records their face for about a minute at a time while a smartwatch measures their heart rate. The computer keeps the average colour of the forehead and cheeks for each frame, the face position, the smartwatch readings, the age group, sex if given, skin type and, if given, a name or username. The name never leaves this computer. Video is kept only if they also agree to that when recording. Everything is used only for this university project and deleted on request or when the project ends. This is not a medical test.</p>
        <label class="check"><input type="checkbox" name="consent" ${edit ? "checked" : ""}> The volunteer has read this and agrees.</label>
        <label class="check"><input type="checkbox" name="guardian_consent" ${v.guardian_consent ? "checked" : ""}> A parent or guardian agrees (required under 18).</label>
      </div>
      <label class="field"><span class="label mono">NOTES (OPTIONAL)</span><input name="notes" maxlength="300" value="${esc(v.notes)}" placeholder="for example: glasses, beard"></label>
      <p class="form-msg" id="col-form-msg" role="alert">${esc(COL.formMsg)}</p>
      <button class="btn primary" type="submit">${edit ? "Save changes" : "Register volunteer"}</button>
    </form>`;
  box.querySelector("#col-cancel").addEventListener("click", () => { COL.form = null; colVolunteer(); });
  box.querySelector("#col-form").addEventListener("submit", async e => {
    e.preventDefault();
    const f = new FormData(e.target), body = Object.fromEntries(f.entries());
    body.consent = f.has("consent"); body.guardian_consent = f.has("guardian_consent");
    if (edit) body.code = v.code;
    const r = await fetch("/api/collect/volunteer", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
    const j = await r.json();
    if (!r.ok) { COL.formMsg = j.detail || "Could not save."; $("#col-form-msg").textContent = COL.formMsg; return; }
    COL.form = null; COL.selected = j.code; localSet("col-volunteer", j.code); colLoad();
  });
}

/* ------------------------------------------------------------ recording controls */
function colControls() {
  const o = COL.data.options, box = $("#col-controls");
  const seg = (name, vals, cur) => `<div class="seg small wrap" data-colseg="${name}" role="radiogroup">${vals.map(v =>
    `<button type="button" role="radio" data-val="${v}" aria-checked="${String(v) === String(cur)}">${v}</button>`).join("")}</div>`;
  box.innerHTML = `
    <div class="ctl"><span class="label mono">LIGHTING</span>${seg("lighting", o.lighting, COL.lighting)}</div>
    <div class="ctl"><span class="label mono">MOTION TASK</span>${seg("motion", o.motion, COL.motion)}</div>
    <div class="ctl"><span class="label mono">LENGTH (S)</span>${seg("duration", [60, 90, 120], COL.duration)}</div>
    <label class="field"><span class="label mono">SMARTWATCH MODEL</span><input id="col-watch-model" value="${esc(COL.watch)}" placeholder="for example: Galaxy Watch 6"></label>
    <label class="check"><input type="checkbox" id="col-keep" ${COL.keepVideo ? "checked" : ""}> Keep video too (volunteer agreed; about 100 MB per minute)</label>
    <div class="btn-row" id="col-buttons"></div>`;
  box.querySelectorAll("[data-colseg]").forEach(g => g.querySelectorAll("button").forEach(b => b.addEventListener("click", () => {
    const k = g.dataset.colseg; COL[k] = k === "duration" ? +b.dataset.val : b.dataset.val; colControls();
  })));
  box.querySelector("#col-watch-model").addEventListener("change", e => { COL.watch = e.target.value; localSet("col-watch", COL.watch); });
  box.querySelector("#col-keep").addEventListener("change", e => { COL.keepVideo = e.target.checked; });
  COL.btnKey = "";
  colDynamic();
}

/* ------------------------------------------------------------ study results */
/* ------------------------------------------------------------ manage volunteers and recordings */
function colManage() {
  const box = $("#col-manage"), vols = Object.values(COL.data.volunteers);
  const scored = Object.fromEntries((COL.study?.clips || []).map(c => [`${c.volunteer}/${c.clip}`, c.score]));
  const o = COL.data.options;
  if (!vols.length) { box.innerHTML = `<div class="empty-state small"><p>No volunteers yet.</p></div>`; return; }
  box.innerHTML = vols.map(v => {
    const cl = COL.data.clips.filter(c => c.volunteer === v.code);
    const armed = COL.confirm === `v:${v.code}`;
    return `<section class="mg-vol">
      <header><span class="swatch-dot" style="--sw:rgb(${SKIN_RGB[skinOf(v)].join(",")})"></span><b>${who(v)}</b>
        <span class="mono muted">${v.age_group} / ${v.sex} / TYPE ${ROMAN[skinOf(v)]} / ${cl.length} RECORDING${cl.length === 1 ? "" : "S"}</span>
        <span class="mg-actions">
          <button class="btn ghost small" type="button" data-edit="${v.code}">Edit</button>
          ${armed ? `<span class="warnline">Delete ${v.code} and all recordings?</span><button class="btn small danger-btn" type="button" data-delvol-yes="${v.code}">Delete</button><button class="btn ghost small" type="button" data-cancel>Keep</button>`
                  : `<button class="btn ghost small" type="button" data-delvol="${v.code}"><svg><use href="#i-trash"/></svg>Withdraw</button>`}
        </span></header>
      ${cl.length ? `<div class="table-scroll"><table class="data"><thead><tr><th>RECORDED</th><th>LIGHTING</th><th>MOTION</th><th>SECONDS</th><th>READINGS</th><th>TRACE VS WATCH</th><th>FILES</th><th></th></tr></thead><tbody>${
        cl.slice().reverse().map(c => { const key = `${v.code}/${c.clip}`, sc = scored[key] || {}, carm = COL.confirm === `c:${key}`;
          const sel = (k, vals) => `<select data-editclip="${key}" data-k="${k}" aria-label="${k}">${vals.map(x => `<option ${x === c.condition[k] ? "selected" : ""}>${x}</option>`).join("")}</select>`;
          return `<tr><td>${(c.recorded_at || "").replace("T", " ").slice(0, 16)}</td><td>${sel("lighting", o.lighting)}</td><td>${sel("motion", o.motion)}</td>
            <td>${fmt(c.seconds)}</td><td>${(c.readings || []).length}</td>
            <td class="${sc.mae && sc.mae.trace <= 5 ? "best" : ""}">${sc.mae ? `${fmt(sc.mae.trace, 1)} BPM` : "--"}</td>
            <td><button class="btn ghost small" type="button" data-open="${key}" data-what="folder">Open folder</button>${c.video ? ` <button class="btn ghost small" type="button" data-open="${key}" data-what="video">Play video</button>` : ""}</td>
            <td>${carm ? `<button class="btn small danger-btn" type="button" data-delclip-yes="${key}">Confirm delete</button><button class="btn ghost small" type="button" data-cancel>Keep</button>`
                       : `<button class="btn ghost small" type="button" data-delclip="${key}" title="Delete this recording"><svg><use href="#i-trash"/></svg></button>`}</td></tr>`; }).join("")}</tbody></table></div>`
        : `<p class="foot">No recordings yet.</p>`}
    </section>`;
  }).join("");
  const on = (sel, fn) => box.querySelectorAll(sel).forEach(b => b.addEventListener(b.tagName === "SELECT" ? "change" : "click", () => fn(b)));
  on("[data-edit]", b => { COL.form = { mode: "edit", v: COL.data.volunteers[b.dataset.edit] }; COL.formMsg = ""; colVolunteer(); $("#col-volunteer").scrollIntoView({ behavior: "smooth" }); });
  on("[data-delvol]", b => { COL.confirm = `v:${b.dataset.delvol}`; colManage(); });
  on("[data-delclip]", b => { COL.confirm = `c:${b.dataset.delclip}`; colManage(); });
  on("[data-cancel]", () => { COL.confirm = null; colManage(); });
  on("[data-delvol-yes]", async b => {
    await fetch(`/api/collect/volunteer/${encodeURIComponent(b.dataset.delvolYes)}`, { method: "DELETE" });
    COL.confirm = null; if (COL.selected === b.dataset.delvolYes) COL.selected = ""; colLoad();
  });
  on("[data-delclip-yes]", async b => {
    const [v, c] = b.dataset.delclipYes.split("/");
    await fetch(`/api/collect/clip/${encodeURIComponent(v)}/${encodeURIComponent(c)}`, { method: "DELETE" });
    COL.confirm = null; colLoad();
  });
  on("[data-open]", async b => {
    const [v, c] = b.dataset.open.split("/");
    const r = await fetch(`/api/collect/open/${encodeURIComponent(v)}/${encodeURIComponent(c)}?what=${b.dataset.what}`, { method: "POST" });
    if (!r.ok) b.textContent = "Not found";
  });
  on("[data-editclip]", async s => {
    const [v, c] = s.dataset.editclip.split("/");
    await fetch(`/api/collect/clip/${encodeURIComponent(v)}/${encodeURIComponent(c)}`, { method: "PATCH", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ condition: { [s.dataset.k]: s.value } }) });
    colLoad();
  });
}

/* ------------------------------------------------------------ live parts (4 Hz) */
function colDynamic() {
  const s = state, cam = s.running && s.source === "webcam", rec = s.rec && s.rec.active ? s.rec : null;
  const btns = $("#col-buttons");
  if (btns) {
    const key = [cam, !!rec, !!COL.selected, rec && rec.capture_done].join("|");
    if (COL.btnKey !== key) {
      COL.btnKey = key;
      btns.innerHTML = !cam
        ? `<button class="btn" type="button" id="col-cam"><svg><use href="#i-camera"/></svg>Start camera</button>`
        : rec ? `<button class="btn primary" type="button" id="col-stop"><svg><use href="#i-stop"/></svg>${rec.capture_done ? "Save recording" : "Stop and save"}</button><button class="btn ghost" type="button" id="col-discard">Discard</button>`
        : `<button class="btn primary" type="button" id="col-start" ${COL.selected ? "" : "disabled"}><svg><use href="#i-rec"/></svg>Start recording</button><button class="btn ghost" type="button" id="col-camoff"><svg><use href="#i-stop"/></svg>Stop camera</button>${COL.selected ? "" : `<span class="foot">Choose or register a volunteer first.</span>`}`;
      const b1 = $("#col-cam"); if (b1) b1.addEventListener("click", () => { send({ cmd: "start", source: "webcam" }); });
      const b0 = $("#col-camoff"); if (b0) b0.addEventListener("click", () => send({ cmd: "stop" }));
      const b2 = $("#col-start"); if (b2) b2.addEventListener("click", () =>
        send({ cmd: "rec_start", options: { volunteer: COL.selected, condition: { lighting: COL.lighting, motion: COL.motion }, duration: COL.duration, watch: COL.watch, keep_video: COL.keepVideo } }));
      const b3 = $("#col-stop"); if (b3) b3.addEventListener("click", () => send({ cmd: "rec_stop", save: true }));
      const b4 = $("#col-discard"); if (b4) b4.addEventListener("click", () => send({ cmd: "rec_stop", save: false }));
    }
  }
  setPill($("#col-rec-state"), rec ? (rec.capture_done ? "WAITING FOR LAST READING" : "RECORDING") : cam ? "CAMERA ON" : s.running ? "SIMULATOR RUNNING" : "CAMERA OFF",
    rec ? "coral" : cam ? "good" : s.running ? "warn" : "");
  const live = $("#col-live");
  if (!rec) {
    if (live.dataset.mode !== (cam ? "cam" : "idle")) {
      live.dataset.mode = cam ? "cam" : "idle";
      live.innerHTML = cam ? `<ul class="chips" id="col-checks"><li data-check="face"><i></i><span class="mono">FACE</span></li><li data-check="light"><i></i><span class="mono">LIGHT</span></li><li data-check="still"><i></i><span class="mono">STILL</span></li></ul>` : "";
    }
  } else if (live.dataset.mode !== "rec") {
    live.dataset.mode = "rec";
    live.innerHTML = `
      <div class="rec-bar"><span class="mono" id="col-time"></span><div class="bar"><i id="col-prog"></i></div><span class="mono" id="col-trace"></span></div>
      <form class="watch-entry" id="col-watch-form" autocomplete="off">
        <button class="btn primary" type="button" id="col-mark" title="Press the instant the watch shows its number (Space)"><svg><use href="#i-check"/></svg>Mark (Space)</button>
        <label for="col-bpm" class="label mono">SMARTWATCH READING</label>
        <input id="col-bpm" type="number" inputmode="numeric" min="30" max="220" placeholder="BPM" aria-describedby="col-prompt">
        <button class="btn" type="submit">Log</button>
        <span class="prompt mono" id="col-prompt" aria-live="polite"></span>
      </form>
      <ol class="slots mono" id="col-slots"></ol>`;
    const mark = () => send({ cmd: "rec_mark" });
    $("#col-mark").addEventListener("click", () => { mark(); $("#col-bpm").focus(); });
    // Space marks the moment even while the number box has focus (a number field ignores spaces anyway).
    $("#col-bpm").addEventListener("keydown", e => { if (e.key === " ") { e.preventDefault(); mark(); } });
    $("#col-watch-form").addEventListener("submit", e => {
      e.preventDefault();
      const v = +$("#col-bpm").value;
      if (v >= 30 && v <= 220) { send({ cmd: "rec_watch", bpm: v }); $("#col-bpm").value = ""; }
      $("#col-bpm").focus();
    });
    $("#col-bpm").focus();
  }
  if (rec) {
    $("#col-time").textContent = `${mmss(rec.elapsed)} / ${mmss(rec.duration)}`;
    $("#col-prog").style.width = `${Math.min(100, rec.elapsed / rec.duration * 100)}%`;
    $("#col-trace").textContent = haveBpm() ? `TRACE ${fmt(s.bpm)} BPM${s.confident ? "" : " (LOW CONFIDENCE)"}` : "TRACE COLLECTING";
    // Readings are free in time: the watch is restarted after each one, and Mark freezes the moment it locked.
    const got = rec.readings.length, p = $("#col-prompt");
    let msg, due = false;
    if (COL.markError && performance.now() - COL.markError.at < 4000) { msg = COL.markError.text; due = true; }
    else if (rec.mark != null) { due = true; msg = `MARKED AT ${mmss(rec.mark)}. TYPE THE NUMBER AND PRESS ENTER, THEN RESTART THE WATCH`; }
    else if (rec.elapsed < MIN_READ_AT && !rec.capture_done) msg = got === 0 && rec.elapsed < 3 ? "START THE WATCH NOW" : `WATCH MEASURING. READINGS COUNT FROM ${mmss(MIN_READ_AT)}`;
    else if (rec.capture_done) { due = true; msg = "CAPTURE FINISHED. MARK AND ENTER THE LAST READING IF THE WATCH IS SHOWING ONE, THEN SAVE"; }
    else msg = "PRESS MARK (SPACE) THE MOMENT THE WATCH SHOWS ITS NUMBER";
    p.textContent = msg; p.classList.toggle("due", due);
    const ol = $("#col-slots"), sig = rec.readings.map(r => `${r.t}:${r.bpm}`).join(",") + "|" + (rec.mark ?? "");
    if (ol.dataset.sig !== sig) {
      ol.dataset.sig = sig;
      ol.innerHTML = rec.readings.map(r => `<li class="got"><span>${mmss(r.t)}${r.marked ? "" : " *"}</span><b>${fmt(r.bpm)}</b></li>`).join("")
        + (rec.mark != null ? `<li class="due"><span>${mmss(rec.mark)}</span><b>--</b></li>` : "")
        + (got ? "" : `<li><span>READINGS</span><b>--</b></li>`);
    }
  }
  const checks = s.checks || {};
  $$("#col-checks li").forEach(li => li.classList.toggle("ok", !!checks[li.dataset.check]));
}

function colLast(r) {
  const box = $("#col-last");
  if (!r || r.discarded) { box.hidden = true; return; }
  const sc = r.score || {}, rows = sc.rows || [], v = COL.data?.volunteers[r.volunteer];
  box.hidden = false;
  box.innerHTML = `
    <header class="card-h"><span class="label mono">JUST RECORDED / ${v ? who(v) : r.volunteer} / ${esc(r.condition.motion.toUpperCase())} / ${esc(r.condition.lighting.toUpperCase())}</span>
      <span class="pill small ${r.completed ? "good" : "warn"}">${r.completed ? "COMPLETE" : "STOPPED EARLY"}</span></header>
    ${rows.length ? `<div class="table-scroll"><table class="data"><thead><tr><th>TIME</th><th>WATCH</th><th>TRACE</th><th>GREEN</th><th>CHROM</th><th>POS</th><th>CONFIDENT</th><th>SELECTED</th></tr></thead><tbody>${
      rows.map(x => { const d = dominantOf(x.weights);
        return `<tr><td>${mmss(x.t)}</td><td>${fmt(x.watch)}</td><td class="${Math.abs(x.trace - x.watch) <= 5 ? "best" : ""}">${fmt(x.trace, 1)}</td><td>${fmt(x.green, 1)}</td><td>${fmt(x.chrom, 1)}</td><td>${fmt(x.pos, 1)}</td><td>${x.confident ? "YES" : "NO"}</td><td>${MNAME[d]}</td></tr>`; }).join("")}</tbody></table></div>
      <p class="foot">TRACE within 5 BPM of the watch on ${pct(sc.within5?.trace)} of ${sc.n} readings. Face found on ${r.frames ? pct(r.face_frames / r.frames) : "--"} of frames.</p>`
    : `<p class="foot">No watch readings from 0:20 on, so nothing to score.</p>`}`;
}

window.onRecMessage = msg => {
  if (msg.type === "rec_ack" && msg.result && msg.result.mark_error) { COL.markError = { text: msg.result.mark_error, at: performance.now() }; return; }
  if (msg.type === "rec_ack" && msg.result && msg.result.error) { $("#col-live").innerHTML = `<p class="form-msg">${esc(msg.result.error)}</p>`; $("#col-live").dataset.mode = "err"; }
  if (msg.type === "rec_done") { if (msg.result && msg.result.clip) colSeenLast = msg.result.clip; colLast(msg.result); colLoad(); }
};

window.renderCollect = () => {
  if (!COL.built) { COL.built = true; colLoad(); }
  if (COL.data) colDynamic();
  // A recording that ended by its timeout arrives through the state.
  const last = state.rec && !state.rec.active ? state.rec.last : null;
  if (last && last.clip && last.clip !== colSeenLast) { colSeenLast = last.clip; colLast(last); colLoad(); }
};
