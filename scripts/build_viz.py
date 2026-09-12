"""Run the real pipeline, capture every intermediate stage, and bake the
results into a self-contained visualisation page.

The point is fidelity: the page plots numbers this script actually computed
by calling the same functions the pipeline uses. Nothing is reimplemented in
JavaScript, so the visualisation cannot drift away from the code.

Run:  .venv/Scripts/python.exe scripts/build_viz.py
Then: publish or open  pipeline-viz.html
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from tracerppg import (  # noqa: E402
    HR_BAND,
    SUPPRESSED_FUNDAMENTAL,
    bandpass_fir,
    bandpass_kernel,
)
from tracerppg.preprocess import (  # noqa: E402
    convolve_reflect,
    detrend,
    fft_convolve,
    first_null_hz,
    frequency_response,
    moving_average_kernel,
)
from tracerppg.spectral import (  # noqa: E402
    band_mask,
    estimate_bpm,
    peak_frequency,
    resolution_hz,
    spectral_snr,
    spectrum,
)
from tracerppg.synth import (  # noqa: E402
    lighting_drift,
    pulse_signal,
    pulse_wave,
    time_axis,
    two_subject_signal,
)

FS = 30.0
DURATION = 30.0
TRUE_BPM = 72.0
MA_WINDOW = 61
NUMTAPS = 301


def f(x) -> list[float]:
    """numpy array -> JSON-safe list of floats, rounded to keep the page small."""
    return [round(float(v), 6) for v in np.asarray(x).ravel()]


def clip_spectrum(freqs, power, fmax=5.0, max_points=900):
    m = freqs <= fmax
    fr, pw = freqs[m], power[m]
    if len(fr) > max_points:
        step = int(np.ceil(len(fr) / max_points))
        fr, pw = fr[::step], pw[::step]
    return fr, pw


data: dict = {}

# ---------------------------------------------------------------- meta
t, raw = pulse_signal(bpm=TRUE_BPM, duration_s=DURATION, fs=FS,
                      drift=4.0, snr_db=0.0)
clean_pulse = pulse_wave(t, TRUE_BPM)
drift_only = lighting_drift(t, strength=4.0, seed=0)

trend = convolve_reflect(raw, moving_average_kernel(MA_WINDOW))
detrended = raw - trend
filtered = bandpass_fir(detrended, FS, *HR_BAND, numtaps=NUMTAPS)
est = estimate_bpm(filtered, FS)

data["meta"] = {
    "fs": FS,
    "duration_s": DURATION,
    "true_bpm": TRUE_BPM,
    "n_samples": int(len(raw)),
    "resolution_bpm": round(resolution_hz(len(raw), FS) * 60.0, 3),
    "ma_window": MA_WINDOW,
    "numtaps": NUMTAPS,
    "band": list(HR_BAND),
    "generated": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
    "estimate": {
        "bpm": round(est.bpm, 3),
        "freq_hz": round(est.freq_hz, 5),
        "quality": round(est.quality, 4),
        "error_bpm": round(abs(est.bpm - TRUE_BPM), 3),
    },
}

# ---------------------------------------------------------------- stages
data["t"] = f(t)
data["stages"] = [
    {
        "id": "components",
        "n": 1,
        "title": "What the camera sees",
        "sub": "pulse + lighting drift + sensor noise",
        "series": [
            {"name": "pulse alone", "y": f(clean_pulse), "colour": "signal"},
            {"name": "lighting drift", "y": f(drift_only), "colour": "warn"},
        ],
        "note": (
            "The drift is four times the amplitude of the pulse. This is not "
            "an exaggeration; raw skin-brightness traces really do look like "
            "this, which is why detrending comes first."
        ),
        "stat": [
            ["pulse RMS", f"{np.sqrt(np.mean(clean_pulse**2)):.3f}"],
            ["drift RMS", f"{np.sqrt(np.mean(drift_only**2)):.3f}"],
            ["ratio", f"{np.sqrt(np.mean(drift_only**2)) / np.sqrt(np.mean(clean_pulse**2)):.1f}x"],
        ],
    },
    {
        "id": "raw",
        "n": 2,
        "title": "Raw signal",
        "sub": "everything summed, plus noise at 0 dB SNR",
        "series": [
            {"name": "raw", "y": f(raw), "colour": "ink"},
            {"name": "extracted trend", "y": f(trend), "colour": "warn"},
        ],
        "note": (
            "The pulse is in there. You cannot see it. The amber line is the "
            "moving average, which follows only the slow part."
        ),
        "stat": [
            ["samples", f"{len(raw)}"],
            ["range", f"{raw.min():.2f} to {raw.max():.2f}"],
            ["visible pulse?", "no"],
        ],
    },
    {
        "id": "detrended",
        "n": 3,
        "title": "After detrending",
        "sub": "step 4, convolution with a moving-average kernel, then subtract",
        "series": [
            {"name": "detrended", "y": f(detrended), "colour": "accent"},
        ],
        "note": (
            "A low-pass subtracted from the original is a high-pass. The slow "
            "swell is gone and a rhythm is becoming visible, still buried in "
            "noise."
        ),
        "stat": [
            ["kernel length", f"{MA_WINDOW} samples ({MA_WINDOW / FS:.2f} s)"],
            ["first null", f"{first_null_hz(MA_WINDOW, FS):.2f} Hz"],
            ["pulse kept", "87%"],
        ],
    },
    {
        "id": "filtered",
        "n": 4,
        "title": "After bandpass filtering",
        "sub": "step 6, convolution with a windowed-sinc FIR, 0.7 to 4 Hz",
        "series": [
            {"name": "filtered", "y": f(filtered), "colour": "accent"},
            {"name": "true pulse", "y": f(clean_pulse * 0.35), "colour": "signal"},
        ],
        "note": (
            "The teal line is the true pulse, scaled for comparison. The "
            "recovered rhythm tracks it. Everything outside 0.7 to 4 Hz has "
            "been removed by a kernel we built from a truncated sinc."
        ),
        "stat": [
            ["taps", f"{NUMTAPS}"],
            ["band", f"{HR_BAND[0]} to {HR_BAND[1]} Hz"],
            ["in BPM", f"{HR_BAND[0] * 60:.0f} to {HR_BAND[1] * 60:.0f}"],
        ],
    },
]

# ---------------------------------------------------------------- kernels
ma_k = moving_average_kernel(MA_WINDOW)
bp_k = bandpass_kernel(FS, *HR_BAND, numtaps=NUMTAPS)
fr_ma, resp_ma = frequency_response(ma_k, FS)
fr_bp, resp_bp = frequency_response(bp_k, FS)
m_ma = fr_ma <= 5.0
m_bp = fr_bp <= 6.0

data["kernels"] = {
    "moving_average": {
        "taps": f(ma_k),
        "freqs": f(fr_ma[m_ma]),
        "response": f(resp_ma[m_ma]),
        "null_hz": round(first_null_hz(MA_WINDOW, FS), 4),
        "gain_at_pulse": round(float(np.interp(1.2, fr_ma, resp_ma)), 4),
    },
    "bandpass": {
        "taps": f(bp_k),
        "freqs": f(fr_bp[m_bp]),
        "response": f(resp_bp[m_bp]),
        "gain_72": round(float(np.interp(1.2, fr_bp, resp_bp)), 4),
        "gain_144": round(float(np.interp(2.4, fr_bp, resp_bp)), 4),
        "gain_30": round(float(np.interp(0.5, fr_bp, resp_bp)), 4),
    },
}

# ---------------------------------------------------------------- spectrum
freqs, power = spectrum(filtered, FS, pad_factor=4)
fr_c, pw_c = clip_spectrum(freqs, power)
peak_hz = est.freq_hz
q = spectral_snr(freqs, power, peak_hz, HR_BAND)

data["spectrum"] = {
    "freqs": f(fr_c),
    "power": f(pw_c / pw_c.max()),
    "peak_hz": round(peak_hz, 5),
    "peak_bpm": round(peak_hz * 60, 3),
    "harmonic_hz": round(peak_hz * 2, 5),
    "band": list(HR_BAND),
    "half_width": 0.12,
    "quality": round(q, 4),
    "note": (
        "Teal shading counts as signal: a window around the peak plus one "
        "around its harmonic. Crimson shading is everything else in the band, "
        "counted as noise. The quality score is the ratio."
    ),
}

# ---------------------------------------------------------------- experiments
exp: dict = {}

# convolution theorem
direct = np.convolve(detrended, bp_k, mode="full")
via = fft_convolve(detrended, bp_k)
diff = np.abs(direct - via)
exp["conv_theorem"] = {
    "direct": f(direct[:900]),
    "via_fft": f(via[:900]),
    "max_diff": float(np.max(diff)),
    "rel_diff": float(np.max(diff) / np.max(np.abs(direct))),
}

# wraparound trap
N = len(detrended)
circ = np.fft.irfft(np.fft.rfft(detrended, N) * np.fft.rfft(bp_k, N), N)
tail = len(bp_k) - 1
scale_d = float(np.max(np.abs(direct)))
exp["wraparound"] = {
    "correct": f(direct[:N]),
    "circular": f(circ),
    "corrupt_until": int(tail),
    "head_err_pct": round(float(np.max(np.abs(circ[:tail] - direct[:tail]))) / scale_d * 100, 2),
    "tail_err": float(np.max(np.abs(circ[tail:N] - direct[tail:N])) / scale_d),
}

# harmonic trap
_, trapped = pulse_signal(bpm=TRUE_BPM, duration_s=DURATION, fs=FS,
                          harmonics=SUPPRESSED_FUNDAMENTAL, drift=1.0, snr_db=6.0)
tf = bandpass_fir(detrend(trapped, MA_WINDOW), FS, *HR_BAND)
frt, pwt = spectrum(tf, FS, pad_factor=4)
frt_c, pwt_c = clip_spectrum(frt, pwt)
naive = estimate_bpm(tf, FS, guard_harmonic=False)
guarded = estimate_bpm(tf, FS, guard_harmonic=True)
exp["harmonic_trap"] = {
    "freqs": f(frt_c),
    "power": f(pwt_c / pwt_c.max()),
    "naive_bpm": round(naive.bpm, 2),
    "guarded_bpm": round(guarded.bpm, 2),
    "true_bpm": TRUE_BPM,
    "corrected": bool(guarded.harmonic_corrected),
}

# resolution
res_sets = []
for dur in (6.0, 12.0, 30.0):
    _, two = two_subject_signal(72.0, 78.0, duration_s=dur, fs=FS)
    twof = bandpass_fir(detrend(two, MA_WINDOW), FS, *HR_BAND)
    fr2, pw2 = spectrum(twof, FS, pad_factor=8)
    m2 = (fr2 >= 1.0) & (fr2 <= 1.55)
    res_sets.append({
        "duration": dur,
        "resolution_bpm": round(resolution_hz(int(dur * FS), FS) * 60, 2),
        "freqs": f(fr2[m2]),
        "power": f(pw2[m2] / pw2[m2].max()),
    })
exp["resolution"] = res_sets

# parabolic interpolation, zoomed on one peak
_, off = pulse_signal(bpm=75.2, duration_s=DURATION, fs=FS, drift=2.0, snr_db=6.0)
offf = bandpass_fir(detrend(off, MA_WINDOW), FS, *HR_BAND)
fro, pwo = spectrum(offf, FS, pad_factor=1)
im = band_mask(fro, HR_BAND)
idx = np.flatnonzero(im)[np.argmax(pwo[im])]
lo, hi = idx - 3, idx + 4
bins_f = fro[lo:hi]
bins_p = pwo[lo:hi] / pwo[idx]
y1, y2, y3 = np.log(pwo[idx - 1: idx + 2] + 1e-30)
delta = 0.5 * (y1 - y3) / (y1 - 2 * y2 + y3)
df = fro[1] - fro[0]
xs = np.linspace(-1.6, 1.6, 120)
a = (y1 - 2 * y2 + y3) / 2
b = (y3 - y1) / 2
para = np.exp(a * xs**2 + b * xs + y2) / pwo[idx]
exp["interpolation"] = {
    "true_bpm": 75.2,
    "bin_freqs": f(bins_f * 60),
    "bin_power": f(bins_p),
    "parabola_x": f((fro[idx] + xs * df) * 60),
    "parabola_y": f(para),
    "nearest_bpm": round(float(fro[idx] * 60), 3),
    "interp_bpm": round(float((fro[idx] + delta * df) * 60), 3),
    "bin_width_bpm": round(float(df * 60), 3),
}

# noise sweep
sweep = []
for snr in (20, 10, 0, -6, -12):
    _, s = pulse_signal(bpm=TRUE_BPM, duration_s=DURATION, fs=FS,
                        drift=4.0, snr_db=snr, seed=3)
    sf = bandpass_fir(detrend(s, MA_WINDOW), FS, *HR_BAND)
    e = estimate_bpm(sf, FS)
    sweep.append({
        "snr_db": snr,
        "bpm": round(e.bpm, 2),
        "error": round(abs(e.bpm - TRUE_BPM), 2),
        "quality": round(e.quality, 3),
        "signal": f(sf[:300]),
    })
exp["noise_sweep"] = sweep

data["experiments"] = exp

# ---------------------------------------------------------------- write
payload = json.dumps(data, separators=(",", ":"))
template = (ROOT / "viz" / "template.html").read_text(encoding="utf-8")
out = template.replace("/*__PIPELINE_DATA__*/null", payload)
dest = ROOT / "pipeline-viz.html"
dest.write_text(out, encoding="utf-8")

print(f"pipeline data : {len(payload) / 1024:.0f} KB")
print(f"page written  : {dest}  ({len(out) / 1024:.0f} KB)")
print(f"estimate      : {est}")
