"""Synthetic test signals with known ground truth.

The point of this module is to let every later stage be debugged against a
signal whose correct answer we already know. If the pipeline cannot recover
72 BPM from `pulse_signal(bpm=72)`, the bug is in the mathematics, not in
face tracking, lighting, or the camera.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

# Relative harmonic amplitudes of a realistic pulse waveform. A heartbeat is a
# sharp upstroke followed by a fast fall, and Fourier series says a shape that
# sharp needs harmonics. These are the same values used in the Tier 1 lesson.
REALISTIC_PULSE = (1.00, 0.62, 0.38, 0.24, 0.15, 0.09)

# A pulse whose fundamental has been suppressed, e.g. by an over-aggressive
# high-pass edge. This is what triggers the 144 BPM bug.
SUPPRESSED_FUNDAMENTAL = (0.35, 0.80, 0.40, 0.22)


def time_axis(duration_s: float, fs: float) -> np.ndarray:
    """Uniformly spaced sample times. Uniform spacing is load-bearing: the
    DFT assumes it, so anything that breaks it (dropped webcam frames) must
    be resampled onto this grid before analysis."""
    n = int(round(duration_s * fs))
    return np.arange(n) / fs


def pulse_wave(
    t: np.ndarray,
    bpm: float,
    harmonics: tuple[float, ...] = REALISTIC_PULSE,
    phase: float = 0.0,
) -> np.ndarray:
    """A quasi-periodic pulse built as a fundamental plus harmonics.

    harmonics[k] is the amplitude of the (k+1)-th harmonic, so harmonics[0]
    is the fundamental at `bpm` and harmonics[1] sits at twice that rate.
    """
    f0 = bpm / 60.0
    out = np.zeros_like(t)
    for k, amp in enumerate(harmonics, start=1):
        # Small progressive phase offset so the waveform has a realistic
        # asymmetric shape rather than a symmetric spike.
        out += amp * np.cos(2 * np.pi * k * f0 * t + phase - 0.35 * (k - 1))
    return out


def lighting_drift(t: np.ndarray, strength: float = 4.0, seed: int = 0) -> np.ndarray:
    """Slow baseline wander: sun behind a cloud, subject settling, a screen
    changing colour behind them. Typically several times larger than the
    pulse, which is why detrending comes before anything else."""
    rng = np.random.default_rng(seed)
    drift = (
        np.sin(2 * np.pi * 0.021 * t + rng.uniform(0, 2 * np.pi))
        + 0.6 * np.sin(2 * np.pi * 0.060 * t + rng.uniform(0, 2 * np.pi))
        + 0.25 * (t / max(t[-1], 1e-9))  # linear component
    )
    return strength * drift


def add_noise(x: np.ndarray, snr_db: float, seed: int = 0) -> np.ndarray:
    """Add white Gaussian noise at a specified signal-to-noise ratio.

    snr_db is computed on power: 10*log10(P_signal / P_noise). Negative
    values mean the noise is stronger than the signal, which is the normal
    situation in real rPPG and still perfectly recoverable, because noise is
    not rhythmic and cancels when wound around a circle.
    """
    rng = np.random.default_rng(seed)
    p_signal = float(np.mean(x**2))
    p_noise = p_signal / (10 ** (snr_db / 10.0))
    return x + rng.normal(0.0, np.sqrt(p_noise), size=x.shape)


def pulse_signal(
    bpm: float = 72.0,
    duration_s: float = 30.0,
    fs: float = 30.0,
    harmonics: tuple[float, ...] = REALISTIC_PULSE,
    drift: float = 4.0,
    snr_db: float = 0.0,
    seed: int = 0,
) -> tuple[np.ndarray, np.ndarray]:
    """A complete synthetic skin-brightness trace with known ground truth.

    Returns (t, x). Defaults mimic a webcam recording: 30 fps, 30 seconds,
    drift several times larger than the pulse, and noise at equal power to
    the pulse.
    """
    t = time_axis(duration_s, fs)
    pulse = pulse_wave(t, bpm, harmonics)
    x = pulse + lighting_drift(t, drift, seed=seed)
    if snr_db is not None:
        # Reference the SNR to the pulse alone, not to pulse + drift.
        rng = np.random.default_rng(seed + 1)
        p_signal = float(np.mean(pulse**2))
        p_noise = p_signal / (10 ** (snr_db / 10.0))
        x = x + rng.normal(0.0, np.sqrt(p_noise), size=x.shape)
    return t, x


@dataclass
class Rhythm:
    """A heartbeat sequence with known timing, for HRV ground truth.

    `beat_times` are systolic peak times in seconds. `rr` holds the intervals
    between them. `lf_hf_nominal` is the ratio of the squared LF and HF
    modulation depths used to generate the rhythm, a first-order analytic
    value that a long recording should reproduce.
    """

    beat_times: np.ndarray
    rr: np.ndarray
    mean_bpm: float
    lf_hf_nominal: float


def heart_rhythm(
    duration_s: float,
    mean_bpm: float = 72.0,
    lf_bpm: float = 3.0,
    hf_bpm: float = 2.5,
    lf_hz: float = 0.10,
    resp_hz: float = 0.25,
    wander_bpm: float = 2.0,
    seed: int = 0,
) -> Rhythm:
    """Beat times from an instantaneous heart rate with LF and HF rhythms.

    The instantaneous rate is a mean, plus a slow baroreflex-like oscillation
    in the LF band (default 0.10 Hz), plus respiratory sinus arrhythmia at
    the breathing rate in the HF band (default 0.25 Hz, 15 breaths/min), plus
    a slow random wander. Beats fall wherever the integrated phase crosses a
    whole number, so the rhythm is continuous rather than a jittered grid.
    """
    rng = np.random.default_rng(seed)
    fs = 200.0
    t = np.arange(0.0, duration_s + 3.0, 1.0 / fs)

    # Slow wander: white noise smoothed by a 20 s moving average, rescaled.
    k = int(20 * fs)
    raw = rng.normal(size=len(t) + k)
    wander = np.convolve(raw, np.ones(k) / k, mode="valid")[: len(t)]
    wander = wander / (np.std(wander) + 1e-12) * wander_bpm

    hr = (
        mean_bpm
        + lf_bpm * np.sin(2 * np.pi * lf_hz * t + rng.uniform(0, 2 * np.pi))
        + hf_bpm * np.sin(2 * np.pi * resp_hz * t + rng.uniform(0, 2 * np.pi))
        + wander
    )
    phase = np.cumsum(hr / 60.0) / fs + rng.uniform(0, 1)
    whole = np.floor(phase)
    idx = np.flatnonzero(np.diff(whole) > 0)
    # Linear interpolation of the exact crossing time between samples.
    frac = (whole[idx + 1] - phase[idx]) / (phase[idx + 1] - phase[idx])
    beats = t[idx] + frac / fs
    beats = beats[beats <= duration_s]

    return Rhythm(
        beat_times=beats,
        rr=np.diff(beats),
        mean_bpm=float(60.0 / np.mean(np.diff(beats))),
        lf_hf_nominal=float((lf_bpm / hf_bpm) ** 2),
    )


def ppg_from_beats(
    t: np.ndarray,
    beat_times: np.ndarray,
    dicrotic: float = 0.35,
) -> np.ndarray:
    """A PPG-shaped waveform with a systolic peak exactly at each beat time.

    Each beat is a narrow systolic Gaussian followed by a smaller, wider
    dicrotic wave. The result is zero-mean with unit peak-to-peak amplitude,
    so callers scale it to a physical modulation depth.
    """
    d = t[:, None] - beat_times[None, :]
    wave = np.exp(-0.5 * (d / 0.09) ** 2) + dicrotic * np.exp(-0.5 * ((d - 0.32) / 0.12) ** 2)
    x = wave.sum(axis=1)
    x = x - np.mean(x)
    return x / (np.ptp(x) + 1e-12)


def two_subject_signal(
    bpm_a: float = 72.0,
    bpm_b: float = 78.0,
    duration_s: float = 30.0,
    fs: float = 30.0,
    seed: int = 0,
) -> tuple[np.ndarray, np.ndarray]:
    """Two rhythms at once, for testing frequency resolution. They separate
    only once the window is longer than 1/(f_b - f_a)."""
    t = time_axis(duration_s, fs)
    x = pulse_wave(t, bpm_a) + 0.9 * pulse_wave(t, bpm_b, phase=0.7)
    return t, add_noise(x, snr_db=10.0, seed=seed)
