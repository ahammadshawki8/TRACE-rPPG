# TRACE-rPPG

**Tone-stratified Robustness Across Compressed Encodings**

Contactless heart rate from ordinary face video, built from Fourier series, the
Fourier transform and convolution. No trained model appears anywhere in the
estimation path.

The research question: **does video compression amplify the skin-tone accuracy
gap in remote photoplethysmography (rPPG)?** Darker skin produces a weaker pulse
signal because melanin absorbs more light; video codecs discard exactly the
colour detail where that pulse lives. Both effects are documented separately.
Their interaction had not been measured.

> Current results come from a **simulated pilot**: real codecs, a real face
> detector and the real pipeline, applied to rendered faces whose skin-tone
> physics is modelled. The same code runs unchanged on recorded participants
> (`deliverables/data_collection_protocol.md`).

## Status

| Tier | What | State |
|---|---|---|
| T0 | Synthetic verification of the mathematics | done, 12/12 |
| T1 | Dataset loaders, ground truth, face-video simulator | done, 8/8 |
| T2 | Face tracking (Haar + phase correlation), RGB traces | done, 6/6 |
| T3 | Green, ICA, CHROM, POS | done, 7/7 |
| T4 | TRACE fusion (v1 failed held-out; v2 with a pulse-blind artifact reference) | done, 8/8 |
| T5 | Compression harness with lossless controls | done, 8/8 |
| T6 | Neural baselines (PhysNet, FactorizePhys; pretrained, inference only) | done, 9/9 |
| T7 | Full grid, interaction statistics, figures | done on the simulated pilot (36 subjects, 23 conditions, 11 methods) |
| T8 | Own data collection | protocol and consent form ready; recording not started |
| T9 | HRV and LF/HF (the second Fourier transform) | done, 11/11 |
| T10 | Live demo and TRACE Night Signal | done; live rPPG monitor, guided camera rBCG, pulse-wave stealth horror mission and replay |
| T11 | Extended abstract, poster, course report | drafts generated from results, see `deliverables/` |

`CLAUDE.md` is the detailed project memory: every measured number, every
decision, and every failed attempt.

## What the simulated pilot found

- Compression did **not** widen the skin-tone gap in mean error: darker skin was
  already near its failure plateau at every bitrate, and compression pulled
  lighter skin down to meet it.
- At the signal level the mechanism does favour the hypothesis: on a still face,
  H.264 at 100 kbps left pulse fidelity at 0.46 for lighter skin and about 0 for
  darker skin (0.92 and 0.84 lossless).
- TRACE (quality-weighted fusion with a pulse-blind artifact mask) had the lowest
  error of all methods, classical or neural, on lossless and 400 kbps video, and
  halved the lossless skin-tone gap of POS.

These are simulated; the real-data study is the next step. Details and every
number are in `CLAUDE.md` and `deliverables/`.

## Quick start

```bash
python -m venv .venv
.venv/Scripts/python.exe -m pip install -r requirements.txt

# acceptance checks, one per tier
.venv/Scripts/python.exe scripts/step1_synthetic.py      # T0 mathematics
.venv/Scripts/python.exe scripts/step2_ground_truth.py   # T1
.venv/Scripts/python.exe scripts/step3_video.py          # T2
.venv/Scripts/python.exe scripts/step4_methods.py        # T3
.venv/Scripts/python.exe scripts/step5_fusion.py         # T4
.venv/Scripts/python.exe scripts/step6_compression.py    # T5
.venv/Scripts/python.exe scripts/step7_hrv.py            # T9
.venv/Scripts/python.exe scripts/step8_neural.py         # T6 (needs .venv-nn)
.venv/Scripts/python.exe scripts/step9_camera_bcg.py     # T12 guided rBCG gate

# the experiment: simulated pilot, then statistics, figures and documents
.venv/Scripts/python.exe scripts/run_grid.py --max-subjects 36
.venv/Scripts/python.exe scripts/analyze_grid.py
.venv/Scripts/python.exe scripts/build_app_assets.py
.venv/Scripts/python.exe scripts/build_deliverables.py --pdf

# on real recordings in the UBFC layout, which may live on another drive
set TRACE_UBFC_DIR=D:/datasets/ubfc                    # the acceptance scripts read this
.venv/Scripts/python.exe scripts/make_labels_template.py D:/datasets/ubfc   # then rate each subject
.venv/Scripts/python.exe scripts/run_grid.py --dataset D:/datasets/ubfc --tag ubfc --work-root D:/trace-scratch
.venv/Scripts/python.exe scripts/analyze_grid.py --tag ubfc

# live demo and pulse-aware stealth game (camera or synthetic pulse), then open http://127.0.0.1:8000
.venv/Scripts/python.exe app/server.py
```

