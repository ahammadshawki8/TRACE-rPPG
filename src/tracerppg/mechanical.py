"""Experimental camera ballistocardiography for the live demonstration."""
from __future__ import annotations

from collections import deque

import cv2
import numpy as np
from scipy.interpolate import CubicSpline

from .preprocess import bandpass_fir
from .spectral import estimate_bpm


class CameraBCG:
    """Estimate tiny vertical facial motion from tracked feature points.

    The feature displacement is independent of the colour trace used by rPPG,
    but voluntary motion can still look cardiac. It is therefore shown as an
    experimental corroboration channel and is allowed to veto game feedback
    when it disagrees strongly with the optical estimate.
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
            mask[max(0, y):min(gray.shape[0], y + h), max(0, x):min(gray.shape[1], x + w)] = 255
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
        out = {"usable": False, "experimental": True,
               "reason": "Gathering 12 s of steady feature tracks"}
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
                "usable": bool(usable),
                "reason": "Experimental motion estimate" if usable else "Motion channel not reliable",
                "pulse": (pulse[-180:] / (np.std(pulse) + 1e-12)).tolist()}
