"""Experimental mechanical sensing. Synthetic acceptance is not human validation."""
from __future__ import annotations

import csv
import io
from collections import deque

import cv2
import numpy as np
from scipy.interpolate import CubicSpline

from .preprocess import bandpass_fir
from .spectral import estimate_bpm


class CameraBCG:
    """Track subpixel facial features without the face box's smoothing deadband.

    Median feature displacement suppresses some local expressions. Voluntary
    periodic motion can still mimic a pulse, so this remains experimental.
    """
    def __init__(self):
        self.previous = None
        self.points = None
        self.samples = deque(maxlen=900)
        self.position = 0.0
        self.last_reset = -100.0

    def update(self, frame, box, t):
        gray = cv2.cvtColor(frame, cv2.COLOR_RGB2GRAY)
        if box is None:
            self.points = None
            self.samples.clear()
            self.previous = gray
            return
        if self.points is None or len(self.points) < 12 or t - self.last_reset > 25:
            mask = np.zeros_like(gray)
            x, y, w, h = map(int, box)
            mask[max(0, y):min(gray.shape[0], y+h), max(0, x):min(gray.shape[1], x+w)] = 255
            self.points = cv2.goodFeaturesToTrack(gray, 70, .02, 7, mask=mask)
            self.samples.clear()
            self.position = 0.0
            self.last_reset = t
        else:
            pts, ok, _ = cv2.calcOpticalFlowPyrLK(self.previous, gray, self.points, None)
            if pts is not None:
                keep = ok.ravel().astype(bool)
                delta = pts[keep, 0] - self.points[keep, 0]
                if len(delta) >= 12 and np.max(np.abs(np.median(delta, axis=0))) < 3:
                    self.position += float(np.median(delta[:, 1]))
                    self.samples.append((t, self.position))
                    self.points = pts[keep]
                else:
                    self.points = None
                    self.samples.clear()
        self.previous = gray

    def result(self):
        out = {"usable": False, "experimental": True, "reason": "Gathering 12 s of steady feature tracks"}
        if len(self.samples) < 100:
            return out
        a = np.array(self.samples)
        a = a[a[:, 0] >= a[-1, 0] - 20]
        if a[-1, 0] - a[0, 0] < 12 or np.max(np.diff(a[:, 0])) > .2:
            return out
        t = np.arange(a[0, 0], a[-1, 0], 1 / 30)
        motion = CubicSpline(a[:, 0], a[:, 1])(t)
        pulse = bandpass_fir(motion, 30, .7, 3)
        est = estimate_bpm(pulse, 30)
        usable = est.quality >= .6 and np.std(pulse) > .015 and np.std(motion) < 2
        return {**out, "bpm": round(est.bpm, 1), "quality": round(est.quality, 3),
                "usable": bool(usable), "reason": "Experimental motion estimate" if usable else "Motion channel not reliable",
                "pulse": (pulse[-180:] / (np.std(pulse) + 1e-12)).tolist()}


def analyse_phone_csv(text: str) -> dict:
    """Accept timestamped SI acceleration. Analyse a mechanical envelope and respiration separately."""
    rows = csv.DictReader(io.StringIO(text))
    required = {"t", "ax", "ay", "az"}
    if not required.issubset(rows.fieldnames or []):
        raise ValueError("CSV needs t,ax,ay,az columns. Time in seconds; acceleration in m/s^2.")
    try:
        data = np.array([[float(r[k]) for k in ("t", "ax", "ay", "az")] for r in rows])
    except (ValueError, TypeError, KeyError) as exc:
        raise ValueError("Every sample must contain numeric t,ax,ay,az values.") from exc
    if len(data) < 100 or not np.isfinite(data).all():
        raise ValueError("Provide at least 100 finite samples.")
    dt = np.diff(data[:, 0])
    if np.any(dt <= 0):
        raise ValueError("Timestamps must be strictly increasing.")
    fs = 1 / np.median(dt)
    duration = data[-1, 0] - data[0, 0]
    if not 50 <= fs <= 500 or not 20 <= duration <= 300 or max(dt) > .1:
        raise ValueError("Record 20 to 300 seconds at 50 to 500 Hz, without gaps over 0.1 s.")
    t = np.arange(data[0, 0], data[-1, 0], 1 / fs)
    axes = CubicSpline(data[:, 0], data[:, 1:])(t)
    candidates = []
    for axis in axes.T:
        vibration = bandpass_fir(axis, fs, 5, min(20, fs * .4))
        envelope = bandpass_fir(vibration ** 2, fs, .7, 3, numtaps=501)
        est = estimate_bpm(envelope, fs)
        candidates.append((est.quality, est, envelope))
    quality, est, pulse = max(candidates, key=lambda c: c[0])
    # Respiration is a separate low-frequency branch, not raw SCG cardiac rate.
    axis = axes[:, int(np.argmax(np.std(axes, axis=0)))]
    resp = bandpass_fir(axis, fs, .1, .5, numtaps=int(fs * 10) | 1)
    f = np.fft.rfftfreq(len(resp), 1/fs)
    p = np.abs(np.fft.rfft((resp - resp.mean()) * np.hanning(len(resp)))) ** 2
    mask = (f >= .1) & (f <= .5)
    respiration = float(f[mask][np.argmax(p[mask])] * 60)
    return {"experimental": True, "seconds": round(duration, 1), "fs": round(fs, 1),
            "bpm": round(est.bpm, 1), "quality": round(quality, 3),
            "usable": bool(quality >= .6 and np.std(pulse) > 1e-9),
            "respiration_bpm": round(respiration, 1) if duration >= 40 and np.std(resp) > 1e-8 else None,
            "pulse": (pulse[::max(1, len(pulse)//300)] / (np.std(pulse)+1e-12)).tolist(),
            "note": "Research estimate from a mechanical envelope. Not ECG or a diagnostic result; movement can dominate."}
