"""TRACE-rPPG: Tone-stratified Robustness Across Compressed Encodings.

A classical rPPG pipeline with quality-adaptive fusion, built to measure
whether video compression amplifies the skin-tone accuracy gap.

Every number this package produces comes out of a convolution or a Fourier
transform. There is no trained model anywhere in the estimation path.
"""

from .preprocess import (
    bandpass_butter,
    bandpass_fir,
    bandpass_kernel,
    detrend,
    fft_convolve,
    first_null_hz,
    frequency_response,
    moving_average_kernel,
)
from .spectral import (
    HR_BAND,
    Estimate,
    correct_harmonic_lock,
    estimate_bpm,
    peak_frequency,
    resolution_hz,
    spectral_snr,
    spectrum,
    welch_spectrum,
)
from .synth import (
    REALISTIC_PULSE,
    SUPPRESSED_FUNDAMENTAL,
    pulse_signal,
    pulse_wave,
    two_subject_signal,
)

__version__ = "0.1.0"

__all__ = [
    "HR_BAND",
    "REALISTIC_PULSE",
    "SUPPRESSED_FUNDAMENTAL",
    "Estimate",
    "bandpass_butter",
    "bandpass_fir",
    "bandpass_kernel",
    "correct_harmonic_lock",
    "detrend",
    "estimate_bpm",
    "fft_convolve",
    "first_null_hz",
    "frequency_response",
    "moving_average_kernel",
    "peak_frequency",
    "pulse_signal",
    "pulse_wave",
    "resolution_hz",
    "spectral_snr",
    "spectrum",
    "two_subject_signal",
    "welch_spectrum",
]
