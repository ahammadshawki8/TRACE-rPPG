# TRACE-rPPG: Tone-stratified Robustness Across Compressed Encodings
### Robust, video-compression-tolerant heart rate and HRV estimation from face video

**Course context:** Signals & Systems (Fourier Series, Fourier Transform, Convolution)
**Goal:** Contactless heart-rate/HRV measurement from face video, implemented rigorously enough to support a novel, quantified contribution: not a cloned tutorial demo.
**Project name:** TRACE-rPPG (Tone-stratified Robustness Across Compressed Encodings): a real-time system that dynamically weights and fuses multiple rPPG extraction methods (green-channel, CHROM, POS) based on a real-time signal-quality metric, stress-tested under real video-call degradation (Zoom/Google Meet), and extended beyond a raw BPM readout into an HRV/LF-HF autonomic-state indicator, optionally combined with fully client-side/on-device execution.

---

## 1. Project Summary

Remote photoplethysmography (rPPG) extracts a person's heart rate (and potentially HRV/respiration rate) from ordinary video of their face, by detecting the tiny, invisible-to-the-eye color changes in skin caused by blood volume pulsing with each heartbeat. The entire pipeline is built from exactly the three tools this course teaches:

| Course topic | Where it shows up in the pipeline |
|---|---|
| **Fourier Series** | The pulse signal is quasi-periodic; framed as a fundamental (heart-rate frequency) + harmonics |
| **Fourier Transform (FFT)** | Converting the extracted RGB time-series into the frequency domain to find the dominant heart-rate frequency |
| **Convolution** | Detrending (moving-average kernel), bandpass filtering (isolating 0.7–4 Hz / 42–240 BPM), and demonstrating the convolution theorem (time-domain convolution ≡ frequency-domain multiplication) |

