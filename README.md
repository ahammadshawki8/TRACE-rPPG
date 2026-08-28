# TRACE-rPPG

**Tone-stratified Robustness Across Compressed Encodings**

Contactless heart-rate measurement from ordinary face video, built entirely from
Fourier series, the Fourier transform, and convolution. No trained model appears
anywhere in the estimation path.

The research question: **does video compression amplify the skin-tone accuracy
gap in remote photoplethysmography?**

Both halves of that question are separately well established. Darker skin
produces a weaker pulse signal because melanin absorbs more light. Video codecs
discard colour detail preferentially, which is exactly where the pulse signal
lives. Nobody has measured whether the second makes the first worse.

---

## Status

| Step | State |
|---|---|
| 1. Synthetic verification | **done**, 12/12 checks passing |
| 2. Ground-truth PPG waveform | not started |
| 3. Recorded video | not started |
| 4. CHROM / POS | not started |
| 5. Quality metric and fusion | partial (metric done) |
| 6. Compression grid | not started |

## Quick start

```bash
python -m venv .venv
.venv/Scripts/python.exe -m pip install numpy scipy

# verify the mathematics against a signal whose answer we know
.venv/Scripts/python.exe scripts/step1_synthetic.py

# export real pipeline data and rebuild the visualisation
.venv/Scripts/python.exe scripts/build_viz.py
```

`scripts/step1_synthetic.py` recovers **72.07 BPM** from a synthetic trace where
lighting drift is four times the pulse amplitude and noise sits at equal power
to the pulse. It holds to within 0.27 BPM at −6 dB SNR, where the noise carries
four times the pulse's power.

## Layout

```
src/tracerppg/
  synth.py       synthetic pulses with known ground truth
  preprocess.py  detrending, hand-built windowed-sinc FIR, zero-phase filtering
  spectral.py    windowed FFT, parabolic peak location, quality metric
scripts/
  step1_synthetic.py   acceptance checks against known answers
  build_viz.py         exports pipeline data into the visualisation page
viz/template.html      presentation layer for the visualisation
Idea/                  project plan, novelty assessment, pitch materials
Lesson/                seven interactive lessons on the underlying theory
pipeline-viz.html      generated; every trace is real pipeline output
```

## What the pipeline does

1. Average skin-pixel intensity per frame into R, G, B time series
2. **Detrend** by convolution with a moving-average kernel, then subtract
   (a low-pass subtracted from the original is a high-pass)
3. **Bandpass** 0.7 to 4 Hz with a windowed-sinc FIR built from a truncated
   sinc rather than pulled from a library
4. **FFT**, then locate the peak between bins by parabolic interpolation
5. Check the sub-harmonic, so a suppressed fundamental does not cause the
   system to report double the true rate
6. Compute a **quality score** directly from the FFT output as in-band peak
   power over total in-band power
7. Fuse green-channel, CHROM and POS weighted by that score, frame by frame

Steps 2, 3 are convolution. Steps 4, 6 are the Fourier transform. Step 5 falls
out of Fourier series: a sharp pulse waveform necessarily produces harmonics.

## Measured results so far

| Check | Result |
|---|---|
| BPM recovery through 4x drift, 0 dB noise | 72.07 BPM, error 0.07 |
| Convolution theorem, direct vs FFT route | agree to 4.3e-16 relative |
| Parabolic interpolation, 5 off-grid rates | MAE 0.420 to 0.022 BPM |
| Unpadded FFT filtering | corrupts first len(h)−1 samples at 82% of scale |
| Detrending | cuts in-band drift leakage 71x |
| Sub-harmonic defence | recovers 71.99 from a trap, 0 false positives 86–140 BPM |
| Noise floor | pulse recovered to −6 dB SNR |

## Lessons

Seven interactive lessons covering the theory, each bilingual in English and
Bangla:

| Tier | Topic |
|---|---|
| 0 | Complex numbers, Euler, the winding machine |
| 1 | Fourier series, convolution, sampling, the DFT |
| 2 | Filter design and zero-phase filtering |
| 3 | Parseval, Welch, the quality metric |
| 4 | Beat timing, uneven sampling, LF/HF |
| 5 | Bland-Altman, bias, chroma subsampling |
| 6 | Interaction effects, experiment design, statistical power |

## Course context

Signals & Systems. Fourier series, Fourier transform, convolution.

## Note on scope

The compression-by-skin-tone result is a measurement, not a claim in advance.
If the accuracy curves for lighter and darker skin fan apart as bitrate falls,
the disadvantage compounds. If they stay parallel, compression is
demographically neutral. Both outcomes are reportable and neither has been
measured.

Any heart-rate-variability output is a wellness indicator, not a diagnosis.
