"""Experimental camera ballistocardiography for the live demonstration."""
from __future__ import annotations

from collections import deque

import cv2
import numpy as np
from scipy.interpolate import CubicSpline

from .preprocess import bandpass_fir
from .spectral import estimate_bpm, peak_frequency, spectral_snr, spectrum


class CameraBCG:
    """Estimate tiny vertical facial motion from tracked feature points.

    Feature displacement is extracted independently from the colour trace, but
    voluntary motion can still look cardiac. The reporting gate therefore uses
    a stable rPPG estimate as a frequency guide and publishes rBCG only as an
    experimental corroboration channel when mechanical evidence agrees.
    """

    def __init__(self):
        self.previous = None
        self.points = None
        self.samples = deque(maxlen=900)
        self.position = 0.0
        self.last_reset = -100.0
        self.estimates = deque(maxlen=5)

    def update(self, frame, box, t):
        gray = cv2.cvtColor(frame, cv2.COLOR_RGB2GRAY)
        if box is None:
            self.points = None
            self.samples.clear()
            self.estimates.clear()
            self.previous = gray
            return
        if self.points is None or len(self.points) < 12 or t - self.last_reset > 60:
            mask = np.zeros_like(gray)
            x, y, w, h = map(int, box)
            mask[max(0, y):min(gray.shape[0], y + h), max(0, x):min(gray.shape[1], x + w)] = 255
            self.points = cv2.goodFeaturesToTrack(gray, 70, .02, 7, mask=mask)
            self.samples.clear()
            self.estimates.clear()
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

    def result(self, reference_bpm: float | None = None):
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
        trace = (pulse[-180:] / (np.std(pulse) + 1e-12)).tolist()
        if reference_bpm is None or not 42 <= reference_bpm <= 180:
            self.estimates.clear()
            return {**out, "reason": "Waiting for a stable optical reference", "pulse": trace}

        # rBCG is much weaker than voluntary head motion. Search only near the
        # independently recovered optical rhythm, then require that local peak
        # to carry a meaningful fraction of the mechanical spectrum. This
        # rejects plausible-looking 50/80 BPM motion peaks instead of showing
        # them as measurements.
        freqs, power = spectrum(pulse, 30, pad_factor=8)
        global_est = estimate_bpm(pulse, 30, band=(.7, 3.0))
        ref_hz = reference_bpm / 60.0
        guided_band = (max(.7, ref_hz - .14), min(3.0, ref_hz + .14))
        candidate_hz = peak_frequency(freqs, power, guided_band)
        candidate_bpm = candidate_hz * 60.0
        quality = spectral_snr(freqs, power, candidate_hz, band=(.7, 3.0),
                               half_width_hz=.08, include_harmonic=False)

        def local_power(hz: float) -> float:
            m = np.abs(freqs - hz) <= .08
            return float(np.sum(power[m]))

        peak_ratio = local_power(candidate_hz) / max(local_power(global_est.freq_hz), 1e-12)
        agreement = abs(candidate_bpm - reference_bpm)
        prelim = (quality >= .32 and peak_ratio >= .30 and agreement <= 8.5
                  and np.std(pulse) > .015 and np.std(motion) < 2)
        if prelim and self.estimates:
            prelim = abs(candidate_bpm - float(np.median(self.estimates))) <= 6.0
        if prelim:
            self.estimates.append(candidate_bpm)
        else:
            self.estimates.clear()
        usable = prelim and len(self.estimates) >= 3
        result = {**out, "quality": round(quality, 3), "agreement_bpm": round(agreement, 1),
                  "peak_ratio": round(peak_ratio, 3), "usable": bool(usable), "pulse": trace,
                  "guided_by": round(reference_bpm, 1)}
        if usable:
            result.update({"bpm": round(float(np.median(self.estimates)), 1),
                           "reason": "Mechanical rhythm agrees with rPPG"})
        else:
            result["reason"] = "Mechanical evidence too weak or unstable"
        return result
