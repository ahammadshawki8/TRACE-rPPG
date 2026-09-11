"""Heart-rate variability: the second Fourier transform. Tier T9.

The first transform turns skin brightness into a heart rate. This module
applies a second, independent transform to a different signal: the gaps
between beats. That series is unevenly sampled (one value per beat), so it
is resampled onto a uniform 4 Hz grid before its spectrum is taken
(invariant 11); the DFT assumes uniform spacing.

Bands follow the Task Force of ESC/NASPE (1996):
    LF 0.04 to 0.15 Hz   mixed autonomic activity, baroreflex
    HF 0.15 to 0.40 Hz   parasympathetic, respiratory sinus arrhythmia

LF starts at 0.04 Hz, a 25 s period, so LF/HF needs at least two minutes of
data (five is the standard). Everything here is a wellness indicator and
never a diagnosis.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .preprocess import bandpass_fir, default_numtaps
from .spectral import estimate_bpm

LF_BAND = (0.04, 0.15)
HF_BAND = (0.15, 0.40)
RR_FS = 4.0
MIN_HRV_SECONDS = 120.0
# The waveform used for beat timing. Choosing by spectral quality picked the
# green channel (fooled by motion) on half the subjects in step7; POS found
# 79 percent of beats against 50 percent.
HRV_METHOD = "pos"

DISCLAIMER = "Research and wellness indicator only, not a medical diagnosis."


def adaptive_band(f0_hz: float, half_width: float = 0.6) -> tuple[float, float]:
    """A band centred on the heart rate, wide enough to keep the HRV
    sidebands (a rhythm modulated at 0.1 and 0.25 Hz puts energy at f0 plus
    and minus those frequencies) but narrow enough to drop the harmonics,
    so each beat becomes one clean, well-timed peak."""
    return max(0.5, f0_hz - half_width), f0_hz + half_width


def detect_beats(pulse: np.ndarray, fs: float, bpm_hint: float | None = None) -> np.ndarray:
    """Beat times in seconds, in two stages.

    Find: a narrow band around the heart rate turns each beat into one clean
    peak, so beats are found reliably (a refractory period of 60 percent of
    the expected interval stops a dicrotic bump counting twice).

    Time: the narrow-band peak sits at the fundamental's phase, not at the
    systolic peak (measured: 41 ms RMS error, more than a frame). So each
    beat is re-timed on the wideband waveform (0.5 to 6 Hz, harmonics kept),
    as the maximum within a third of an interval of the found peak, refined
    between samples by a parabola. At 30 fps one sample is 33 ms, larger
    than the RR changes HRV measures, so sub-sample timing is essential.
    """
    x = np.asarray(pulse, float) - float(np.mean(pulse))
    if bpm_hint is None:
        bpm_hint = estimate_bpm(x, fs).bpm
    taps = min(default_numtaps(fs), 2 * (len(x) // 2) - 1)
    lo, hi = adaptive_band(bpm_hint / 60.0)
    narrow = bandpass_fir(x, fs, lo, hi, numtaps=taps)
    wide = bandpass_fir(x, fs, 0.5, min(6.0, 0.45 * fs), numtaps=taps)
    period = fs * 60.0 / bpm_hint
    refractory = int(0.6 * period)
    thresh = 0.2 * np.std(narrow)

    cand = np.flatnonzero((narrow[1:-1] > narrow[:-2]) & (narrow[1:-1] >= narrow[2:]) & (narrow[1:-1] > thresh)) + 1
    peaks: list[int] = []
    for i in cand:
        if peaks and i - peaks[-1] < refractory:
            if narrow[i] > narrow[peaks[-1]]:
                peaks[-1] = i
            continue
        peaks.append(int(i))

    half = max(1, int(period / 3))
    times = []
    for i in peaks:
        a0, a1 = max(1, i - half), min(len(wide) - 1, i + half + 1)
        j = a0 + int(np.argmax(wide[a0:a1]))
        if 0 < j < len(wide) - 1:
            a, b, c = wide[j - 1], wide[j], wide[j + 1]
            d = a - 2 * b + c
            delta = 0.5 * (a - c) / d if abs(d) > 1e-12 else 0.0
            times.append((j + float(np.clip(delta, -0.5, 0.5))) / fs)
    return np.unique(np.round(np.array(times), 6))


def clean_rr(beat_times: np.ndarray, tol: float = 0.20) -> tuple[np.ndarray, np.ndarray]:
    """(interval mid-times, RR in s) with ectopic or missed beats removed.

    An interval more than 20 percent away from the local median is dropped
    (the classic Malik rule), rather than letting one missed beat double an
    interval and dominate every statistic.
    """
    rr = np.diff(beat_times)
    mid = beat_times[1:]
    if len(rr) < 5:
        return mid, rr
    med = np.array([np.median(rr[max(0, i - 5) : i + 6]) for i in range(len(rr))])
    keep = np.abs(rr - med) <= tol * med
    return mid[keep], rr[keep]


@dataclass
class HRV:
    mean_hr: float
    sdnn_ms: float
    rmssd_ms: float
    pnn50: float
    lf_ms2: float | None
    hf_ms2: float | None
    lf_hf: float | None
    resp_hz: float | None
    n_beats: int
    duration_s: float
    valid_frequency: bool
    freqs: np.ndarray | None = None
    psd: np.ndarray | None = None

    def indicator(self) -> str:
        """Plain-language read-out with the caveat attached."""
        if not self.valid_frequency or self.lf_hf is None:
            return (f"Heart rate {self.mean_hr:.0f} BPM. Record at least {MIN_HRV_SECONDS / 60:.0f} minutes "
                    f"for LF/HF. {DISCLAIMER}")
        if self.lf_hf > 2.0:
            state = "elevated, consistent with an alert or stressed state"
        elif self.lf_hf < 0.5:
            state = "low, consistent with a relaxed, parasympathetic state"
        else:
            state = "balanced"
        return f"Heart rate {self.mean_hr:.0f} BPM. LF/HF {self.lf_hf:.2f} ({state}). {DISCLAIMER}"


def time_domain(rr_s: np.ndarray) -> tuple[float, float, float, float]:
    """Mean HR, SDNN, RMSSD, pNN50 from RR intervals in seconds."""
    rr = np.asarray(rr_s) * 1000.0
    d = np.diff(rr)
    return (float(60000.0 / np.mean(rr)), float(np.std(rr, ddof=1)),
            float(np.sqrt(np.mean(d**2))) if len(d) else 0.0,
            float(np.mean(np.abs(d) > 50.0)) if len(d) else 0.0)


def resample_rr(times: np.ndarray, rr_s: np.ndarray, fs: float = RR_FS) -> tuple[np.ndarray, np.ndarray]:
    """RR as a uniformly sampled signal (cubic spline through each interval)."""
    from scipy.interpolate import CubicSpline

    tu = np.arange(times[0], times[-1], 1.0 / fs)
    return tu, CubicSpline(times, rr_s)(tu)


def psd(x: np.ndarray, fs: float, seg_s: float = 64.0) -> tuple[np.ndarray, np.ndarray]:
    """Welch power spectral density in units^2/Hz, built on np.fft.

    Linear trend removed per segment, Hann window, 50 percent overlap, and
    scaled so that integrating the PSD over frequency gives the variance
    (Parseval), which is what makes band powers come out in ms^2.
    """
    n = len(x)
    seg = min(n, int(seg_s * fs))
    step = seg // 2
    w = np.hanning(seg)
    scale = fs * np.sum(w**2)
    acc, count = None, 0
    t = np.arange(seg)
    for s in range(0, n - seg + 1, max(step, 1)):
        y = x[s : s + seg]
        y = y - np.polyval(np.polyfit(t, y, 1), t)
        p = np.abs(np.fft.rfft(y * w)) ** 2 / scale
        p[1:-1] *= 2  # one-sided
        acc = p if acc is None else acc + p
        count += 1
    return np.fft.rfftfreq(seg, 1.0 / fs), acc / count


def band_power(f: np.ndarray, p: np.ndarray, band: tuple[float, float]) -> float:
    m = (f >= band[0]) & (f < band[1])
    return float(np.trapezoid(p[m], f[m])) if m.sum() > 1 else 0.0


def hrv_from_beats(beat_times: np.ndarray) -> HRV:
    times, rr = clean_rr(np.asarray(beat_times))
    mean_hr, sdnn, rmssd, pnn50 = time_domain(rr)
    duration = float(beat_times[-1] - beat_times[0]) if len(beat_times) > 1 else 0.0
    valid = duration >= MIN_HRV_SECONDS and len(rr) >= 60
    lf = hf = ratio = resp = None
    f = p = None
    if valid:
        tu, ru = resample_rr(times, rr * 1000.0)
        f, p = psd(ru, RR_FS)
        lf, hf = band_power(f, p, LF_BAND), band_power(f, p, HF_BAND)
        ratio = lf / hf if hf > 0 else None
        m = (f >= HF_BAND[0]) & (f < HF_BAND[1])
        resp = float(f[m][np.argmax(p[m])]) if m.any() else None
    return HRV(mean_hr, sdnn, rmssd, pnn50, lf, hf, ratio, resp, len(beat_times), duration, valid, f, p)


def hrv_from_pulse(pulse: np.ndarray, fs: float, bpm_hint: float | None = None) -> tuple[HRV, np.ndarray]:
    beats = detect_beats(pulse, fs, bpm_hint)
    return hrv_from_beats(beats), beats


def match_beats(est: np.ndarray, true: np.ndarray, tol: float = 0.15) -> np.ndarray:
    """Timing error (s) of each true beat's nearest detected beat within tol."""
    out = []
    for b in true:
        j = np.searchsorted(est, b)
        cands = [est[k] for k in (j - 1, j) if 0 <= k < len(est)]
        if cands:
            d = min(cands, key=lambda c: abs(c - b)) - b
            if abs(d) <= tol:
                out.append(d)
    return np.array(out)