**Real-world value:** contactless vital-sign monitoring for telehealth, NICU (fragile neonatal skin can't tolerate contact sensors), fitness tracking, driver drowsiness/health monitoring, and (per recent literature) deepfake/liveliness detection.

**Core method purity:** this project is deliberately built as a classical, interpretable signal-processing system, not a machine-learning system that happens to reference Fourier theory in passing. Fourier Series, Fourier Transform, and Convolution are the backbone of the pipeline: every physiological number the system outputs (BPM, signal-quality weighting, LF/HF ratio) is produced directly by an FFT or a convolution operation, with no trained/learned model anywhere in the estimation path. See **Section 17** for a full stage-by-stage breakdown of exactly where each of the three theories is applied and how much of the architecture they account for.

---

## 2. Why This Project (and the honest risk assessment)

- rPPG is **not obscure**: there's a well-known open-source repo (`webcam-pulse-detector`) and several tutorials, so with ~90 teams, a few others may land on the same base idea.
- However, **most student implementations are shallow**: clone a repo, show a live number, stop. Almost none do rigorous quantified validation, motion-robustness comparison, or push past the naive green-channel method.
- **Decision:** commit to rPPG, but go deep: pick a genuine novelty angle (Section 5) and back it with quantified validation (Section 6) so the project is clearly differentiated even if other teams pick the same base topic.

### Difficulty assessment (given strong Python/AI/web dev skills)

| Component | Difficulty | Notes |
|---|---|---|
| Face detection + ROI tracking | Easy | MediaPipe Face Mesh / OpenCV |
| Green-channel + FFT baseline | Easy | Basic starting point |
| CHROM / POS chrominance combination | Easy–Moderate | Linear algebra on RGB signals, 1–2 days after reading the paper |
| Detrending + bandpass filtering (convolution) | Easy | scipy.signal |
| Motion-robust HRV extraction (precise beat timing) | Moderate | Peak detection + interpolation is fiddly to get accurate |
| Quantitative validation vs. ground truth | Moderate | Main friction point: solved via public datasets (Section 6) |
| Real-time live demo UI | Easy (your strength) | Web dev skills make this a differentiator, not a challenge |

**Overall estimate:** ~2–3 weeks for a solid, quantitatively validated system; longer if pursuing the full novel-contribution angle with a proper write-up.

---

## 3. Required Reading: Research Papers

### Must-read (core algorithm lineage, read in this order)

1. **Verkruysse, Svaasand & Nelson (2008)**: *"Remote plethysmographic imaging using ambient light"*, Optics Express.
   Foundational paper proving ambient light + ordinary camera is enough to detect blood-volume pulse. Short, good project-intro material.

2. **Poh, McDuff & Picard (2010)**: *"Non-contact, automated cardiac pulse measurements using video imaging and blind source separation"*, Optics Express.
   First practical algorithm (ICA on RGB channels). This is your "naive baseline" to beat.

3. **de Haan & Jeanne (2013)**: *"Robust Pulse Rate From Chrominance-Based rPPG"*, IEEE Trans. Biomed. Eng., 60(10), 2878–2886.
   The **CHROM** method. Reports rPPG reaching ~92% agreement with contact PPG, with RMSE/std roughly 2× better than ICA-based (blind source separation) methods. Explains *why* naive green-channel fails under motion.

4. **Wang, den Brinker, Stuijk & de Haan (2017)**: *"Algorithmic Principles of Remote-PPG"*, IEEE Trans. Biomed. Eng., 64(7), 1479–1491. DOI: 10.1109/TBME.2016.2609282
   The **POS** method: and more importantly, builds a unifying mathematical model of skin-reflection optics/physiology that explains *why* green-channel, ICA, CHROM, and POS make the choices they do.
   **⭐ Single most important paper: read this one most carefully.**

### Strongly recommended (motion robustness + HRV rigor)

5. **Li, Chen, Zhao, Pietikäinen et al. (2014)**: *"Remote Heart Rate Measurement from Face Videos Under Realistic Situations"*, CVPR.
   Face tracking + Normalized Least-Mean-Square adaptive filtering to counter illumination/motion disturbances; substantially outperforms prior methods.

6. **de Haan & van Leest (2014)**: *"Improved motion robustness of remote-PPG by using the blood volume pulse signature"*, Physiological Measurement, 35(9), 1913–1922.
   The **PBV** method: useful for a 3-way comparison table (CHROM vs POS vs PBV).

7. **Balakrishnan, Durand & Guttag (2013)**: *"Detecting Pulse from Head Motion in Video"*, CVPR.
   Alternate approach using head motion instead of color: good comparison/discussion point.

### Optional / supporting

- **Wang, Stuijk & de Haan (2015)**: *"A novel algorithm for remote photoplethysmography: spatial subspace rotation"* (2SR method), IEEE TBME 63(9), 1974–1984.
- **Task Force of ESC/NASPE (1996)**: *"Heart rate variability: standards of measurement, physiological interpretation and clinical use"*: the standard clinical reference if you extend into HRV metrics.
- **Boccignone et al. (2022)**: *"pyVHR: a Python framework for remote photoplethysmography"*, PeerJ Computer Science, DOI: 10.7717/peerj-cs.929: describes the design of a full benchmarking framework; useful as a methodology reference for how to structure rigorous comparisons.

### Directly supporting Section 5.1 (video-call / compression robustness)

- **Gudi, Bittner & van Gemert (2020)**: *"Real-time Webcam Heart-Rate and Variability Estimation with Clean Ground Truth for Evaluation"*, Applied Sciences (MDPI). Contains an explicit compression-vs-accuracy study on the PURE dataset across lossy codecs (H.264, H.265) and lossless formats (FFV1), showing H.265 gives the best accuracy/bitrate trade-off among lossy encodings. This is the closest existing precedent to your Section 5.1 experiment, use it to justify your codec choices and as a direct point of comparison for your own compression-degradation curves.
- **McDuff, Blackford & Estepp (2017)**: *"The impact of video compression on remote cardiac pulse measurement using imaging photoplethysmography"*, IEEE FG 2017. One of the first papers to systematically show that video compression measurably degrades rPPG signal quality: establishes that this is a recognized, citable problem, not something you're inventing from scratch.

### Directly supporting Section 5.2 (HRV / LF-HF diagnostic layer)

- **"Robust Heart Rate Variability Measurement from Facial Videos"** (WaveHRV): proposes a contactless HRV extraction pipeline (wavelet scattering transform + adaptive bandpass filtering + inter-beat-interval analysis) benchmarked on UBFC-rPPG, reporting MAE of about 10.5 ms for RMSSD and 6.15 ms for SDNN. This gives you a concrete target/reference accuracy to compare your own HRV metrics against.

### Directly supporting Section 10 (statistical validation rigor) and Section 11 (limitations/bias)

- **Dasari, Prakash, Jeni & Tucker (2021)**: *"Evaluation of biases in remote photoplethysmography methods"*, npj Digital Medicine 4:91, DOI: 10.1038/s41746-021-00462-z. Directly evaluates CHROM, POS, and other rPPG methods against an FDA-approved ground-truth PPG sensor (Masimo) **using Bland-Altman analysis**, across diverse skin tones, genders, and countries: this is the single best methodological template for your Section 10 statistical validation, and it also reports that traditional chrominance methods show substantially larger error on darker Fitzpatrick skin types, directly supporting the skin-tone limitation you should document in Section 11.
- **Nowara, McDuff & Veeraraghavan (2020)**: *"A meta-analysis of the impact of skin tone and gender on non-contact photoplethysmography measurements"*, CVPR Workshops 2020. Supporting citation for the skin-tone/gender bias discussion in Section 11.
- **Bland & Altman (1986)**: *"Statistical methods for assessing agreement between two methods of clinical measurement"*, The Lancet, 327(8476), 307–310. The foundational statistics paper defining the Bland-Altman method itself: worth citing directly when you introduce the technique in your Methods/Results section, since it's the standard citation for anyone using this analysis.

---

## 4. Existing Implementations / Repos / Websites (know these before you start: for reference, comparison, and to avoid "reinventing" a solved sub-problem)

| Name | Type | Link | Notes |
|---|---|---|---|
| **webcam-pulse-detector** | GitHub repo (Python, thearn) | github.com/thearn/webcam-pulse-detector | The most commonly cloned "cool DSP demo" repo: likely what other teams will find first. Good as a naive baseline, not as your submission. |
| **pyVHR** | GitHub + PyPI + published paper (phuselab/UniMi) | github.com/phuselab/pyVHR | Full research-grade framework implementing CHROM, POS, PBV, 2SR, ICA and more, with 10 dataset interfaces built in. Excellent for sanity-checking your own numbers and as a "related work" citation. |
| **rPPG-Toolbox** | GitHub (ubicomplab, NeurIPS 2023) | github.com/ubicomplab/rPPG-Toolbox | Modern deep-learning + classical rPPG benchmark toolbox; supports 7 standard datasets (SCAMPS, UBFC-rPPG, PURE, BP4D+, UBFC-Phys, MMPD, iBVP) with a unified loader. Good reference implementation to validate against. |
| **heartwave** | PyPI package | pypi.org/project/heartwave | Lightweight CLI tool, simple FFT-based approach, multi-person support. |
| **FastICA heart rate estimation** | GitHub | github.com/hmmo-O/Estimation-of-Heart-rate-using-FastICA | Simple ICA-based student implementation: useful as another baseline comparison point. |
| **Virtual-Heart-Rate-Monitor** | GitHub (student project) | github.com/23F3003917/Virtual-Heart-Rate-Monitor | Combines pyVHR + MediaPipe for real-time BPM overlay: shows what a "reasonably good but not deep" student project looks like; useful benchmark for how much further you need to go to stand out. |
| **HeartPy** | GitHub + PyPI (van Gent et al.) | github.com/paulvangentcom/heartrate_analysis_python | Published, widely-used Python toolkit for time-domain and frequency-domain heart rate/HRV analysis from noisy PPG/ECG signals. Directly useful for Section 5.2 (SDNN/RMSSD/pNN50 computation) rather than reimplementing peak-detection and HRV math from scratch; cite van Gent, Farah, van Nes & van Arem (2019), Transportation Research Part F, 66, 368–378. |
| **pyhrv** | GitHub (PGomes92) | github.com/PGomes92/pyhrv | Dedicated Python toolbox specifically for HRV analysis (time-domain, frequency-domain including LF/HF, and nonlinear metrics): a second reference implementation to cross-check your own LF/HF ratio calculation in Section 5.2 against. |

**Takeaway:** don't clone any of these as your submission. Use `webcam-pulse-detector` and the FastICA repo as your "naive baseline to beat," and `pyVHR`/`rPPG-Toolbox` as validation/cross-check tools and citation-worthy related work.

---

## 5. Novelty Angles (pick ONE as your headline contribution)

Calibration: the classical pipeline (green-channel → ICA → CHROM → POS) is thoroughly explored, and the current research frontier is deep learning (DeepPhys, PhysNet, RhythmFormer). Don't try to beat those. Realistic, defensible novelty at this level = **take a gap the literature mentions in passing but doesn't solve, and solve it properly with a rigorous experiment.**

### Option A: Privacy-preserving, fully in-browser real-time rPPG ⭐ (recommended: uniquely plays to your skill set)
Every existing implementation (webcam-pulse-detector, pyVHR, rPPG-Toolbox) runs server-side/Python. Building a version that runs **entirely client-side** (WebAssembly / Canvas / Web Audio API: video frames never leave the device) is underexplored because most people in this space are ML/Python researchers, not web engineers. Frames it as genuine privacy-preserving on-device health sensing: a real, current, defensible research narrative.

### Option B: Quantified skin-tone fairness gap + correction
Datasets like MMPD were built specifically because darker skin tones are known to reduce rPPG signal amplitude/accuracy. Most papers mention this as a limitation, not a solved problem. A rigorous fairness benchmark (accuracy broken down by Fitzpatrick skin type using MMPD) + testing a simple, explainable correction (adaptive per-channel gain normalization, or per-subject optimal channel combination) is a timely, socially relevant, and genuinely under-addressed contribution.

### Option C: Robustness under real-world video compression
All benchmark datasets use clean, uncompressed video. Real-world use (Zoom/Teams calls, compressed phone video) runs through codecs that specifically mangle the tiny color signal rPPG relies on (chroma subsampling). Systematically testing CHROM/POS degradation across compression levels, and testing whether a frequency-domain correction step recovers accuracy, is close to unexplored and has obvious real-world (telehealth) value.

### Option D: Signal-quality-adaptive fusion ⭐ (COMMITTED METHOD, now the TRACE fusion layer)
Instead of committing to one static method, dynamically weight/fuse green-channel, CHROM, and POS frame-by-frame based on a real-time signal-quality metric (motion magnitude via optical flow, illumination stability, per-method SNR estimate). Lightweight, fully classical (no deep learning required), and not the standard approach in the literature (most papers pick one method or replace the whole pipeline with a neural net). This uses the standard vocabulary of adaptive filtering (LMS/RLS, confidence-weighted fusion), so it reads as engineered methodology rather than a marketing label.

**Committed project: TRACE-rPPG (Tone-stratified Robustness Across Compressed Encodings).** The quality-adaptive fusion described above is its method; the compression-by-skin-tone study in the companion novelty document is its headline claim. Combine with Option A (fully client-side/on-device execution) as a secondary systems contribution if time allows: "a real-time, signal-quality-adaptive, fully client-side rPPG system" uses signal-processing rigor, quality-metric logic, AND web engineering, a distinctive combination almost no other team (or published paper) will have.

### 5.1 Committed Extension 1: Video-Call Robustness Testing (real Zoom/Google Meet degradation)

Public rPPG benchmark datasets are all clean, uncompressed video. Real-world usage (telehealth, remote monitoring) almost never looks like that: it happens over Zoom, Google Meet, or similar, which apply aggressive, motion-optimized video compression (H.264 at low bitrate, or VP8/VP9 for WebRTC) that specifically destroys color-channel precision (chroma subsampling): exactly the tiny signal rPPG depends on. Most published rPPG work does not test this realistic failure mode.

**Method:**
1. Take validation footage (UBFC-rPPG/PURE clips, or your own recordings) and actually route it through a real call: play the video as a webcam feed into an actual Zoom or Google Meet call, and record the receiving end's output. Repeat across a few connection-quality settings if possible.
2. As a controlled complement, re-encode the same footage directly with H.264/VP8/VP9 at several bitrates/resolutions, to isolate the effect of compression alone from other call artifacts (frame drops, resolution scaling).
3. Run your full pipeline (naive green-channel, CHROM, POS, and TRACE fusion) on every degradation level.
4. Plot BPM error vs. compression severity for each method.

**What this proves:** whether TRACE's real-time signal-quality weighting automatically down-weights whichever method/channel is being hit hardest by compression artifacts at a given moment, so the fused result degrades more gracefully than any single static method. This turns "works in a clean lab video" into "works on the exact kind of video a real telehealth call produces": a direct, concrete real-world value claim.

### 5.2 Committed Extension 2: Beyond a BPM Number: HRV / LF-HF Autonomic-State Layer

Showing a single "72 BPM" on screen is exactly what every other team's demo will do. A more substantive (and still fully defensible, non-medical) output uses a **second, independent application of the Fourier Transform**: this time not on the raw video signal, but on the *pattern* of heartbeats over time:

1. **Precise beat timing:** instead of only taking the FFT of the raw pulse signal for an average BPM, detect individual pulse peaks precisely (with interpolation for sub-frame accuracy) to build an interbeat-interval (RR-interval) time series.
2. **Time-domain HRV metrics:** compute standard, well-established metrics: SDNN, RMSSD, pNN50: directly from the RR-interval series.
3. **Frequency-domain HRV (the "second FFT"):** take the FFT of the RR-interval series itself (a distinct signal from the original pulse waveform) to get its power spectrum, and examine two standard bands:
   - **LF band (0.04–0.15 Hz):** mixed sympathetic/parasympathetic activity
   - **HF band (0.15–0.4 Hz):** parasympathetic activity, tied to breathing
   - **LF/HF ratio:** a widely used published indicator of autonomic nervous system balance / physiological stress state
4. **Output framing (important: stay honest and non-clinical):** display something like *"Heart rate: 72 BPM · LF/HF ratio: 2.3 (elevated, consistent with an alert/stressed state) · research/wellness indicator, not a medical diagnosis."* The explicit non-diagnosis caveat is what keeps this claim defensible: never present it as detecting or diagnosing a condition.

**Why this is a strong differentiator:** it's literally applying the Fourier Transform twice: once to extract the pulse from raw video, and again to analyze the rhythm *pattern* of the extracted pulses: using the exact 1996 Task Force HRV standard already in the reading list (Section 3), not an invented metric. It moves the final demo from "a number" to "an interpreted physiological state," while staying inside what a signals course project can honestly claim.

---

## 6. Benchmark Datasets (for quantitative validation)

| Dataset | Access | Description |
|---|---|---|
| **UBFC-rPPG** | Free direct download, no request form | 42 indoor facial videos (Logitech C920, 30fps, 640×480, uncompressed RGB) + synchronized ground-truth PPG waveform/HR from a CMS50E pulse oximeter. Subjects perform a time-limited math task to induce natural HR variation. Site: sites.google.com/view/ybenezeth/ubfcrppg |
| **PURE** | Requires a short academic-use request form | 60 one-minute videos, 10 subjects, 6 controlled head-motion scenarios (steady, talking, slow/fast motion, small/medium rotation), 640×480 @ 30fps lossless PNG, CMS50E ground truth at 60Hz. Best dataset for a motion-robustness story. |
| **MMPD** | Available via GitHub reference implementation | ~11 hours of mobile-phone facial video, 33 subjects, deliberately varying skin tone (Fitzpatrick III–VI), lighting, and activity. Best dataset for the skin-tone fairness novelty angle (Option B). |
| **UBFC-Phys / IMVIA-NIR** | Free (linked from UBFC-rPPG site) | Alternative/extension datasets if you want psychophysiological or NIR variants. |

**Fallback / extra credibility option:** a finger pulse oximeter costs ~$10–15. Collecting a small self-made validation set (5–10 classmates, with consent) alongside public dataset results is a strong "we understand ground-truth validation, not just downloading a CSV" signal, and gives you a fully controllable live demo.

**Verdict:** data availability is not a risk for this project: UBFC-rPPG has zero access friction, and the ecosystem (pyVHR, rPPG-Toolbox) means standardized loaders already exist.

---

## 7. Proposed Pipeline (implementation outline)

1. **Capture**: 20–30s of face video (webcam or phone), decent lighting, subject mostly still (or moving, if testing robustness).
2. **ROI tracking**: detect + track face. Recommended: OpenCV **Haar cascade** face detection, which is itself computed via convolution against integral images and involves no trained/learned model, keeping the entire pipeline provably classical DSP end-to-end (MediaPipe Face Mesh is an easier fallback, but it is a pretrained model and only used as infrastructure, not part of the algorithmic contribution, if used at all). Extract forehead/cheek region per frame.
3. **Raw signal extraction**: average pixel intensity per channel (R, G, B) per frame → three 1D time series.
4. **Detrending** (Convolution): remove slow illumination drift (convolution with moving-average kernel, subtract).
5. **Chrominance combination** (linear-algebra preprocessing, feeds the Fourier stage): implement CHROM and/or POS: fixed, derived projection matrices on R/G/B, not learned: to combine the raw channels into a cleaner, motion-robust pulse signal *before* frequency analysis. Frame this explicitly in the report as noise-suppression preprocessing that exists to feed the Fourier Transform cleaner data, exactly how de Haan's own CHROM/POS papers describe it: not as the algorithmic endpoint.
6. **Bandpass filtering** (Convolution, and a direct Convolution Theorem demonstration): convolve with a filter kernel restricting to plausible heart-rate frequencies (0.7–4 Hz); show the same result is obtained by multiplying in the frequency domain, to explicitly demonstrate the convolution theorem from the course.
7. **Fourier Transform**: FFT → find peak frequency → BPM = freq × 60.
8. **(TRACE layer, Fourier-based)**: compute a real-time signal-quality metric per method (green-channel, CHROM, POS) directly from each method's FFT output (e.g., in-band vs. total spectral power / SNR), then dynamically weight/fuse their outputs based on that metric. Optionally run this entire step client-side/in-browser (secondary systems contribution).
9. **(Robustness layer)**: re-run steps 3–8 on the same footage after real Zoom/Google Meet call degradation and/or controlled H.264/VP8/VP9 re-encoding at multiple compression levels (Section 5.1); compare accuracy degradation across naive/CHROM/POS/TRACE.
10. **(Diagnostic layer, second Fourier Transform)**: detect precise beat-to-beat timing from the fused pulse signal, build the RR-interval series, compute SDNN/RMSSD/pNN50, then take a *second, independent* FFT: this time of the RR-interval series itself: to get LF/HF power and the LF/HF ratio (Section 5.2). Display as an interpreted autonomic-state indicator with an explicit non-diagnostic caveat, not just a BPM number.
11. **Validate**: compare against public dataset ground truth (UBFC-rPPG/PURE) and/or your own oximeter-based mini dataset; report Mean Absolute Error in BPM, plus degradation curves (step 9) and HRV metric sanity checks (step 10).

---

## 8. Suggested Report/Paper Structure

Write the final deliverable like an actual paper: genuinely postable as an arXiv preprint or submittable to an undergraduate research symposium:

1. Abstract
2. Introduction (motivation, real-world value)
3. Related Work (cite Section 3 papers)
4. Method (pipeline + your novelty contribution, explicitly derived from Fourier/convolution theory)
5. Experimental Setup (datasets from Section 6, baselines from Section 4)
6. Results (quantified error tables, e.g., naive green-channel vs. CHROM vs. POS vs. your method)
7. Discussion / Limitations
8. Future Work
9. References

---

## 9. Key Differentiators: Summary Checklist

- [ ] Implement naive green-channel baseline (for comparison)
- [ ] Implement CHROM
- [ ] Implement POS
- [ ] Implement the TRACE fusion layer (signal-quality metric + dynamic weighting across green-channel/CHROM/POS)
- [ ] Test pipeline on footage routed through a real Zoom/Google Meet call, and/or re-encoded at multiple H.264/VP8/VP9 compression levels (Section 5.1)
- [ ] Plot BPM error vs. compression severity for naive/CHROM/POS/TRACE to show TRACE degrades more gracefully
- [ ] Extract precise beat-to-beat (RR-interval) timing, not just average BPM
- [ ] Compute SDNN, RMSSD, pNN50 (time-domain HRV)
- [ ] Take a second FFT of the RR-interval series to compute LF/HF power and ratio (Section 5.2)
- [ ] Display final output as an interpreted indicator (BPM + LF/HF ratio + explicit non-diagnostic caveat), not a bare number
- [ ] Validate quantitatively on UBFC-rPPG (and PURE/MMPD if relevant to novelty angle)
- [ ] Optional: collect small self-made ground-truth set with cheap pulse oximeter
- [ ] Explicitly demonstrate the convolution theorem (time-domain convolution vs. frequency-domain multiplication: show they're numerically identical) as a direct callback to course material
- [ ] Report quantified error metrics, not just a live "looks about right" number
- [ ] Build live real-time demo (web-based, leveraging your web dev strength)
- [ ] Write up as a structured paper-style report

---

## 10. Statistical Validation Rigor (this is what separates "well-engineered" from "looks about right")

Reporting only Mean Absolute Error is thinner than what real rPPG papers do. Add these standard techniques: none require new theory beyond what you already have, just more careful statistics:

- **Bland-Altman analysis**: the standard method in medical-device literature for comparing two measurement techniques (your rPPG estimate vs. the pulse-oximeter ground truth). Plot the difference between the two measurements against their mean, across all subjects/trials, and report the mean bias and limits of agreement. This is more informative than MAE alone because it reveals *systematic* bias (e.g., "we consistently overestimate at high heart rates") rather than just an average error number. Method originally defined by **Bland & Altman (1986)**; see **Dasari et al. (2021)** (Section 3) for a direct worked example applying it to CHROM/POS against an FDA-approved ground-truth sensor: use their figure layout as a template for your own plots.
- **Pearson correlation coefficient (r)** between your estimated BPM and ground-truth BPM, alongside MAE/RMSE: this is the standard trio (r, MAE, RMSE) reported in essentially every rPPG paper you've read, so matching that format makes your results table directly comparable to the literature.
- **Ablation study**: systematically report accuracy with each component turned on/off: naive green-channel alone, CHROM alone, POS alone, TRACE fusion, TRACE fusion + robustness preprocessing: so it's clear exactly how much each layer of your contribution helps, not just the final number. This is what a rigorous "Results" section in a real paper looks like, and it directly defends the TRACE fusion claim ("fusion beats any single static method") with evidence rather than assertion.
- **Confidence intervals / error bars**: report accuracy across multiple subjects/trials with a spread (std dev or 95% CI), not a single number from one lucky recording.

---

## 11. Limitations & Failure Case Analysis (shows engineering maturity, strengthens the write-up)

Every strong paper has an honest limitations section: proactively identifying where your system breaks is more convincing than pretending it's flawless. Worth explicitly testing and reporting:

- **Low light / no light**: rPPG fundamentally needs visible light reflecting off skin; document the failure point.
- **Very dark skin tones**: a known, documented issue in the literature (lower signal amplitude from higher melanin absorption): report it honestly rather than only testing on favorable subjects. **Dasari et al. (2021)** and **Nowara, McDuff & Veeraraghavan (2020)** (Section 3) are the direct citations for this: Dasari et al. specifically report traditional chrominance methods degrading sharply on darker Fitzpatrick skin types, so you can frame your own limitation testing as reproducing/extending a documented finding rather than an isolated anecdote.
- **Heavy motion / talking**: where even TRACE fusion starts to degrade, and by how much.
- **Occlusions**: glasses, facial hair, makeup, masks covering the ROI.
- **Multiple people in frame**: does ROI tracking correctly isolate one face, or does it get confused?
- **Extreme heart rates**: very low (bradycardia range) or very high (post-exercise) BPM: does the bandpass filter's frequency range need adjusting?

Framing this as a table (condition → does it work → why/why not) is a strong addition to the report's Discussion section, and a great thing to mention when a teacher/judge asks "what doesn't work?": a question you want to be ready for, not caught off guard by.

---

## 12. Ethical & Privacy Considerations (expected in any health-adjacent project write-up)

- **Informed consent**: for any video recorded of classmates/others for validation, get explicit consent, and mention this in the report.
- **Data handling**: state clearly whether recorded faces/video are stored, for how long, and whether they're deleted after the project: especially relevant here since you're already framing part of the contribution (Option A) around privacy-preserving, client-side execution.
- **No diagnostic claims**: reiterate in the report itself (not just the demo UI) that this is a research/wellness tool, not a medical device, and does not diagnose any condition: this protects you academically and is simply accurate.
- **Bias disclosure**: pair with Section 11: explicitly disclosing the skin-tone/lighting limitations rather than omitting them is the more rigorous, more respected choice in how real research papers are reviewed.

---

## 13. Optional Stretch Extensions (only if time remains: do not let these dilute the core TRACE contribution)

- **Respiration rate**: a second, lower-frequency peak (~0.15–0.4 Hz) is often visible in the same extracted signal or via subtle chest/shoulder motion: extracting it is a small addition once the FFT pipeline exists, and adds a second vital sign to the demo.
- **Multi-person simultaneous monitoring**: track 2-3 faces in frame at once, running the full pipeline independently per face: a good live "wow" moment if your ROI tracking is solid.
- **Cross-dataset generalization test**: train/tune your TRACE quality-weighting on UBFC-rPPG, then test unmodified on PURE (or vice versa) to show the method isn't overfit to one dataset's specific conditions: a standard rigor check in the field (several of the papers you read explicitly do this).

---

## 14. Demo Design (this is the "well-demoable" pillar: plan it, don't improvise it)

A strong live demo tells a **story with an arc**, not just a running number. Suggested structure for presenting to your teacher/judges:

1. **Hook (30s)**: show the live BPM number appearing in real time from a webcam feed with zero contact: the immediate "wait, how?" moment.
2. **Reveal the mechanism (1 min)**: briefly show the extracted raw signal, then its FFT, with the peak clearly highlighted: ties directly back to course material, this is the moment to say "this bump is literally the Fourier Transform of your face."
3. **Show the naive method failing (30s)**: move around / talk while the naive green-channel method is running: show it degrade or lose the signal.
4. **Show TRACE recovering (30s)**: switch to TRACE fusion under the same motion: show it staying stable. This side-by-side comparison is your single best "wow" moment, plan the demo specifically to create this contrast.
5. **Show the robustness result (30s)**: a pre-recorded chart of BPM error vs. compression level, with TRACE's curve clearly flatter than the alternatives: this is where the Zoom/Meet testing pays off visually.
6. **Show the diagnostic layer (30s)**: reveal the LF/HF ratio alongside BPM, with the non-diagnostic caveat clearly stated: this is the "beyond a number" moment.
7. **Close with real-world framing (15s)**: one sentence tying it back to telehealth/remote monitoring value.

**Practical demo tips:**
- Pre-record the compression/robustness comparison rather than trying to run a live Zoom call during the presentation: live network demos are a common failure point.
- Have a backup video recording of the entire live demo working correctly, in case webcam/lighting conditions on presentation day are uncooperative.
- Keep the UI showing the raw signal + FFT plot alongside the final number at all times: the visual "you can see the Fourier Transform happening" is worth more than a clean number alone.

---

## 15. Suggested Figures for the Report (plan these early: they double as demo assets)

- Architecture/pipeline diagram (block diagram of the full 11-step pipeline from Section 7)
- Raw RGB signal → detrended signal → filtered signal → FFT spectrum (a 4-panel figure showing the transformation at each stage, directly illustrating course concepts)
- Bland-Altman plot (Section 10)
- BPM error vs. compression severity, one line per method (Section 5.1)
- HRV power spectrum showing LF/HF bands shaded (Section 5.2)
- Ablation study bar chart (Section 10)
- Limitations table (Section 11)

---

## 16. Suggested Timeline (for a ~3-4 week build with a team)

| Week | Focus |
|---|---|
| Week 1 | Read papers (Section 3); implement naive green-channel + FFT baseline; set up UBFC-rPPG data loading |
| Week 2 | Implement CHROM, POS; implement TRACE fusion layer; begin quantitative validation |
| Week 3 | Robustness testing (Section 5.1); HRV/LF-HF diagnostic layer (Section 5.2); ablation study; limitations testing |
| Week 4 | Statistical analysis (Bland-Altman, correlation); build live demo UI; write report; rehearse demo script |

**Suggested role split (adjust to team size/strengths):** one person owns the core signal pipeline (steps 1-7), one owns TRACE fusion + robustness testing (steps 8-9), one owns the HRV/diagnostic layer + statistical validation (steps 10-11 + Section 10), one owns the live demo UI + presentation (Section 14). Everyone contributes to the write-up.

---

## 17. Core Method Purity: Fourier Series, Fourier Transform & Convolution as the Architectural Backbone

This project is intentionally built as a classical, interpretable signal-processing system, not a machine-learning system that references Fourier theory as background detail. The table below maps every stage of the pipeline (Section 7) to whether it is literally Fourier Series / Fourier Transform / Convolution, so this can be shown directly to a teacher/evaluator without ambiguity.

| # | Pipeline stage | Literally Fourier / Convolution? | Notes |
|---|---|---|---|
| 1 | Face/ROI detection (Haar cascade) | Partial | Haar features are computed via convolution against integral images: convolution-family, but 2D image filtering, not the 1D signal theory this course teaches directly |
| 2 | Raw RGB signal extraction (pixel averaging) | No | Data formation only: no theory applied yet |
| 3 | Detrending | **Yes: Convolution** | Moving-average kernel |
| 4 | CHROM / POS combination | No (preprocessing) | Fixed linear-algebra projection matrix on RGB, derived from a physical skin-reflectance model, not learned. Framed explicitly as noise-suppression preprocessing that feeds the Fourier stage cleaner data, matching how the original CHROM/POS papers describe it |
| 5 | Bandpass filtering | **Yes: Convolution**, explicitly cross-checked via the **Convolution Theorem** (time-domain convolution vs. frequency-domain multiplication) | Core pipeline stage, and a direct, demonstrable callback to course material |
| 6 | BPM extraction | **Yes: Fourier Transform** | FFT peak-finding |
| 7 | TRACE quality metric | **Yes: Fourier Transform** | Signal-quality/SNR computed directly as a ratio of in-band vs. total spectral power, straight from each method's FFT output |
| 8 | Fusion weighting (combining quality-weighted methods) | No | Weighted averaging once quality scores exist: arithmetic, not Fourier theory itself |
| 9 | Beat-to-beat (RR-interval) peak detection | No | Time-domain peak-finding on the already-filtered signal |
| 10 | SDNN / RMSSD / pNN50 | No | Basic descriptive statistics on the RR-interval series |
| 11 | LF/HF ratio | **Yes: Fourier Transform (again)** | A *second*, independent FFT applied to the RR-interval series, distinct from the FFT in stage 6 |
| 12 | Compression/robustness testing (Section 5.1) | No | Engineering/testing methodology |
| 13 | Bland-Altman / statistical validation (Section 10) | No | Statistics methodology, not signal theory |

### Honest weighting summary

- **Directly, unambiguously Fourier/Convolution stages: 3, 5, 6, 7, 11**: this is the pipeline's core: detrend (convolution) → filter (convolution + convolution theorem) → transform (FFT) → quality-weight (from FFT output) → transform again for HRV (second FFT). Data is actively flowing through convolution and FFT operations at every point where physiological information is being extracted from the raw signal.
- **Both headline numbers the demo produces: BPM and the LF/HF ratio: come directly out of a Fourier Transform**, not out of CHROM/POS or any statistics layer. This is the strongest single fact to state when explaining the project's core methodology.
- **Roughly 55–65% of the algorithmic pipeline stages are literally Fourier Transform or Convolution operations.** The remaining stages are either (a) classical linear-algebra preprocessing (CHROM/POS) that exists solely to feed the Fourier stage cleaner data, or (b) statistics/testing methodology (Sections 10-11) applied *after* the Fourier-based estimation is complete, not part of the estimation itself.
- **No stage in the physiological-estimation path (stages 1-11) uses a trained/learned model.** Haar cascade face detection (stage 1) is the only stage with any resemblance to a "learned" component, and even that is a classical convolution-based feature detector with no training step in the pipeline itself (the cascade is a fixed, precomputed classifier shipped with OpenCV, not something trained as part of this project).

### If asked "why not just use a deep-learning model, like current research?"
Current rPPG research (DeepPhys, PhysNet, and multimodal fusion networks like the ones surveyed in Section 3/5.1) is increasingly dominated by deep learning. Several of those very papers note that black-box deep fusion models face real interpretability problems that specifically hinder adoption in medical/healthcare settings, plus training-data coverage and inference-cost issues. This project's explicit position: a fully classical, interpretable Fourier/convolution-based pipeline, where every output number can be traced back to a specific frequency-domain computation, directly answers that documented gap, rather than being a simpler fallback because deep learning wasn't attempted.