Neural baselines live in a separate environment so the core stays classical:

```bash
python -m venv .venv-nn
.venv-nn/Scripts/python.exe -m pip install torch --index-url https://download.pytorch.org/whl/cpu
.venv-nn/Scripts/python.exe -m pip install numpy scipy "opencv-python-headless<5" neurokit2
git clone --depth 1 https://github.com/ubicomplab/rPPG-Toolbox third_party/rPPG-Toolbox
```

Requirements: Python 3.14, ffmpeg with libx264, libx265 and libvpx on the path.

Subject folders are found recursively, so a download keeps its own nesting.
Public datasets ship no skin-type labels, so a skin-tone comparison needs a
`fitzpatrick.csv` (subject, type) beside the data; `make_labels_template.py`
writes the blank file. Keep `--work-root` on the same drive as a large dataset:
each subject's encodes are transient but large.

## Layout

```
src/tracerppg/      the pipeline package
  synth.py            synthetic pulses and heart rhythms with known answers
  preprocess.py       detrending, hand-built FIR, zero-phase filtering
  spectral.py         windowed FFT, interpolation, quality, harmonic defence
  datasets.py         UBFC loaders, uniform resampling, windows, ground truth
  simulate.py         face-video simulator with controllable melanin
  video.py, roi.py    ffmpeg decoding; Haar + phase-correlation tracking
  methods.py          green, ICA, CHROM, POS
  fusion.py           TRACE v1 and v2
  compress.py         codec conditions and the encoder wrapper
  hrv.py              beats, RR, SDNN, RMSSD, LF/HF
  metrics.py, stats.py  agreement metrics; the interaction model; power
  grid.py             the subject x condition x method experiment
scripts/            acceptance checks (stepN), grid, analysis, builders
app/                FastAPI live pipeline and TRACE Ghost Protocol game
  static/game.html  pixel-art stealth game and session replay
  static/game.js    game loop, pulse feedback controller UI, export
  biofeedback.py    baseline-relative, quality-gated feedback controller
src/tracerppg/mechanical.py  experimental camera rBCG feature tracking
deliverables/       poster, extended abstract, course report, data protocol
results/            frozen parameters, tables, figures (raw outputs gitignored)
Lesson/             seven bilingual lessons on the theory
Idea/               the original plan, novelty search and pitch materials
```

## What the pipeline does

1. Track the face (Haar initialisation, phase-correlation tracking) and
   average forehead and cheek skin into R, G, B traces
2. **Detrend** by convolution with a moving average, then subtract
3. Combine channels (green, CHROM, POS)
4. **Bandpass** 0.7 to 4 Hz with a windowed-sinc FIR built from a truncated sinc
5. **FFT**, then locate the peak between bins by parabolic interpolation
6. Check the sub-harmonic, so a suppressed fundamental does not double the rate
7. **TRACE**: score each method from its own spectrum, mask frequencies where a
   pulse-blind artifact reference has power, fuse, and flag low confidence
8. **HRV**: time each beat, resample the intervals, take a second Fourier
   transform for LF/HF

## Note on scope

The compression-by-skin-tone result is a measurement, not a claim made in
advance. If the error curves for lighter and darker skin fan apart as bitrate
falls, the disadvantage compounds; if they stay parallel, compression is
demographically neutral. Both outcomes are reportable.

Heart-rate variability output is a wellness indicator, never a diagnosis.
