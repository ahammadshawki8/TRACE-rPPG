"""TRACE: signal-quality-adaptive spectral fusion. Tier T4.

For every analysis window, each method's band-limited pulse is scored by the
same Fourier-domain quality metric (in-band power at the peak and its
harmonic, over total in-band power; Parseval is what makes power in the
spectrum equal energy in time). The weights are the scores raised to a
power gamma and normalised. The fused spectrum is the weighted sum of each
method's spectrum normalised to unit in-band peak, and the heart rate comes
from that fused spectrum through the same peak search and sub-harmonic
defence as any single method.

gamma is the one hyperparameter. gamma = 0 is an equal-weight average,
gamma -> infinity is "pick the best-scoring method", and the default comes
from tuning on a separate simulated cohort in step5 (frozen before testing).

Quality is scored on a Welch spectrum (averaged segments, a calmer estimator
whose bin jitter will not shake the weights); the BPM read-out uses the
full-length FFT (finer resolution). Engineering invariant 9 in CLAUDE.md.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from .spectral import (
    HR_BAND,
    band_mask,
    correct_harmonic_lock,
    peak_frequency,
    resolution_hz,
    spectral_snr,
    spectrum,
    welch_spectrum,
)

DEFAULT_GAMMA = 2.0
# Below this fused quality the read-out is flagged low confidence. Set in step5
# from the quality at which single-window error starts to exceed 5 BPM.
DEFAULT_CONFIDENCE = 0.35


@dataclass
class MethodWindow:
    bpm: float
    quality: float
    power: np.ndarray = field(repr=False)


@dataclass
class FusionResult:
    bpm: float
    quality: float
    confident: bool
    weights: dict[str, float]
    per_method: dict[str, MethodWindow] = field(repr=False)
    freqs: np.ndarray = field(repr=False, default=None)
    fused_power: np.ndarray = field(repr=False, default=None)
    harmonic_corrected: bool = False
    resolution_bpm: float = 0.0


def score(segment: np.ndarray, fs: float, pad_factor: int = 4) -> tuple[np.ndarray, np.ndarray, MethodWindow]:
    """Full-length spectrum for the read-out, Welch spectrum for the score."""
    freqs, power = spectrum(segment, fs, pad_factor=pad_factor)
    peak = peak_frequency(freqs, power)
    peak, _ = correct_harmonic_lock(freqs, power, peak)
    wf, wp = welch_spectrum(segment, fs)
    q = spectral_snr(wf, wp, peak_frequency(wf, wp))
    return freqs, power, MethodWindow(bpm=peak * 60.0, quality=q, power=power)


def weights_from_quality(q: dict[str, float], gamma: float) -> dict[str, float]:
    names = list(q)
    v = np.array([max(q[n], 1e-6) for n in names])
    if np.isinf(gamma):
        w = (v == v.max()).astype(float)
    else:
        w = v**gamma
    w = w / w.sum()
    return {n: float(x) for n, x in zip(names, w)}


def fuse(
    segments: dict[str, np.ndarray],
    fs: float,
    gamma: float = DEFAULT_GAMMA,
    confidence: float = DEFAULT_CONFIDENCE,
) -> FusionResult:
    """Fuse one analysis window of several methods' band-limited pulses."""
    per, freqs = {}, None
    for name, seg in segments.items():
        freqs, power, mw = score(seg, fs)
        per[name] = mw
    w = weights_from_quality({n: m.quality for n, m in per.items()}, gamma)
    mask = band_mask(freqs, HR_BAND)
    fused = np.zeros_like(freqs)
    for n, m in per.items():
        fused += w[n] * m.power / max(float(np.max(m.power[mask])), 1e-30)
    peak = peak_frequency(freqs, fused)
    peak, corrected = correct_harmonic_lock(freqs, fused, peak)
    q = spectral_snr(freqs, fused, peak)
    n = len(next(iter(segments.values())))
    return FusionResult(
        bpm=peak * 60.0, quality=q, confident=q >= confidence, weights=w, per_method=per,
        freqs=freqs, fused_power=fused, harmonic_corrected=corrected,
        resolution_bpm=resolution_hz(n, fs) * 60.0,
    )


def fuse_windows(
    t: np.ndarray,
    pulses: dict[str, np.ndarray],
    fs: float,
    windows: list[tuple[float, float]],
    gamma: float = DEFAULT_GAMMA,
    confidence: float = DEFAULT_CONFIDENCE,
) -> list[FusionResult]:
    """TRACE over every window. `pulses` must already be band-limited
    (`clean_pulse` over the whole recording), then each window is cut."""
    from .datasets import window_slice

    out = []
    for a, b in windows:
        sl = window_slice(t, a, b)
        out.append(fuse({n: p[sl] for n, p in pulses.items()}, fs, gamma, confidence))
    return out
