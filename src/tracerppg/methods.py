"""Pulse extraction from RGB traces. Tier T3.

Every method maps an (n, 3) array of mean skin R, G, B to a 1D pulse signal.
Their outputs all pass through the same `clean_pulse` and FFT afterwards, so
the only thing that differs between methods is how the three channels are
combined. None of them is learned: CHROM and POS are fixed projections
derived from a model of skin reflectance, and ICA is blind source separation
with no training data.

The physics they exploit (Lesson Tier 0, slide 4 of the deck): motion and
lighting change all three channels together, a heartbeat changes their
balance. After dividing each channel by its own running mean, a pure
brightness change becomes the vector (1, 1, 1), which both CHROM and POS
project to zero exactly.
"""

from __future__ import annotations

from typing import Callable

import numpy as np

from .preprocess import bandpass_fir, convolve_reflect, default_numtaps, moving_average_kernel
from .spectral import HR_BAND, spectral_snr, spectrum, peak_frequency

WIN_S = 1.6  # the short window both CHROM and POS use in their papers


def temporal_normalise(rgb: np.ndarray, fs: float, win_s: float = WIN_S) -> np.ndarray:
    """Divide each channel by its running mean: a convolution, then a ratio.

    This removes the skin's own colour (the DC of each channel) and leaves
    relative changes, so a brightness change of 1 percent reads as 0.01 in
    every channel regardless of how dark or light the skin is.
    """
    k = max(3, int(round(win_s * fs)) | 1)
    mean = np.column_stack([convolve_reflect(rgb[:, c], moving_average_kernel(k)) for c in range(3)])
    return rgb / np.maximum(mean, 1e-6)


def green(rgb: np.ndarray, fs: float) -> np.ndarray:
    """Green channel alone (Verkruysse 2008): haemoglobin absorbs green most."""
    return temporal_normalise(rgb, fs)[:, 1] - 1.0


def _overlap_add(n: int, win: int, fn: Callable[[slice], np.ndarray]) -> np.ndarray:
    """Hann-windowed overlap-add at 50 percent hop, the scheme both papers use."""
    out = np.zeros(n)
    hop = max(1, win // 2)
    w = np.hanning(win)
    for start in range(0, n - win + 1, hop):
        sl = slice(start, start + win)
        out[sl] += fn(sl) * w
    return out


def chrom(rgb: np.ndarray, fs: float) -> np.ndarray:
    """CHROM (de Haan and Jeanne 2013).

    X = 3R - 2G and Y = 1.5R + G - 1.5B are two chrominance signals that
    each cancel specular reflection under a standardised skin colour. The
    pulse is X - alpha Y, with alpha = std(X)/std(Y) re-tuned in every short
    window, which cancels whatever distortion X and Y still share.

    X and Y are band-limited once over the whole recording with the project's
    own FIR (rather than a short Butterworth per 1.6 s window), then alpha is
    computed locally and the result overlap-added.
    """
    c = temporal_normalise(rgb, fs)
    x = 3.0 * c[:, 0] - 2.0 * c[:, 1]
    y = 1.5 * c[:, 0] + c[:, 1] - 1.5 * c[:, 2]
    taps = min(default_numtaps(fs), 2 * (len(x) // 2) - 1)
    xf = bandpass_fir(x - x.mean(), fs, *HR_BAND, numtaps=taps)
    yf = bandpass_fir(y - y.mean(), fs, *HR_BAND, numtaps=taps)
    win = max(8, int(round(WIN_S * fs)))

    def seg(sl: slice) -> np.ndarray:
        a = np.std(xf[sl]) / max(np.std(yf[sl]), 1e-12)
        s = xf[sl] - a * yf[sl]
        return s - s.mean()

    return _overlap_add(len(x), win, seg)


POS_PROJECTION = np.array([[0.0, 1.0, -1.0], [-2.0, 1.0, 1.0]])


def pos(rgb: np.ndarray, fs: float) -> np.ndarray:
    """POS (Wang, den Brinker, Stuijk and de Haan 2017).

    Project temporally normalised RGB onto the plane orthogonal to (1, 1, 1),
    which removes brightness changes exactly. Within that plane, combine the
    two axes S1 = G - B and S2 = G + B - 2R with a data-driven weight
    std(S1)/std(S2), so whichever direction the distortion takes in a given
    window is cancelled. Unlike CHROM, no standard skin colour is assumed.
    """
    n = len(rgb)
    win = max(8, int(round(WIN_S * fs)))
    out = np.zeros(n)
    for end in range(win, n + 1):
        block = rgb[end - win : end]
        cn = block / np.maximum(block.mean(axis=0), 1e-6)
        s = cn @ POS_PROJECTION.T
        h = s[:, 0] + (np.std(s[:, 0]) / max(np.std(s[:, 1]), 1e-12)) * s[:, 1]
        out[end - win : end] += h - h.mean()
    return out


def _fastica(x: np.ndarray, n_iter: int = 200, seed: int = 0) -> np.ndarray:
    """Symmetric FastICA with a log-cosh contrast, from first principles."""
    x = x - x.mean(axis=0)
    cov = np.cov(x, rowvar=False)
    d, e = np.linalg.eigh(cov)
    white = e @ np.diag(1.0 / np.sqrt(np.maximum(d, 1e-12))) @ e.T
    z = x @ white.T
    rng = np.random.default_rng(seed)
    w, _ = np.linalg.qr(rng.normal(size=(3, 3)))
    for _ in range(n_iter):
        wz = z @ w.T
        g, dg = np.tanh(wz), 1 - np.tanh(wz) ** 2
        w_new = (g.T @ z) / len(z) - np.diag(dg.mean(axis=0)) @ w
        u, _, vt = np.linalg.svd(w_new)
        w_new = u @ vt
        if np.max(np.abs(np.abs(np.diag(w_new @ w.T)) - 1)) < 1e-7:
            w = w_new
            break
        w = w_new
    return z @ w.T


def ica(rgb: np.ndarray, fs: float) -> np.ndarray:
    """ICA baseline (Poh, McDuff and Picard 2010).

    Separate the three normalised traces into independent components and keep
    the one whose spectrum is most concentrated at a single in-band rhythm.
    Component order and sign are arbitrary in ICA, which is precisely why it
    is a fragile baseline.
    """
    c = temporal_normalise(rgb, fs) - 1.0
    taps = min(default_numtaps(fs), 2 * (len(c) // 2) - 1)
    cf = np.column_stack([bandpass_fir(c[:, k], fs, *HR_BAND, numtaps=taps) for k in range(3)])
    comps = _fastica(cf)
    best, best_q = comps[:, 0], -1.0
    for k in range(comps.shape[1]):
        f, p = spectrum(comps[:, k], fs, pad_factor=2)
        q = spectral_snr(f, p, peak_frequency(f, p))
        if q > best_q:
            best, best_q = comps[:, k], q
    return best


METHODS: dict[str, Callable[[np.ndarray, float], np.ndarray]] = {
    "green": green,
    "ica": ica,
    "chrom": chrom,
    "pos": pos,
}
CLASSICAL = ("green", "chrom", "pos")  # the three TRACE fuses
