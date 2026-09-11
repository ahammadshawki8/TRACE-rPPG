"""TRACE: signal-quality-adaptive spectral fusion. Tier T4.

Two versions exist, and both stay in the ablation.

TRACE v1 (below, `fuse` with no artifact reference) scores each method by
spectral concentration alone. Measured in step5: on a held-out cohort it did
worse than POS alone (15.9 vs 10.2 BPM), because a periodic motion artifact
is also a concentrated peak. For the green channel the score was inversely
related to correctness (AUC 0.26).

TRACE v2 adds a pulse-blind artifact reference. Take the brightness
direction (1, 1, 1) in temporally normalised RGB and remove its component
along a nominal blood-volume-pulse direction. What remains sees motion,
shading and lighting changes but is blind to blood. Its spectrum is used
twice: (1) every method's spectrum is multiplied by (1 - A(f))^k, removing
artifact frequencies (a frequency-domain cousin of reference-based noise
cancellation, Li et al. 2014); (2) a method's score is multiplied by
(1 - a)^2, where a is the fraction of artifact power sitting at that
method's chosen peak. The nominal direction is deliberately not the one the
simulator generates pulses with, so the reference is not artificially blind.

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

In v1 quality is scored on a Welch spectrum (a calmer estimator whose bin
jitter will not shake the weights) and the BPM read-out uses the full-length
FFT. In v2 both use the masked full-length spectrum, because the artifact
mask is defined on that frequency grid.
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
# Below this fused quality the read-out is flagged low confidence. The frozen
# values live in results/fusion_params.json, written by step5.
DEFAULT_CONFIDENCE = 0.35
DEFAULT_MASK_K = 4.0


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
    artifact: np.ndarray | None = None,
    mask_k: float = DEFAULT_MASK_K,
    mask_mode: str = "power",
) -> FusionResult:
    """Fuse one analysis window of several methods' band-limited pulses.

    With `artifact` (the band-limited pulse-blind reference for the same
    window) this is TRACE v2 (`mask_mode="power"`) or v3 (`"wiener"`);
    without it, TRACE v1.

    The v3 mask is a Wiener gain, P_m / (P_m + P_a): each frequency is kept
    in proportion to how much of the method's own power exceeds the artifact
    power there. Unlike v2 it compares the artifact with the pulse rather
    than with itself, so a weak reference dominated by pulse leakage cannot
    delete the fundamental.
    """
    if artifact is None:
        per, freqs = {}, None
        for name, seg in segments.items():
            freqs, power, mw = score(seg, fs)
            per[name] = mw
        w = weights_from_quality({n: m.quality for n, m in per.items()}, gamma)
        mask = band_mask(freqs, HR_BAND)
        fused = np.zeros_like(freqs)
        for n, m in per.items():
            fused += w[n] * m.power / max(float(np.max(m.power[mask])), 1e-30)
    else:
        freqs, a_pow = spectrum(artifact, fs, pad_factor=4)
        mask = band_mask(freqs, HR_BAND)
        a_norm = np.clip(a_pow / max(float(np.max(a_pow[mask])), 1e-30), 0, 1)
        keep = (1.0 - a_norm) ** mask_k
        a_total = max(float(np.sum(a_norm[mask])), 1e-30)
        per, masked = {}, {}
        for name, seg in segments.items():
            _, power = spectrum(seg, fs, pad_factor=4)
            pm = power * (power / (power + a_pow + 1e-30) if mask_mode == "wiener" else keep)
            pk = peak_frequency(freqs, pm)
            pk, _ = correct_harmonic_lock(freqs, pm, pk)
            a_frac = float(np.sum(a_norm[mask & (np.abs(freqs - pk) <= 0.12)])) / a_total
            q = spectral_snr(freqs, pm, pk) * (1.0 - a_frac) ** 2
            per[name] = MethodWindow(bpm=pk * 60.0, quality=q, power=pm)
            masked[name] = pm
        w = weights_from_quality({n: m.quality for n, m in per.items()}, gamma)
        fused = np.zeros_like(freqs)
        for n, pm in masked.items():
            fused += w[n] * pm / max(float(np.max(pm[mask])), 1e-30)
    peak = peak_frequency(freqs, fused)
    peak, corrected = correct_harmonic_lock(freqs, fused, peak)
    q = spectral_snr(freqs, fused, peak)
    n = len(next(iter(segments.values())))
    return FusionResult(
        bpm=peak * 60.0, quality=q, confident=q >= confidence, weights=w, per_method=per,
        freqs=freqs, fused_power=fused, harmonic_corrected=corrected,
        resolution_bpm=resolution_hz(n, fs) * 60.0,
    )


# Nominal blood-volume-pulse direction in normalised RGB for the artifact
# reference. Close to published PBV signatures (de Haan and van Leest 2014)
# but deliberately different from the simulator's generating vector
# (0.33, 0.77, 0.53); step5 checks both give the same accuracy.
PBV_NOMINAL = (0.27, 0.80, 0.54)


def artifact_direction(pbv=PBV_NOMINAL) -> np.ndarray:
    p = np.asarray(pbv, float)
    p = p / np.linalg.norm(p)
    one = np.ones(3) / np.sqrt(3.0)
    u = one - np.dot(one, p) * p
    return u / np.linalg.norm(u)


def artifact_reference(rgb: np.ndarray, fs: float, pbv=PBV_NOMINAL) -> np.ndarray:
    """Band-limited pulse-blind reference: normalised RGB along the part of
    the brightness direction orthogonal to the pulse direction."""
    from .methods import temporal_normalise
    from .preprocess import clean_pulse

    return clean_pulse((temporal_normalise(rgb, fs) - 1.0) @ artifact_direction(pbv), fs)


def band_limited_pulses(rgb: np.ndarray, fs: float, names=None) -> dict[str, np.ndarray]:
    """Run each extraction method over the whole recording and band-limit it."""
    from .methods import CLASSICAL, METHODS
    from .preprocess import clean_pulse

    names = names or CLASSICAL
    return {n: clean_pulse(METHODS[n](rgb, fs), fs) for n in names}


def most_trusted(pulses: dict[str, np.ndarray], fs: float, win_s: float = 20.0) -> str:
    """The method with the highest mean quality across the recording.

    Fusion combines spectra, which is right for a heart-rate read-out but
    produces no time-domain waveform. Beat timing (HRV) needs a waveform, so
    it uses the single method TRACE trusts most over the whole capture.
    """
    n = len(next(iter(pulses.values())))
    step = int(win_s * fs)
    scores = {}
    for name, p in pulses.items():
        qs = [score(p[s : s + step], fs)[2].quality for s in range(0, max(n - step, 0) + 1, step // 2)]
        scores[name] = float(np.mean(qs)) if qs else 0.0
    return max(scores, key=scores.get)


def fuse_windows(
    t: np.ndarray,
    pulses: dict[str, np.ndarray],
    fs: float,
    windows: list[tuple[float, float]],
    gamma: float = DEFAULT_GAMMA,
    confidence: float = DEFAULT_CONFIDENCE,
    artifact: np.ndarray | None = None,
    mask_k: float = DEFAULT_MASK_K,
    mask_mode: str = "power",
) -> list[FusionResult]:
    """TRACE over every window. `pulses` (and `artifact`) must already be
    band-limited over the whole recording; each window is then cut."""
    from .datasets import window_slice

    out = []
    for a, b in windows:
        sl = window_slice(t, a, b)
        art = artifact[sl] if artifact is not None else None
        out.append(fuse({n: p[sl] for n, p in pulses.items()}, fs, gamma, confidence, art, mask_k, mask_mode))
    return out
