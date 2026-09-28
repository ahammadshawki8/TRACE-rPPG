"""Volunteer data collection: recording, storage, and scoring against a smartwatch.

What is stored (data/own/, never committed):
    volunteers.json            code -> name (optional), age group, sex, skin type, consent record
    <code>/<clip>/trace.npz    per frame: time, mean skin RGB, skin pixel count, face box
    <code>/<clip>/meta.json    condition, camera, duration, smartwatch readings with times
    <code>/<clip>/video.mkv    only if the volunteer agreed to keep video

The trace is all the pipeline needs to re-run every method and every fusion
variant later, so by default no face video is kept. A name is optional and
stays in volunteers.json on this computer: it is never part of an export,
and every analysis refers to the code.

Scoring (rule fixed on 2026-09-28, the same for every clip and method): the
smartwatch measures for about 20 s and then locks its value. Its reading is
compared with the median of five read-outs whose 20 s windows end every 2.5 s
from 5 s before to 5 s after the moment the watch locked. That moment is the
Mark time when the presenter pressed Mark, or 5 s before the reading was
typed for older clips recorded without Mark (typing delay). The median
absorbs a momentary glitch without letting the scorer pick the read-out that
happens to match the watch. Read-outs need a full 20 s window.

Typing delay: the watch locks its number a few seconds before the presenter
has typed it. The Mark button (Space) freezes the time the instant the watch
shows its number; the reading typed afterwards is stamped with that mark, so
typing speed no longer shifts the comparison window. Readings are accepted
at any time from 20 s on (TRACE needs a full 20 s window).
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import threading
import time
from datetime import datetime
from pathlib import Path

import numpy as np

from tracerppg.simeval import WINDOW_S, analyse, frozen_params

ROOT = Path(__file__).resolve().parents[1]
import os
# TRACE_COLLECT_DIR lets a test run use a scratch folder instead of the real data/own.
DATA = Path(os.environ.get("TRACE_COLLECT_DIR", str(ROOT / "data" / "own")))
METHODS = ("green", "chrom", "pos")
TYPING_LAG_S = 5.0     # clips without Mark: the watch locked about this long before the number was typed
MEDIAN_HALF_S = 5.0    # read-outs from 5 s before to 5 s after the lock ...
MEDIAN_STEP_S = 2.5    # ... every 2.5 s: five read-outs, and their median is compared
AGE_GROUPS = ("under 18", "18-29", "30-44", "45-59", "60+")
LIGHTING = ("room light", "bright lamp", "dim room", "daylight window", "screen lit")
MOTION = ("still", "talking", "head movement", "natural")
_lock = threading.Lock()


def _slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


# ------------------------------------------------------------------ volunteers
def volunteers() -> dict:
    p = DATA / "volunteers.json"
    return json.loads(p.read_text()) if p.exists() else {}


def _save_volunteers(v: dict) -> None:
    DATA.mkdir(parents=True, exist_ok=True)
    (DATA / "volunteers.json").write_text(json.dumps(v, indent=1))


def upsert_volunteer(body: dict) -> dict:
    """Create (no code given) or update a volunteer. Refuses without consent."""
    if not body.get("consent"):
        raise ValueError("Consent is required before anything is stored.")
    age = body.get("age_group")
    if age not in AGE_GROUPS:
        raise ValueError("Choose an age group.")
    if age == "under 18" and not body.get("guardian_consent"):
        raise ValueError("A parent or guardian must consent for a volunteer under 18.")
    fz = int(body.get("fitzpatrick_self") or 0)
    if not 1 <= fz <= 6:
        raise ValueError("Choose a skin type from I to VI.")
    with _lock:
        v = volunteers()
        code = body.get("code") or f"V{len(v) + 1:02d}"
        while not body.get("code") and code in v:
            code = f"V{int(code[1:]) + 1:02d}"
        rated = body.get("fitzpatrick_rated")
        v[code] = {
            "code": code, "name": str(body.get("name") or "").strip()[:60], "age_group": age,
            "sex": body.get("sex") or "not given",
            "fitzpatrick_self": fz, "fitzpatrick_rated": int(rated) if rated else None,
            "consent": True, "guardian_consent": bool(body.get("guardian_consent")),
            "consent_at": v.get(code, {}).get("consent_at") or datetime.now().isoformat(timespec="seconds"),
            "notes": str(body.get("notes") or "")[:300],
        }
        _save_volunteers(v)
    return v[code]


def _audit(action: str) -> None:
    """Every deletion is written down, so a missing recording can be explained."""
    DATA.mkdir(parents=True, exist_ok=True)
    with open(DATA / "audit.log", "a", encoding="utf-8") as f:
        f.write(f"{datetime.now().isoformat(timespec='seconds')} {action}" + chr(10))


def delete_volunteer(code: str) -> None:
    """Withdrawal: removes the volunteer and every recording of theirs."""
    with _lock:
        v = volunteers()
        v.pop(code, None)
        _save_volunteers(v)
        d = DATA / code
        if d.is_dir() and d.parent == DATA:
            shutil.rmtree(d)
        _audit(f"withdrew volunteer {code} and all their recordings")


def delete_clip(code: str, clip: str) -> None:
    d = DATA / code / clip
    if d.is_dir() and d.parent.parent == DATA:
        shutil.rmtree(d)
        _audit(f"deleted recording {code}/{clip}")


def _clip_dir(code: str, clip: str) -> Path:
    d = (DATA / code / clip).resolve()
    if d.parent.parent != DATA.resolve() or not (d / "meta.json").exists():
        raise ValueError("No such recording.")
    return d


def update_clip(code: str, clip: str, condition: dict) -> dict:
    """Correct a recording's lighting or motion label."""
    d = _clip_dir(code, clip)
    meta = json.loads((d / "meta.json").read_text())
    for k, allowed in (("lighting", LIGHTING), ("motion", MOTION)):
        if condition.get(k) in allowed:
            meta["condition"][k] = condition[k]
    (d / "meta.json").write_text(json.dumps(meta, indent=1))
    return meta


