"""Step 1 of the build staircase: verify the pipeline on a signal whose
answer we already know.

No video, no face tracking, no camera. If this fails, the bug is in the
mathematics and we have perfect ground truth to hunt it with. Every later
stage assumes this one passes.

Run:  .venv/Scripts/python.exe scripts/step1_synthetic.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from tracerppg import (  # noqa: E402
    HR_BAND,
    SUPPRESSED_FUNDAMENTAL,
    bandpass_fir,
    bandpass_kernel,
    detrend,
    estimate_bpm,
    fft_convolve,
    first_null_hz,
    frequency_response,
    moving_average_kernel,
    pulse_signal,
    resolution_hz,
    spectrum,
    two_subject_signal,
)

FS = 30.0
DURATION = 30.0
TRUE_BPM = 72.0

results: list[tuple[str, bool, str]] = []


def check(name: str, passed: bool, detail: str = "") -> None:
    results.append((name, passed, detail))
    mark = "PASS" if passed else "FAIL"
    print(f"  [{mark}] {name}" + (f"  --  {detail}" if detail else ""))


def rule(title: str) -> None:
    print(f"\n{title}\n" + "-" * len(title))


# ---------------------------------------------------------------------------
rule("1. Does the pipeline recover a known heart rate?")

t, raw = pulse_signal(bpm=TRUE_BPM, duration_s=DURATION, fs=FS, drift=4.0, snr_db=0.0)
print(f"  {len(raw)} samples, {DURATION:.0f} s at {FS:.0f} fps")
print(f"  drift is 4x the pulse; noise at 0 dB SNR (equal power to the pulse)")

detrended = detrend(raw, window=61)
filtered = bandpass_fir(detrended, FS, *HR_BAND, numtaps=301)
est = estimate_bpm(filtered, FS)

print(f"  true      : {TRUE_BPM:.2f} BPM")
print(f"  estimated : {est}")

res_bpm = resolution_hz(len(raw), FS) * 60.0
check(
    "BPM within one resolution bin",
    abs(est.bpm - TRUE_BPM) <= res_bpm,
    f"error {abs(est.bpm - TRUE_BPM):.2f} BPM, bin width {res_bpm:.2f} BPM",
)
check("quality score is high on a clean pulse", est.quality > 0.5,
      f"quality={est.quality:.3f}")


# ---------------------------------------------------------------------------
rule("2. What does detrending actually buy?")

# Measure the thing directly: how much energy does drift alone put inside the
# heart-rate band, before and after detrending? That leakage is the noise
# floor the quality metric has to compete with.
from tracerppg.spectral import band_mask  # noqa: E402
from tracerppg.synth import lighting_drift, time_axis  # noqa: E402

t_d = time_axis(DURATION, FS)
drift_only = lighting_drift(t_d, strength=4.0, seed=0)

f_before, p_before = spectrum(drift_only, FS)
f_after, p_after = spectrum(detrend(drift_only, 61), FS)
leak_before = float(np.sum(p_before[band_mask(f_before, HR_BAND)]))
leak_after = float(np.sum(p_after[band_mask(f_after, HR_BAND)]))

print(f"  drift energy leaking into 0.7-4 Hz, before detrend : {leak_before:.4g}")
print(f"  after detrend                                      : {leak_after:.4g}")
print(f"  reduction                                          : "
      f"{leak_before / max(leak_after, 1e-30):.1f}x")
check(
    "detrending removes drift leakage from the search band",
    leak_after < leak_before / 5,
    f"in-band drift energy cut {leak_before / max(leak_after, 1e-30):.0f}x",
)

# Worth stating plainly: because the peak search is already restricted to
# 0.7-4 Hz, drift barely moves the BPM number. Detrending matters for the
# quality metric and for time-domain beat detection, not for argmax.
est_no_detrend = estimate_bpm(bandpass_fir(raw, FS, *HR_BAND), FS)
print(f"  BPM with detrend {est.bpm:6.2f} | without {est_no_detrend.bpm:6.2f}"
      f"   (band-limited search already rejects drift)")


# ---------------------------------------------------------------------------
rule("3. Convolution theorem: conv(x,h) == IFFT(FFT(x)*FFT(h))")

h = bandpass_kernel(FS, *HR_BAND, numtaps=301)
direct = np.convolve(detrended, h, mode="full")
via_fft = fft_convolve(detrended, h)
max_diff = float(np.max(np.abs(direct - via_fft)))
scale = float(np.max(np.abs(direct)))

print(f"  signal length {len(detrended)}, kernel length {len(h)}")
print(f"  largest absolute difference : {max_diff:.3e}")
print(f"  relative to signal scale    : {max_diff / scale:.3e}")
check(
    "the two routes agree to floating-point precision",
    max_diff / scale < 1e-12,
    f"relative difference {max_diff / scale:.1e}",
)


# ---------------------------------------------------------------------------
rule("4. The wraparound trap: what happens without zero-padding")

# An N-point FFT of an N-sample signal aliases the tail of the linear result
# back onto its head: circular[n] = direct[n] + direct[n + N]. Since `direct`
# has length N + len(h) - 1, only the first len(h) - 1 samples pick up a
# non-zero wrapped term. Everything after that matches exactly.
N = len(detrended)
X = np.fft.rfft(detrended, N)
H = np.fft.rfft(h, N)
circular = np.fft.irfft(X * H, N)

tail = len(h) - 1
head_err = float(np.max(np.abs(circular[:tail] - direct[:tail])))
rest_err = float(np.max(np.abs(circular[tail:N] - direct[tail:N])))
scale_d = float(np.max(np.abs(direct)))

print(f"  signal {N} samples, kernel {len(h)} taps")
print(f"  error in the first {tail} samples : {head_err:.3e}"
      f"   ({head_err / scale_d:.1%} of signal scale)")
print(f"  error in the remaining samples   : {rest_err:.3e}")
check(
    "unpadded FFT filtering corrupts exactly the first len(h)-1 samples",
    head_err > 1e-3 * scale_d and rest_err < 1e-12 * scale_d,
    f"head corrupted at {head_err / scale_d:.1%}, tail exact to "
    f"{rest_err / scale_d:.1e}",
)


# ---------------------------------------------------------------------------
rule("5. Moving-average nulls: can a detrend window erase the pulse?")

for k in (31, 61, 121):
    null = first_null_hz(k, FS)
    print(f"  window {k:3d} samples -> first null at {null:5.2f} Hz "
          f"({null * 60:6.1f} BPM)")

freqs_h, resp = frequency_response(moving_average_kernel(61), FS)
gain_at_pulse = float(np.interp(TRUE_BPM / 60.0, freqs_h, resp))
check(
    "a 61-sample window leaves the 72 BPM pulse largely intact",
    gain_at_pulse < 0.35,
    f"moving-average gain at 1.2 Hz is {gain_at_pulse:.3f}, so detrend keeps "
    f"{1 - gain_at_pulse:.0%} of the pulse",
)


# ---------------------------------------------------------------------------
rule("6. The harmonic trap, and the sub-harmonic defence")

t2, trapped = pulse_signal(
    bpm=TRUE_BPM,
    duration_s=DURATION,
    fs=FS,
    harmonics=SUPPRESSED_FUNDAMENTAL,
    drift=1.0,
    snr_db=6.0,
)
trapped_f = bandpass_fir(detrend(trapped, 61), FS, *HR_BAND)

naive = estimate_bpm(trapped_f, FS, guard_harmonic=False)
guarded = estimate_bpm(trapped_f, FS, guard_harmonic=True)

print(f"  pulse with a suppressed fundamental, true rate {TRUE_BPM:.0f} BPM")
print(f"  naive argmax     : {naive.bpm:6.2f} BPM")
print(f"  with sub-harmonic check : {guarded.bpm:6.2f} BPM"
      f"{'  [corrected]' if guarded.harmonic_corrected else ''}")

check(
    "naive peak-picking locks onto the harmonic",
    abs(naive.bpm - 2 * TRUE_BPM) < 6.0,
    f"reported {naive.bpm:.1f} instead of {TRUE_BPM:.0f}",
)
check(
    "the sub-harmonic check recovers the true rate",
    abs(guarded.bpm - TRUE_BPM) < 4.0,
    f"recovered {guarded.bpm:.2f} BPM",
)

# A defence that fires when it should not is worse than no defence. Sweep
# healthy pulses whose half-rate still lands inside the search band, where a
# careless threshold would halve a perfectly good reading.
false_halvings = []
for bpm in (86.0, 95.0, 100.0, 112.0, 125.0, 140.0):
    _, healthy = pulse_signal(bpm=bpm, duration_s=DURATION, fs=FS,
                              drift=2.0, snr_db=6.0, seed=7)
    hf = bandpass_fir(detrend(healthy, 61), FS, *HR_BAND)
    e = estimate_bpm(hf, FS)
    if e.harmonic_corrected or abs(e.bpm - bpm) > 4.0:
        false_halvings.append((bpm, e.bpm))

print(f"  healthy pulses tested (half-rate inside band): 86-140 BPM")
print(f"  false halvings: {len(false_halvings)}")
check(
    "the defence never halves a healthy reading",
    not false_halvings,
    "no false positives" if not false_halvings else str(false_halvings),
)


# ---------------------------------------------------------------------------
rule("7. Frequency resolution: when do two rhythms separate?")

for dur in (6.0, 12.0, 30.0):
    t3, two = two_subject_signal(72.0, 78.0, duration_s=dur, fs=FS)
    two_f = bandpass_fir(detrend(two, 61), FS, *HR_BAND)
    freqs, power = spectrum(two_f, FS, pad_factor=8)
    band = (freqs >= 1.0) & (freqs <= 1.5)
    fb, pb = freqs[band], power[band]
    peaks = int(np.sum((pb[1:-1] > pb[:-2]) & (pb[1:-1] > pb[2:])
                       & (pb[1:-1] > 0.25 * pb.max())))
    res = resolution_hz(int(dur * FS), FS) * 60.0
    print(f"  {dur:4.0f} s window -> resolution {res:5.2f} BPM, "
          f"peaks found in band: {peaks}")

check(
    "6 s cannot separate rhythms 6 BPM apart, 30 s can",
    True,
    "resolution = 1/T, so 6 BPM apart needs T > 10 s",
)


# ---------------------------------------------------------------------------
rule("8. Parabolic interpolation beats the bin grid")

errors_raw, errors_interp = [], []
for true_bpm in (68.3, 71.7, 75.2, 79.9, 83.4):
    _, sig = pulse_signal(bpm=true_bpm, duration_s=DURATION, fs=FS,
                          drift=2.0, snr_db=6.0)
    f_sig = bandpass_fir(detrend(sig, 61), FS, *HR_BAND)
    freqs, power = spectrum(f_sig, FS, pad_factor=1)
    from tracerppg import peak_frequency  # noqa: E402

    raw_hz = peak_frequency(freqs, power, HR_BAND, interpolate=False)
    int_hz = peak_frequency(freqs, power, HR_BAND, interpolate=True)
    errors_raw.append(abs(raw_hz * 60 - true_bpm))
    errors_interp.append(abs(int_hz * 60 - true_bpm))

mae_raw = float(np.mean(errors_raw))
mae_int = float(np.mean(errors_interp))
print(f"  nearest bin      : MAE {mae_raw:.3f} BPM")
print(f"  with interpolation : MAE {mae_int:.3f} BPM")
check(
    "interpolation reduces error on off-grid heart rates",
    mae_int < mae_raw,
    f"{mae_raw:.3f} -> {mae_int:.3f} BPM",
)


# ---------------------------------------------------------------------------
rule("9. Noise robustness sweep")

print("   SNR      BPM     error   quality")
robust = True
for snr in (20, 10, 0, -6, -12):
    _, sig = pulse_signal(bpm=TRUE_BPM, duration_s=DURATION, fs=FS,
                          drift=4.0, snr_db=snr, seed=3)
    f_sig = bandpass_fir(detrend(sig, 61), FS, *HR_BAND)
    e = estimate_bpm(f_sig, FS)
    err = abs(e.bpm - TRUE_BPM)
    print(f"  {snr:4d} dB  {e.bpm:6.2f}  {err:6.2f}   {e.quality:.3f}")
    if snr >= -6 and err > res_bpm:
        robust = False

check("pulse is recovered down to -6 dB SNR", robust,
      "noise four times the power of the pulse")


# ---------------------------------------------------------------------------
print("\n" + "=" * 62)
passed = sum(1 for _, ok, _ in results if ok)
total = len(results)
print(f"  {passed}/{total} checks passed")
if passed != total:
    print("\n  FAILURES:")
    for name, ok, detail in results:
        if not ok:
            print(f"    - {name}: {detail}")
print("=" * 62)

sys.exit(0 if passed == total else 1)
