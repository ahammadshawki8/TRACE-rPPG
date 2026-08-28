"""Detrending and bandpass filtering. Pipeline steps 4 and 6.

Both are convolutions. The FIR bandpass here is built from first principles
(a truncated, windowed sinc) rather than pulled from a library, so the
"classical DSP end to end" claim in Section 17 of the plan holds literally.
A Butterworth path is provided alongside it purely as a cross-check.
"""

from __future__ import annotations

import numpy as np
from scipy.signal import butter, filtfilt


def moving_average_kernel(k: int) -> np.ndarray:
    """The simplest low-pass filter: k equal weights summing to 1."""
    if k < 1:
        raise ValueError("kernel length must be >= 1")
    return np.ones(k) / k


def first_null_hz(k: int, fs: float) -> float:
    """Frequency at which a length-k moving average deletes the signal
    completely. Keep this well above your search band, or the filter will
    erase the very rhythm you are trying to measure."""
    return fs / k


def convolve_reflect(x: np.ndarray, kernel: np.ndarray) -> np.ndarray:
    """Convolution with reflected edges, returning the same length as x.

    Reflect padding matters: zero padding would pull the ends of the signal
    toward zero and create artificial edges, which then leak across the whole
    spectrum.
    """
    pad = len(kernel) // 2
    xp = np.pad(x, pad, mode="reflect")
    y = np.convolve(xp, kernel, mode="same")
    return y[pad : pad + len(x)]


def detrend(x: np.ndarray, window: int) -> np.ndarray:
    """Remove slow baseline wander by subtracting a smoothed copy.

    A low-pass subtracted from the original is a high-pass. Choose `window`
    several times longer than one heartbeat: at 30 fps and 72 BPM a beat is
    25 samples, so 45 to 90 removes drift while leaving the pulse intact.
    Verify with first_null_hz().
    """
    trend = convolve_reflect(x, moving_average_kernel(window))
    return x - trend


def bandpass_kernel(
    fs: float,
    low_hz: float,
    high_hz: float,
    numtaps: int = 301,
    window: str = "hamming",
) -> np.ndarray:
    """Windowed-sinc FIR bandpass, built by hand.

    The ideal bandpass is a difference of two sincs in the time domain, which
    is infinitely long. Truncating it to `numtaps` and multiplying by a smooth
    window is exactly the leakage/windowing trade-off from Tier 1, applied to
    the filter instead of to the data.
    """
    if numtaps % 2 == 0:
        numtaps += 1  # symmetric kernel needs an odd length
    n = np.arange(numtaps) - (numtaps - 1) / 2

    f_low = low_hz / fs      # normalised to cycles/sample
    f_high = high_hz / fs

    # np.sinc(z) is sin(pi z)/(pi z), which already carries the pi factors.
    h = 2 * f_high * np.sinc(2 * f_high * n) - 2 * f_low * np.sinc(2 * f_low * n)

    if window == "hamming":
        w = 0.54 - 0.46 * np.cos(2 * np.pi * np.arange(numtaps) / (numtaps - 1))
    elif window == "blackman":
        m = np.arange(numtaps) / (numtaps - 1)
        w = 0.42 - 0.5 * np.cos(2 * np.pi * m) + 0.08 * np.cos(4 * np.pi * m)
    elif window == "rect":
        w = np.ones(numtaps)
    else:
        raise ValueError(f"unknown window: {window}")

    h = h * w
    # Normalise to unity gain at the centre of the passband.
    f_mid = 0.5 * (low_hz + high_hz)
    gain = np.abs(np.sum(h * np.exp(-2j * np.pi * f_mid / fs * n)))
    if gain > 0:
        h = h / gain
    return h


def bandpass_fir(
    x: np.ndarray,
    fs: float,
    low_hz: float = 0.7,
    high_hz: float = 4.0,
    numtaps: int = 301,
) -> np.ndarray:
    """Apply the hand-built FIR with zero phase distortion.

    A symmetric FIR has linear phase, meaning a constant delay of
    (numtaps-1)/2 samples. Convolving 'full' and then trimming that delay
    removes it exactly, so beat timing is preserved. This matters for HRV,
    where the whole measurement is timing.
    """
    h = bandpass_kernel(fs, low_hz, high_hz, numtaps)
    pad = len(h) // 2
    xp = np.pad(x, pad, mode="reflect")
    y = np.convolve(xp, h, mode="full")
    start = 2 * pad
    return y[start : start + len(x)]


def bandpass_butter(
    x: np.ndarray,
    fs: float,
    low_hz: float = 0.7,
    high_hz: float = 4.0,
    order: int = 3,
) -> np.ndarray:
    """Butterworth bandpass applied with filtfilt.

    filtfilt runs the filter forwards then backwards so the two delays cancel
    exactly at every frequency. Never use a single-pass lfilter before a
    timing measurement.
    """
    nyq = fs / 2.0
    b, a = butter(order, [low_hz / nyq, high_hz / nyq], btype="band")
    return filtfilt(b, a, x)


def fft_convolve(x: np.ndarray, kernel: np.ndarray) -> np.ndarray:
    """Linear convolution performed through the FFT, correctly zero-padded.

    Without padding to at least len(x)+len(h)-1, the FFT treats the signal as
    a loop and the tail contaminates the head. That is circular convolution,
    and it is the wraparound trap from Tier 1.
    """
    n = len(x) + len(kernel) - 1
    nfft = 1 << (n - 1).bit_length()  # next power of two, for speed
    X = np.fft.rfft(x, nfft)
    H = np.fft.rfft(kernel, nfft)
    y = np.fft.irfft(X * H, nfft)[:n]
    return y


def frequency_response(
    kernel: np.ndarray, fs: float, n_points: int = 2048
) -> tuple[np.ndarray, np.ndarray]:
    """Magnitude response |H(f)| of a kernel. The only honest way to judge a
    filter: for each frequency, how much survives?"""
    H = np.fft.rfft(kernel, n_points)
    freqs = np.fft.rfftfreq(n_points, 1 / fs)
    return freqs, np.abs(H)