def open_in_explorer(code: str, clip: str, what: str = "folder") -> None:
    """Show a recording on this PC: its folder in Explorer, or its video in
    the default player. The server only ever runs locally, for the presenter."""
    import os
    d = _clip_dir(code, clip)
    video = d / "video.mkv"
    if what == "video":
        if not video.exists():
            raise ValueError("This recording has no video.")
        os.startfile(str(video))  # type: ignore[attr-defined]  (Windows)
    else:
        subprocess.Popen(["explorer", "/select,", str(video if video.exists() else d / "trace.npz")])


def clips() -> list[dict]:
    out = []
    for m in sorted(DATA.glob("*/*/meta.json")):
        meta = json.loads(m.read_text())
        meta["clip"] = m.parent.name
        out.append(meta)
    return out


# ------------------------------------------------------------------ recording
class Recorder:
    """Collects what one recording needs, frame by frame, from the engine loop."""

    def __init__(self, volunteer: str, condition: dict, duration: float, watch: str, keep_video: bool,
                 camera: dict | None):
        v = volunteers()
        if volunteer not in v:
            raise ValueError("Register the volunteer first.")
        self.volunteer, self.duration = volunteer, float(min(max(duration, 30.0), 300.0))
        self.condition = {"lighting": condition.get("lighting", "room light"), "motion": condition.get("motion", "still")}
        self.watch, self.camera = str(watch or "")[:80], camera or {}
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        self.clip = f"{_slug(self.condition['lighting'])}_{_slug(self.condition['motion'])}_{stamp}"
        self.dir = DATA / volunteer / self.clip
        self.dir.mkdir(parents=True, exist_ok=True)
        self.t0: float | None = None
        self.frozen_at: float | None = None  # wall time when capture reached the planned length
        self.t, self.rgb, self.npx, self.box, self.readings = [], [], [], [], []
        self.last_t = 0.0
        self.pending_mark: float | None = None  # capture time frozen by the Mark button
        self.video = None
        if keep_video:
            # Near-lossless 4:4:4, so the colour the pulse lives in is not subsampled.
            self.video = subprocess.Popen(
                ["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", "640x480", "-r", "30",
                 "-i", "-", "-c:v", "libx264", "-preset", "ultrafast", "-crf", "8", "-pix_fmt", "yuv444p",
                 str(self.dir / "video.mkv")], stdin=subprocess.PIPE)

    @property
    def elapsed(self) -> float:
        return self.last_t

    @property
    def capture_done(self) -> bool:
        return self.frozen_at is not None

    def add(self, frame: np.ndarray, t: float, mean, npx: int, box) -> None:
        if self.frozen_at is not None:
            return  # capture is over; waiting for the last watch reading
        if self.t0 is not None and t - self.t0 >= self.duration:
            self.frozen_at = time.monotonic()
            return
        if self.t0 is None:
            self.t0 = t
        rt = t - self.t0
        self.last_t = rt
        self.t.append(rt)
        self.rgb.append(mean if mean is not None else (np.nan, np.nan, np.nan))
        self.npx.append(npx)
        self.box.append(box if box is not None else (np.nan,) * 4)
        if self.video is not None and frame.shape[:2] == (480, 640):
            try:
                self.video.stdin.write(np.ascontiguousarray(frame).tobytes())
            except (BrokenPipeError, OSError):
                self.video = None

    def mark(self) -> dict:
        """The watch has just shown its number: remember this moment."""
        if self.last_t < WINDOW_S:
            return {"mark_error": f"TOO EARLY: TRACE NEEDS {WINDOW_S:.0f} S OF VIDEO. MARK AGAIN WHEN THE WATCH SHOWS ITS NEXT NUMBER."}
        self.pending_mark = round(self.last_t, 2)
        return {"marked": self.pending_mark}

    def watch_reading(self, bpm: float) -> dict:
        marked = self.pending_mark is not None
        r = {"t": self.pending_mark if marked else round(self.last_t, 2), "bpm": float(bpm), "marked": marked,
             "entered_t": round(self.last_t, 2)}
        self.pending_mark = None
        self.readings.append(r)
        return r

    def finish(self, completed: bool) -> dict:
        if self.video is not None:
            self.video.stdin.close()
            self.video.wait()
        np.savez_compressed(self.dir / "trace.npz", t=np.array(self.t), rgb=np.array(self.rgb, dtype=float),
                            npx=np.array(self.npx), box=np.array(self.box, dtype=float))
        v = volunteers().get(self.volunteer, {})
        meta = {
            "volunteer": self.volunteer, "age_group": v.get("age_group"),
            "fitzpatrick": v.get("fitzpatrick_rated") or v.get("fitzpatrick_self"),
            "condition": self.condition, "seconds": round(self.last_t, 2), "planned_seconds": self.duration,
            "completed": completed, "frames": len(self.t),
            "face_frames": int(np.sum(np.array(self.npx) > 200)) if self.npx else 0,
            "watch": self.watch, "readings": self.readings, "camera": self.camera,
            "video": (self.dir / "video.mkv").exists(), "recorded_at": datetime.now().isoformat(timespec="seconds"),
        }
        (self.dir / "meta.json").write_text(json.dumps(meta, indent=1))
        return {"clip": self.clip, **meta, "score": score_clip(self.dir)}


