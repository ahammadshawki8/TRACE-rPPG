"""Frequency-domain analysis. Pipeline steps 7 and 8.

Everything here is the winding machine: wind the signal around a circle at a
test rate and see whether the dots pile up. BPM comes from where they pile up
highest; the quality score comes from what fraction of the band's energy sits
in that pile.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

HR_BAND = (0.7, 4.0)  # Hz, i.e. 42 to 240 BPM


@dataclass
class Estimate:
    """One BPM reading plus everything needed to judge it."""

    bpm: float
    freq_hz: float
    quality: float
    resolution_bpm: float
    harmonic_corrected: bool = False

    def __str__(self) -> str:
        flag = "  [halved: harmonic lock-on]" if self.harmonic_corrected else ""
        return (
            f"{self.bpm:6.2f} BPM   quality={self.quality:.3f}   "
            f"resolution=+/-{self.resolution_bpm:.2f} BPM{flag}"
        )


def spectrum(
    x: np.ndarray,
    fs: float,
    window: str = "hann",
    pad_factor: int = 1,
) -> tuple[np.ndarray, np.ndarray]:
    """Power spectrum of x.

    A window is applied before the transform. Without one, the abrupt cut at
    each end of the recording is itself a sharp feature that needs a broad
    spread of frequencies to describe, and that spread (leakage) can bury a
    weak peak under a strong neighbour's skirts.

    pad_factor > 1 zero-pads, which interpolates the spectrum so a peak is
    easier to locate. It adds no real resolution: two merged peaks stay
    merged. Only a longer recording separates them.
    """
    n = len(x)
    x = x - np.mean(x)

    if window == "hann":
        w = np.hanning(n)
    elif window == "hamming":
        w = np.hamming(n)
    elif window == "rect":
        w = np.ones(n)
    else:
        raise ValueError(f"unknown window: {window}")

    nfft = int(n * pad_factor)
    X = np.fft.rfft(x * w, n=nfft)
    freqs = np.fft.rfftfreq(nfft, 1.0 / fs)
    return freqs, np.abs(X) ** 2


def resolution_hz(n_samples: int, fs: float) -> float:
    """Frequency resolution = 1/T. The single most practical formula here:
    a 30-second window can only resolve 1/30 Hz, which is 2 BPM."""
    return fs / n_samples


def _parabolic_peak(power: np.ndarray, idx: int) -> float:
    """Sub-bin peak location by fitting a parabola through three points.

    A peak in a sampled spectrum almost never lands exactly on a bin. Fitting
    the log-power of the peak bin and its two neighbours and solving for the
    vertex recovers roughly an order of magnitude in precision for three
    lines of code.
    """
    if idx <= 0 or idx >= len(power) - 1:
        return 0.0
    y1, y2, y3 = np.log(power[idx - 1 : idx + 2] + 1e-30)
    denom = y1 - 2 * y2 + y3
    if abs(denom) < 1e-30:
        return 0.0
    delta = 0.5 * (y1 - y3) / denom
    return float(np.clip(delta, -0.5, 0.5))


def band_mask(freqs: np.ndarray, band: tuple[float, float] = HR_BAND) -> np.ndarray:
    return (freqs >= band[0]) & (freqs <= band[1])


def peak_frequency(
    freqs: np.ndarray,
    power: np.ndarray,
    band: tuple[float, float] = HR_BAND,
    interpolate: bool = True,
) -> float:
    """Strongest frequency inside the plausible band, in Hz."""
    mask = band_mask(freqs, band)
    if not mask.any():
        raise ValueError("band contains no bins")
    in_band = np.flatnonzero(mask)
    idx = in_band[np.argmax(power[mask])]

    df = freqs[1] - freqs[0]
    if interpolate:
        return float(freqs[idx] + _parabolic_peak(power, idx) * df)
    return float(freqs[idx])


def spectral_snr(
    freqs: np.ndarray,
    power: np.ndarray,
    peak_hz: float,
    band: tuple[float, float] = HR_BAND,
    half_width_hz: float = 0.12,
    include_harmonic: bool = True,
) -> float:
    """The TRACE quality score: in-band signal power over total in-band power.

    Returns 0 to 1. Near 1 means nearly all the energy is concentrated at one
    rhythm and its harmonic, which is what a real pulse looks like. Near 0
    means energy is spread across the band, which is what noise looks like.

    The harmonic is counted as signal deliberately: a sharp pulse waveform
    necessarily produces one, so treating it as noise would penalise exactly
    the cleanest signals.
    """
    mask = band_mask(freqs, band)
    total = float(np.sum(power[mask]))
    if total <= 0:
        return 0.0

    sig_mask = np.abs(freqs - peak_hz) <= half_width_hz
    if include_harmonic:
        sig_mask |= np.abs(freqs - 2 * peak_hz) <= half_width_hz
    sig_mask &= mask

    return float(np.sum(power[sig_mask]) / total)


def _local_power(
    freqs: np.ndarray, power: np.ndarray, centre_hz: float, half_width_hz: float
) -> float:
    m = np.abs(freqs - centre_hz) <= half_width_hz
    return float(np.sum(power[m])) if m.any() else 0.0


def correct_harmonic_lock(
    freqs: np.ndarray,
    power: np.ndarray,
    peak_hz: float,
    band: tuple[float, float] = HR_BAND,
    half_width_hz: float = 0.12,
    min_ratio: float = 0.05,
    min_prominence: float = 50.0,
) -> tuple[float, bool]:
    """Defend against reporting double the true heart rate.

    Before accepting a peak at f, look at f/2. If a genuine spectral component
    sits there and f/2 is still a plausible heart rate, the peak was probably
    the second harmonic and the true rate is half.

    Two criteria must both hold, because either alone gives false positives:

      * `min_ratio`  -- the sub-harmonic must carry at least this fraction of
        the peak's power. A suppressed fundamental still carries a useful
        share; unrelated noise does not.
      * `min_prominence` -- the sub-harmonic must stand this many times above
        the band's median power, i.e. it must be a real peak rather than a
        bump in the noise floor.

    Measured separation on synthetic signals: a genuine trap gives ratio 0.17
    and prominence 790, while a healthy pulse whose half-rate lands in band
    gives ratio 0.003 and prominence 22. The thresholds sit between, with
    roughly an order of magnitude of margin on each side.
    """
    half = peak_hz / 2.0
    if half < band[0]:
        # Half the rate is below the plausible range, so it cannot be the
        # true fundamental. Nothing to correct.
        return peak_hz, False

    p_peak = _local_power(freqs, power, peak_hz, half_width_hz)
    p_half = _local_power(freqs, power, half, half_width_hz)
    if p_peak <= 0:
        return peak_hz, False

    mask = band_mask(freqs, band)
    floor = float(np.median(power[mask])) if mask.any() else 0.0

    ratio_ok = (p_half / p_peak) >= min_ratio
    prominent = floor <= 0 or (p_half / floor) >= min_prominence

    if ratio_ok and prominent:
        return half, True
    return peak_hz, False


def estimate_bpm(
    x: np.ndarray,
    fs: float,
    band: tuple[float, float] = HR_BAND,
    window: str = "hann",
    pad_factor: int = 4,
    guard_harmonic: bool = True,
) -> Estimate:
    """Full BPM estimate with quality score and harmonic defence."""
    freqs, power = spectrum(x, fs, window=window, pad_factor=pad_factor)
    peak_hz = peak_frequency(freqs, power, band)

    corrected = False
    if guard_harmonic:
        peak_hz, corrected = correct_harmonic_lock(freqs, power, peak_hz, band)

    q = spectral_snr(freqs, power, peak_hz, band)
    return Estimate(
        bpm=peak_hz * 60.0,
        freq_hz=peak_hz,
        quality=q,
        resolution_bpm=resolution_hz(len(x), fs) * 60.0,
        harmonic_corrected=corrected,
    )


def welch_spectrum(
    x: np.ndarray,
    fs: float,
    n_segments: int = 4,
    overlap: float = 0.5,
) -> tuple[np.ndarray, np.ndarray]:
    """Averaged periodogram, for a calmer estimate of the noise floor.

    A single-FFT spectrum is a noisy estimator in itself: each bin jitters
    even with perfect data. That jitter propagates into the quality score and
    would shake the fusion weights. Averaging segments removes it, at the
    cost of coarser resolution, which is an acceptable trade for the metric
    (but not for the BPM readout, which should use the full-length FFT).
    """
    n = len(x)
    seg = int(n / (1 + (n_segments - 1) * (1 - overlap)))
    if seg < 16 or n_segments < 2:
        return spectrum(x, fs)

    step = max(1, int(seg * (1 - overlap)))
    acc = None
    count = 0
    for start in range(0, n - seg + 1, step):
        f, p = spectrum(x[start : start + seg], fs)
        acc = p if acc is None else acc + p
        count += 1
    return f, acc / max(count, 1)
