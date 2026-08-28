# BCG & Accelerometer-Based Cardiac Sensing: Extended Fusion Options for TRACE-rPPG

**Companion document to:** `TRACE-rPPG_Main_Project_Plan.md`
**Purpose:** detailed background, related work, datasets, and novelty analysis for three ways to extend TRACE-rPPG with mechanical/motion-based cardiac sensing: camera-only (rBCG), hardware-based (accelerometer/SCG), or both combined.

---

## 1. Background: What BCG, SCG, and rBCG Actually Measure

Before comparing the three fusion options, it's important to be precise about the underlying physics, since "BCG" and "SCG" are often used loosely in casual writing but refer to distinct (if related) phenomena.

| Signal | What causes it | How it's sensed |
|---|---|---|
| **BCG (Ballistocardiography)** | Whole-body recoil forces caused by blood being ejected from the heart into the aorta (Newton's third law: the body experiences a tiny reaction force with each heartbeat) | Historically: a person lying on a specially suspended bed/table. Modern versions: a sensor under a mattress, in a chair, or, in the camera-based version below, tiny involuntary head motion |
| **SCG (Seismocardiography)** | Local mechanical vibration of the chest wall directly caused by heart muscle contraction and valve closure | An accelerometer placed directly on the chest/sternum |
| **rBCG (remote/camera Ballistocardiography)** | Same underlying principle as BCG, but the tiny (~0.5mm) involuntary head displacement caused by cardiac ejection is tracked optically from ordinary video, rather than through a mechanical sensor | Face/feature-point tracking + motion signal extraction from RGB video, no contact device |

**Why this distinction matters for your project:** rBCG is fully contactless (same modality as rPPG: just from motion instead of color), while SCG requires physical sensor contact with the chest. This is the central trade-off across the three options below.

---

## 2. Option 1: rPPG + rBCG: Fully Remote, Camera-Only Fusion

### Concept
Extract two independent physiological signals from the *same* video feed: the color-based pulse signal (rPPG, what TRACE-rPPG already does) and the motion-based pulse signal (rBCG, tiny involuntary head displacement from cardiac ejection). Fuse them. No additional hardware is required beyond the webcam TRACE-rPPG already uses.

### Why the two signals are complementary (this is the core scientific argument)
- **rPPG** degrades under poor lighting, low skin exposure, and demographic skin-tone variation, but tolerates mild motion reasonably well (especially with CHROM/POS).
- **rBCG** is completely unaffected by lighting or skin tone (it's tracking geometric position, not color), but degrades badly under voluntary motion: talking, head turns, or general fidgeting: because that swamps the ~0.5mm involuntary cardiac displacement signal.

Their failure modes are close to orthogonal, which is exactly the condition under which signal-quality-adaptive fusion (what TRACE already does across CHROM/POS/green-channel) provides the most benefit when extended across modalities rather than just across color-extraction methods.

### Pipeline
1. Existing TRACE-rPPG color pipeline (Sections 3–7 of the main plan) runs unchanged.
2. **rBCG extraction (new)**: track multiple facial feature points (forehead, nose, cheeks) frame-to-frame using optical flow or landmark tracking; isolate the extremely small, quasi-periodic component of that motion (this is where Blind Source Separation: PCA or ICA: is classically used to separate cardiac motion from voluntary motion and noise).
3. Bandpass filter the rBCG motion signal to the same 0.7–4 Hz plausible heart-rate range (convolution, identical theory to the rPPG pipeline).
4. FFT the rBCG signal to extract its own independent BPM estimate.
5. **Cross-modal TRACE layer**: compute a real-time confidence score for rPPG (based on lighting/skin exposure stability) and a separate confidence score for rBCG (based on voluntary-motion magnitude), then fuse the two modalities' frequency-domain estimates weighted by those scores: the direct generalization of the existing TRACE concept from "which color method" to "which entire modality."

### Related papers (read in this order)
1. **Balakrishnan, Durand & Guttag (2013)**, *"Detecting Pulse from Head Motion in Video"*, CVPR. The foundational rBCG paper: first to show cardiac-induced head motion is extractable from ordinary video using PCA-based feature-point tracking.
2. **Shin, Cha, Park & Lee (2021)**, *"Fusion Method to Estimate Heart Rate from Facial Videos Based on RPPG and RBCG"*, Sensors 21(20), 6764, DOI: 10.3390/s21206764. The most directly relevant existing work: proposes fusing rPPG and rBCG via ensemble averaging, PCA, and ICA (Blind Source Separation methods). Critically, this paper explicitly states that prior work (Shao et al.) monitored both signals simultaneously *without* combining them, and other work (Liu et al.) used a **separate physical motion sensor**, not a camera, to correct rPPG: and concludes it is still necessary to develop a fusion method that properly considers the interaction effect between rPPG and rBCG. **This is your direct, citable research gap.**
3. **Shan & Yu (2013)**, *"Bio-signal based control in assistive robots: A survey"* or more directly, search for **Shan et al.** rBCG feature-point extension work referenced within Shin et al. (2021): extends Balakrishnan's original feature-point approach.

### Novelty opportunities (beyond what Shin et al. 2021 already did)
- **Real-time, per-frame adaptive weighting** (not static offline PCA/ICA blending computed after the fact): genuinely different from the 2021 paper's methodology.
- **Bidirectional correction**: use rPPG to disambiguate rBCG when talking/motion makes its peaks unclear, *and* use rBCG to sanity-check rPPG when lighting is poor: true two-way interaction, which the field explicitly says hasn't been done.
- **Compression robustness across modalities**: test whether motion information (which video codecs generally preserve more aggressively than fine color detail, since codecs prioritize structural/motion fidelity for compression efficiency) survives Zoom/Meet-style compression better than the color signal: ties directly into the TRACE-rPPG Section 5.1 robustness story, and appears to be untested in existing literature.
- **Fully classical/interpretable implementation**: current multimodal cardiac fusion research is increasingly deep-learning-based (temporal fusion networks, cross-modal attention); explicit positioning as a fully classical FFT/convolution/PCA-ICA pipeline (no trained neural network) is itself a legitimate, citable differentiator given documented interpretability concerns around black-box fusion models in medical contexts.

### Public datasets
There is **no dataset built specifically for rBCG validation**: this is a genuine, honest gap in the field. In practice, researchers repurpose standard rPPG/emotion datasets that include synchronized ECG or PPG ground truth, and derive their own rBCG signal from the video itself:
- **MAHNOB-HCI**: 527 videos from 27 subjects, synchronized with 3-electrode ECG ground truth. Not originally designed for rPPG/rBCG (it was built for emotion recognition), but widely reused as an rPPG/rBCG benchmark because of its reliable ECG ground truth and because subjects exhibit natural head motion during emotional stimuli: actually well-suited to testing rBCG under realistic motion.
- **UBFC-rPPG / PURE / MMPD**: same datasets already used for TRACE-rPPG (see main plan, Section 6). PURE in particular includes explicit head-motion scenarios (steady, talking, slow/fast motion, rotation), making it directly usable for rBCG extraction and testing, even though it was not designed with rBCG specifically in mind.
- **Fallback**: collect your own small validation set (webcam + pulse oximeter, as already planned for TRACE-rPPG): since you're already doing this for the main project, extending it to also validate rBCG costs little extra effort.

---

## 3. Option 2: rPPG + Accelerometer: Real Hardware, Contact-Based Fusion

### Concept
Fuse the camera-based rPPG signal with a genuine seismocardiography (SCG) signal captured by a real accelerometer (a smartphone resting on or strapped to the chest, or a dedicated wearable sensor). Unlike rBCG, this uses a completely independent physical sensing modality: mechanical vibration sensed directly at the source, not inferred optically.

### Why this is attractive despite requiring contact
- SCG waveform morphology carries genuinely richer diagnostic information than PPG alone: it can reflect systolic time intervals, aspects of myocardial contractility, and valve-closure timing, information that a pure color-based pulse signal doesn't carry.
- It's a true two-independent-sensor fusion (optical + mechanical), arguably a stronger reliability argument than two signals both extracted from the same camera (Option 1).
- Every modern smartphone already has a capable accelerometer: no specialized hardware purchase needed, unlike a dedicated medical SCG patch.

### Pipeline
1. Existing TRACE-rPPG color pipeline runs from the webcam feed, unchanged.
2. **SCG capture**: use a smartphone's built-in accelerometer (sampling typically 100Hz+) resting on the sternum, or held flat against the chest.
3. **SCG preprocessing**: detrend (convolution, moving-average kernel: removes gravity/postural drift), bandpass filter to the cardiac mechanical vibration band (convolution again).
4. **FFT** the SCG signal for an independent BPM estimate; SCG waveform peak-timing can also give a second, independent RR-interval series for HRV cross-validation against the rPPG-derived one (direct synergy with TRACE-rPPG's existing HRV/LF-HF layer, Section 5.2 of the main plan).
5. **Synchronization**: this is the main new engineering challenge: the camera (typically ~30fps) and accelerometer (100Hz+) run on different clocks/sampling rates and, if using two separate devices (a computer webcam + a phone accelerometer), need explicit time alignment (e.g., a synchronization event like a clap, or NTP-based timestamp alignment if both devices log wall-clock time).
6. **Cross-modal TRACE layer**: same conceptual extension as Option 1: fuse rPPG and SCG frequency-domain estimates, weighted by real-time confidence in each (lighting stability for rPPG; motion-artifact/contact-quality estimate for SCG).

### Related papers
1. **García-González, Argelagós-Palau, Fernández-Chimeno & Ramos-Castro (2013)**, *"Combined measurement of ECG, Breathing and Seismocardiograms (CEBS database)"*, PhysioNet, DOI: 10.13026/C2KW23. The foundational public SCG dataset paper (see Section 3 datasets below): establishes the standard preprocessing/ground-truth methodology for SCG-vs-ECG comparison.
2. **[Feasibility study, PMC11200605]**, *"Automated Heart Rate Detection in Seismocardiograms Using Electrocardiogram-Based Algorithms: A Feasibility Study."* Directly benchmarks SCG-based heart-rate detection against ECG on the CEBS dataset, reporting very high precision at rest (mean difference ~0.12 ± 0.35 BPM) but notable degradation under physical activity/motion (~6.45 ± 3.01 BPM difference): this is a directly citable, quantified statement of exactly the failure mode (motion-induced SCG degradation) that fusing with rPPG could help compensate for, since rPPG's failure modes are different.
3. **[PMC11859794]**, *"Accuracy of the Instantaneous Breathing and Heart Rates Estimated by Smartphone Inertial Units."* Directly validates smartphone-based accelerometer/gyroscope SCG and gyrocardiography (GCG) against reference measurements: the closest existing precedent to "use an ordinary phone as the SCG sensor," exactly your proposed hardware setup.
4. **Inan et al. (2018)**, *"Novel wearable seismocardiography and machine learning algorithms can assess clinical status of heart failure patients"*, Circulation: Heart Failure. Establishes the clinical relevance of SCG beyond simple heart-rate counting: useful for the "why SCG, not just another PPG sensor" argument in your report's motivation section.

### Novelty opportunities
- **rPPG-guided motion-artifact rejection for SCG**: since the CEBS-based feasibility study above shows SCG accuracy drops sharply under physical activity, use the independently-derived rPPG signal (immune to this specific failure mode) as a real-time reference to flag and reject corrupted SCG segments: a concrete, testable, and currently undemonstrated cross-modal correction.
- **Consumer-hardware-only validation**: most SCG literature uses dedicated medical-grade accelerometers (Biopac, wearable patches); explicitly validating smartphone-accelerometer SCG fused with a plain webcam, entirely off-the-shelf consumer hardware, is a genuinely underexplored, real-world-relevant angle (telehealth-at-home feasibility, no special equipment).
- **Synchronization-robustness study**: characterizing how fusion accuracy degrades as clock-synchronization error between the two devices increases (a practical problem any real deployment would face) is a legitimate, useful engineering contribution nobody in the literature above appears to address directly.

### Public datasets
This is where accelerometer-based cardiac sensing is **considerably better provisioned than rBCG**:
- **CEBS Database (PhysioNet)**: 60 records from 20 volunteers, each containing two-lead ECG, respiration, and seismocardiogram signals, all time-synchronized. Freely downloadable, no request form. The standard baseline dataset for SCG-vs-ECG algorithm validation.
- **FOSTER dataset**: the first public dataset combining forcecardiography (FCG) with simultaneous SCG, phonocardiography (PCG), ECG, and respiratory signals from 40 participants (20 male, 20 female), ~7 minutes per recording including quiet breathing and apnea phases. Useful if you want to explore beyond simple heart-rate extraction into richer mechanical-cardiac signal analysis.
- **SCG-RHC (PhysioNet)**: 73 patients with simultaneous wearable ECG + SCG alongside invasive right-heart-catheter hemodynamic ground truth (pulmonary pressures, cardiac output). This is a genuinely clinical-grade dataset: more advanced than you likely need for a course project, but a strong citation for "SCG is a real clinical signal, not just a novelty metric."
- **Note**: none of the above datasets include synchronized *video*, since they were built purely for the SCG/ECG research community. For a true rPPG+SCG fusion validation, you'll most likely need to **collect your own small paired dataset** (webcam + phone accelerometer on the same subjects at the same time), using CEBS/FOSTER as external reference points for "is my SCG extraction working correctly in isolation" before combining with your own rPPG pipeline.

---

## 4. Option 3: Triple Fusion: rPPG + rBCG + Accelerometer SCG

### Concept
Combine all three signals: the existing color-based rPPG, the camera-derived motion signal (rBCG), and a true hardware accelerometer signal (SCG): three independent estimates of the same underlying cardiac cycle, from two different physical principles (optical reflectance and mechanical vibration) and three different extraction pathways.

### Why this is the most novel: and the most ambitious: option
As far as the literature search for this document could establish, **no existing published work fuses all three of rPPG, rBCG, and hardware-based SCG together.** Existing work pairs at most two: rPPG+rBCG (Shin et al., 2021, camera-only) or rPPG+external-motion-sensor (Liu et al., referenced within Shin et al., one-directional correction only, not full fusion). A genuine three-way, quality-adaptive fusion appears to be an open combination: which is exactly the kind of gap a course project can credibly claim as a real contribution, provided the engineering is executed carefully and validated rigorously.

### Pipeline
Builds directly on Options 1 and 2 combined:
1. Webcam feed → rPPG pipeline (TRACE-rPPG core) → BPM estimate + confidence score.
2. Same webcam feed → rBCG pipeline (Option 1) → independent BPM estimate + confidence score.
3. Phone accelerometer on chest → SCG pipeline (Option 2) → independent BPM estimate + confidence score.
4. **Three-way TRACE fusion layer**: combine all three frequency-domain estimates, weighted by three independently-computed real-time confidence scores (lighting/skin stability for rPPG, voluntary-motion magnitude for rBCG, motion-artifact/contact-quality for SCG). This is a direct generalization of the existing 2-way cross-method fusion (green-channel/CHROM/POS) already at the heart of TRACE-rPPG: architecturally, you are not building a new fusion mechanism, you are feeding the same mechanism a third input stream.
5. Cross-validate: use agreement/disagreement across all three signals as an additional real-time signal-quality indicator in its own right (e.g., if all three agree closely, report high confidence in the final estimate; if they diverge, flag lower confidence): a natural, almost "free" byproduct of having three independent estimates instead of two.

### Related papers
Combine the reading lists from Options 1 and 2 above. Additionally:
- **[npj Digital Medicine, 2026]**, multimodal temporal fusion network integrating BCG and PPG via cross-modal attention, reporting MAE of 0.88 BPM: while this is a deep-learning approach (not a direct methodological template for your classical pipeline), it's useful as the current state-of-the-art benchmark number to cite as context, and to explicitly contrast against your interpretable, non-deep-learning three-way fusion.
- Re-read **Shin et al. (2021)**'s discussion section closely: its explicit statement that no existing work properly considers the "interaction effect" between modalities is your strongest direct citation justifying why a three-way *adaptive* fusion (rather than the two-way static fusion it proposes) is a genuine next step, not just "doing more of the same."

### Novelty opportunities
This option inherits all novelty angles from Options 1 and 2, plus:
- **First-of-its-kind three-way classical fusion**: genuinely the most novel of the three options, in the specific sense that no directly comparable published combination was found during research for this document.
- **Redundancy-based confidence estimation**: using inter-modality agreement itself as a live data-quality signal (not just each modality's individual internal confidence) is a distinct, useful idea that only becomes possible with three or more independent estimates.
- **Modality dropout robustness study**: systematically test what happens to accuracy as each modality is removed one at a time (rPPG only, rPPG+rBCG, rPPG+SCG, all three): this doubles as your ablation study (see Section 10 of the main TRACE-rPPG plan) and directly demonstrates the practical value of each added modality with real numbers, not just assertion.

### Public datasets
The honest reality: **no existing public dataset contains synchronized rPPG-quality video, rBCG-relevant head motion, and hardware SCG together.** This is unavoidable, since it's a genuinely novel combination. Realistic approach:
- Use **CEBS** or **FOSTER** to validate your SCG extraction pipeline in isolation first (their own ECG ground truth lets you confirm your SCG algorithm is correct before ever touching a camera).
- Use **UBFC-rPPG/PURE/MAHNOB-HCI** to validate your rPPG and rBCG extraction pipelines in isolation (as in Option 1).
- **Collect your own small paired three-modality dataset** (webcam + phone accelerometer + pulse oximeter as ground truth, on the same handful of consenting classmates) as the final integration/validation step: following the same cheap-hardware, informed-consent approach already planned for TRACE-rPPG's own validation (see Section 6 and Section 12 of the main plan).

---

## 5. Comparative Summary

| Factor | Option 1: rPPG + rBCG | Option 2: rPPG + Accelerometer (SCG) | Option 3: Triple Fusion |
|---|---|---|---|
| Extra hardware needed | None (camera only) | Phone/wearable accelerometer, physical chest contact | Both |
| Preserves "just a video call" telehealth story | Yes, fully | No, requires contact | Partially (rPPG+rBCG channel still contactless) |
| True independent physical modalities | No (both from same camera/optics) | Yes (optical + mechanical) | Yes |
| Synchronization complexity | Low (single video stream) | Moderate–high (two separate devices/clocks) | Highest |
| Existing direct precedent in literature | Yes (Shin et al. 2021): clear gap to fill | Partial (motion-sensor correction exists, full fusion less so) | None found: most novel, most ambitious |
| Public validation data availability | Repurposed rPPG datasets only (no dedicated rBCG dataset) | Good (CEBS, FOSTER, SCG-RHC) but no synchronized video | Weakest (must self-collect for full three-way validation) |
| Realistic implementation effort (given TRACE-rPPG already built) | Moderate | Moderate–high | High |
| Best fit if... | You want to stay fully contactless and extend TRACE's existing fusion concept cleanly | You want the strongest independent-sensor reliability argument and richer SCG diagnostic content | You want the single most novel, defensible research claim and have the time budget for it |

---

## 6. Recommendation

Given TRACE-rPPG is already a substantial project (see the main plan's own scope), treat this document as your **stretch-goal roadmap**, not a requirement to attempt all three immediately:

1. **Start with Option 1 (rPPG + rBCG)** as the most natural, lowest-friction extension: no new hardware, reuses your existing video pipeline, and has the clearest, most directly citable research gap (Shin et al. 2021's own stated limitation).
2. **Treat Option 2 (rPPG + Accelerometer/SCG) as an independent parallel exploration or a separate backup project** in its own right if your teacher wants genuinely distinct submissions: it stands alone on real clinical/research merit (SCG's richer diagnostic content) without needing TRACE-rPPG as a prerequisite.
3. **Reserve Option 3 (Triple Fusion) as the ambitious final-stretch goal** only if Options 1 and/or 2 are working solidly with time to spare: it's genuinely the most novel of the three, but also carries real integration and validation risk given the lack of any existing three-way precedent to model your approach on.

All three options remain fully consistent with the Fourier Series / Fourier Transform / Convolution "core method purity" position established in the main TRACE-rPPG plan (Section 17): detrending and bandpass filtering of SCG/rBCG signals are convolution operations, BPM extraction from any of the three modalities is an FFT peak-finding operation, and the cross-modal TRACE confidence weighting is computed directly from each modality's own FFT output: no additional theory beyond what the course already teaches is required to extend into any of these three directions.