# ------------------------------------------------------------------ scoring
def score_clip(folder: Path, params: dict | None = None) -> dict:
    """Every smartwatch reading at T >= 20 s against the app's read-out at T."""
    params = params or frozen_params()
    meta = json.loads((folder / "meta.json").read_text())
    with np.load(folder / "trace.npz") as z:  # closed at once, or Windows cannot delete it on withdrawal
        t, rgb, npx = z["t"], z["rgb"], z["npx"]
    ok = np.all(np.isfinite(rgb), axis=1) & (npx > 200)
    t, rgb = t[ok], rgb[ok]
    rows = []
    for r in meta.get("readings", []):
        locked = r["t"] - (0.0 if r.get("marked") else TYPING_LAG_S)
        ends = [e for e in np.arange(locked - MEDIAN_HALF_S, locked + MEDIAN_HALF_S + 1e-9, MEDIAN_STEP_S) if e >= WINDOW_S]
        outs = [a for a in (analyse(t, rgb, e, params) for e in ends) if a is not None]
        if not outs:
            continue
        med = lambda xs: float(np.median(xs))
        rows.append({"t": r["t"], "locked_t": round(float(locked), 2), "n_readouts": len(outs), "watch": r["bpm"],
                     "trace": med([a["bpm"] for a in outs]),
                     "confident": sum(a["confident"] for a in outs) > len(outs) / 2,
                     "p_correct": med([a["p_correct"] for a in outs if a["p_correct"] is not None] or [np.nan]),
                     "weights": {m: float(np.mean([a["weights"][m] for a in outs])) for m in METHODS},
                     **{m: med([a["methods"][m]["bpm"] for a in outs]) for m in METHODS}})
    return {"n": len(rows), "rows": rows, **_errors(rows)}


