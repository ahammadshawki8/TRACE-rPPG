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
from .fusion import artifact_reference, band_limited_pulses, fuse, p_correct
from .roi import FaceTracker, skin_mean
from .simulate import LiveSimulator

FS = 30.0
WINDOW_S = 20.0
METHODS = ("green", "chrom", "pos")


def frozen_params() -> dict:
    p = Path(__file__).resolve().parents[2] / "results" / "fusion_params.json"
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
    """One read-out, as the engine makes it, from the `win` seconds before `t_end`."""
    m = (t > t_end - win) & (t <= t_end)
    if m.sum() < FS * win * 0.8:
        return None
    cols = np.column_stack([resample_uniform(t[m], rgb[m, c], FS)[1] for c in range(3)])
    pulses = band_limited_pulses(cols, FS)
    fr = fuse(pulses, FS, float(params["gamma"]), float(params["confidence"]),
              artifact=artifact_reference(cols, FS), mask_k=float(params.get("mask_k", 4.0)))
    return {
        "bpm": fr.bpm, "quality": fr.quality, "confident": bool(fr.confident), "p_correct": p_correct(fr.quality, params),
        "weights": dict(fr.weights),
        "methods": {k: {"bpm": v.bpm, "quality": v.quality, "artifact": v.artifact} for k, v in fr.per_method.items()},
        "green_amp": float(np.std(pulses["green"])),
    }


def evaluate(sim: LiveSimulator, seconds: float, params: dict | None = None, hop: float = 2.5,
             schedule: dict[float, dict] | None = None, first: float = WINDOW_S) -> list[dict]:
    """Every read-out from `first` seconds to the end, each paired with the
    true mean rate over the same 20 s window."""
    params = params or frozen_params()
    t, rgb = stream(sim, seconds, schedule)
    rows = []
    for t_end in np.arange(first, seconds + 1e-9, hop):
        r = analyse(t, rgb, t_end, params)
        if r is None:
            continue
        r["t"] = float(t_end)
        r["truth"] = sim.true_bpm(t_end, WINDOW_S)
        rows.append(r)
    return rows
