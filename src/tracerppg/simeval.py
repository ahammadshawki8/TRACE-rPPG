"""Run the live app's analysis on a simulated volunteer, offline.

The demo app (app/engine.py) analyses the last 20 s of skin colour every
half second. This module does the same thing without a clock, so the
acceptance checks and the scenario sweep measure exactly what the app would
show: same face tracker, same skin average, same uniform resampling, same
three methods, same artifact reference, same frozen TRACE parameters.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from .datasets import resample_uniform
from .fusion import artifact_reference, band_limited_pulses, fuse, fuse_kwargs, p_correct, weights_from_quality
from .roi import FaceTracker, skin_mean
from .simulate import LiveSimulator

FS = 30.0
WINDOW_S = 20.0
METHODS = ("green", "chrom", "pos")


def frozen_params(version: int | None = None) -> dict:
    """The fusion parameters in force: the newest frozen file (v5, v4, then v3,
    per-window selection), else v2. Pass version=2 to 5 for that version."""
    res = Path(__file__).resolve().parents[2] / "results"
    for v in (5, 4, 3):
        if version in (None, v) and (res / f"fusion_params_v{v}.json").exists():
            return json.loads((res / f"fusion_params_v{v}.json").read_text())
    if version not in (None, 2):
        raise FileNotFoundError(f"results/fusion_params_v{version}.json does not exist")
    p = res / "fusion_params.json"
    return json.loads(p.read_text()) if p.exists() else {"gamma": 1.0, "mask_k": 4.0, "confidence": 0.24}


def stream(sim: LiveSimulator, seconds: float, schedule: dict[float, dict] | None = None):
    """Render `seconds` of video and return frame times and mean skin RGB.

    `schedule` maps a time in seconds to settings applied at that moment,
    to test what happens when a presenter changes something mid-run.
    """
    tracker, ts, rgb = FaceTracker(), [], []
    pending = sorted((schedule or {}).items())
    n = int(round(seconds * sim.fps))
    for _ in range(n):
        while pending and pending[0][0] <= sim.i / sim.fps:
            sim.set(**pending.pop(0)[1])
        frame, t = sim.next_frame()
        box, _ = tracker.update(frame)
        if box is None:
            continue
        mean, npx = skin_mean(frame, box)
        if npx > 200:
            ts.append(t)
            rgb.append(mean)
    return np.asarray(ts), np.asarray(rgb)


def analyse(t: np.ndarray, rgb: np.ndarray, t_end: float, params: dict, win: float = WINDOW_S) -> dict | None:
    """One read-out, as the engine makes it, from the `win` seconds before `t_end`.

    v4: when the 20 s read-out's quality is below `long_quality` and the
    recording already holds `long_window_s` seconds, the read-out is redone
    over that longer window. A weak pulse (darker skin, dim light) gains from
    more beats, and a longer window resolves rhythms more finely (1/T). The
    longer read-out is used only if its quality is higher."""
    r = _analyse(t, rgb, t_end, params, win)
    lq, lw = float(params.get("long_quality", 0.0)), float(params.get("long_window_s", 0.0))
    if r is not None and lq and lw > win and r["quality"] < lq and t_end - lw >= t[0] - 0.05:
        r2 = _analyse(t, rgb, t_end, params, lw)
        if r2 is not None and r2["quality"] > r["quality"]:
            # Only TRACE's read-out moves to the longer window. The single
            # methods stay on the standard 20 s window, so the green, CHROM and
            # POS baselines are the same whichever TRACE version is in force.
            r2["window_s"] = lw
            r2["methods_long"], r2["methods"] = r2["methods"], r["methods"]
            return r2
    return r


def consistency_flags(readouts: list[tuple[float, float, bool]], cons: dict | None) -> dict[float, tuple[float, bool]]:
    """The live consistency check along one recording, backwards only.

    `readouts` are (end time, TRACE bpm, confident) in time order. A read-out
    further than cons["tol_bpm"] from the median of TRACE's own read-outs over
    the previous cons["history_s"] seconds (at least three of them) is a glitch:
    in "flag" mode it keeps its BPM but loses its confidence, in "hold" mode it
    reports that median instead. app/engine.py applies the same rule live.
    """
    out = {}
    for i, (e, b, c) in enumerate(readouts):
        prev = [bb for ee, bb, _ in readouts[:i] if e - cons["history_s"] <= ee < e] if cons else []
        if cons and cons.get("tol_bpm") and len(prev) >= 3 and abs(b - float(np.median(prev))) > cons["tol_bpm"]:
            out[e] = (float(np.median(prev)) if cons.get("mode") == "hold" else b, False)
        else:
            out[e] = (b, c)
    return out


def _analyse(t: np.ndarray, rgb: np.ndarray, t_end: float, params: dict, win: float) -> dict | None:
    m = (t > t_end - win) & (t <= t_end)
    # Judge coverage by time, not by frame count: real webcams often deliver
    # fewer than 30 fps (one delivered 20.7), and the signal is resampled onto
    # a uniform 30 Hz grid from its real timestamps anyway. Require the window
    # to be spanned, with no gap long enough to hide a heartbeat.
    tw = t[m]
    if len(tw) < 10 * win or tw[-1] - tw[0] < 0.9 * win or np.max(np.diff(tw)) > 0.25:
        return None
    cols = np.column_stack([resample_uniform(t[m], rgb[m, c], FS)[1] for c in range(3)])
    pulses = band_limited_pulses(cols, FS)
    fr = fuse(pulses, FS, float(params["gamma"]), float(params["confidence"]),
              artifact=artifact_reference(cols, FS), **fuse_kwargs(params))
    return {
        "bpm": fr.bpm, "quality": fr.quality, "confident": bool(fr.confident), "p_correct": p_correct(fr.quality, params),
        "weights": dict(fr.weights),
        "scores": weights_from_quality({k: v.quality for k, v in fr.per_method.items()}, 1.0),
        "methods": {k: {"bpm": v.bpm, "quality": v.quality, "artifact": v.artifact} for k, v in fr.per_method.items()},
        "green_amp": float(np.std(pulses["green"])),
    }


def evaluate(sim: LiveSimulator, seconds: float, params: dict | None = None, hop: float = 2.5,
             schedule: dict[float, dict] | None = None, first: float = WINDOW_S) -> list[dict]:
    """Every read-out from `first` seconds to the end, each paired with the
    true mean rate over the same 20 s window."""
    t, rgb = stream(sim, seconds, schedule)
    return readouts(t, rgb, sim, seconds, params or frozen_params(), hop, first)


def readouts(t: np.ndarray, rgb: np.ndarray, sim: LiveSimulator, seconds: float, params: dict,
             hop: float = 2.5, first: float = WINDOW_S) -> list[dict]:
    """Read-outs from an already streamed trace (see `evaluate`)."""
    rows = []
    for t_end in np.arange(first, seconds + 1e-9, hop):
        r = analyse(t, rgb, t_end, params)
        if r is None:
            continue
        r["t"] = float(t_end)
        r["truth"] = sim.true_bpm(t_end, WINDOW_S)
        rows.append(r)
    return rows