def _errors(rows: list[dict]) -> dict:
    if not rows:
        return {"mae": None, "within5": None, "mean_weights": None}
    e = {m: np.array([abs(r[m] - r["watch"]) for r in rows]) for m in (*METHODS, "trace")}
    conf = np.array([r["confident"] for r in rows])
    return {
        "mae": {m: float(v.mean()) for m, v in e.items()},
        "within5": {m: float((v <= 5).mean()) for m, v in e.items()},
        "mean_weights": {m: float(np.mean([r["weights"][m] for r in rows])) for m in METHODS},
        "confident": float(conf.mean()),
        "mae_confident": float(e["trace"][conf].mean()) if conf.any() else None,
    }


_study_cache: tuple | None = None


def _study_key() -> tuple:
    """Changes whenever a recording, a volunteer record or the frozen TRACE parameters change."""
    files = [*DATA.glob("*/*/meta.json"), *DATA.glob("*/*/trace.npz"), DATA / "volunteers.json",
             *(ROOT / "results").glob("fusion_params*.json")]
    return tuple(sorted((str(f), f.stat().st_mtime_ns) for f in files if f.exists()))


def study() -> dict:
    """Everything recorded so far, scored and grouped. Scoring every clip takes
    a few seconds, so the result is kept until a file it depends on changes."""
    global _study_cache
    key = _study_key()
    if _study_cache is not None and _study_cache[0] == key:
        return _study_cache[1]
    out = _study()
    _study_cache = (key, out)
    return out


def _study() -> dict:
    per_clip, all_rows = [], []
    for meta in clips():
        folder = DATA / meta["volunteer"] / meta["clip"]
        if not (folder / "trace.npz").exists():
            continue
        s = score_clip(folder)
        per_clip.append({k: meta[k] for k in ("volunteer", "clip", "age_group", "fitzpatrick", "condition", "seconds",
                                              "completed", "watch", "video", "recorded_at")} | {"score": {k: v for k, v in s.items() if k != "rows"}})
        for r in s["rows"]:
            all_rows.append({**r, "volunteer": meta["volunteer"], "fitzpatrick": meta["fitzpatrick"],
                             "age_group": meta["age_group"], **meta["condition"]})

    def group(key):
        out = {}
        for val in sorted({str(r[key]) for r in all_rows}):
            rs = [r for r in all_rows if str(r[key]) == val]
            out[val] = {"n": len(rs), "volunteers": len({r["volunteer"] for r in rs}), **_errors(rs)}
        return out

    return {"volunteers": len(volunteers()), "clips": per_clip, "n_readings": len(all_rows),
            "n_volunteers_scored": len({r["volunteer"] for r in all_rows}),
            "overall": _errors(all_rows), "by_motion": group("motion"), "by_lighting": group("lighting"),
            "by_skin": group("fitzpatrick"), "by_age": group("age_group"),
            "by_volunteer": group("volunteer"), "rows": all_rows}
