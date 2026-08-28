# TRACE-rPPG: Novelty Assessment, Literature Search, and Revised Conference Strategy

**Project name:** TRACE-rPPG (Tone-stratified Robustness Across Compressed Encodings)

**Companion to:** `TRACE-rPPG_Main_Project_Plan.md` and `TRACE-rPPG_Fusion_Extensions_rBCG_SCG.md`
**Date of search:** 27 August 2026
**Purpose:** record what the literature search found, which of the originally planned contributions are already occupied, what gap remains genuinely open, and how the project should be restructured to target a poster submission at NSysS (BUET).

---

## 1. What Changed and Why

The project was originally scoped as a strong course project: TRACE-rPPG, a signal-quality-adaptive fusion system, validated quantitatively, with two extensions (video-call robustness and an HRV/LF-HF layer).

Two things then changed:

1. **The supervisor suggested adding a machine-learning comparison**, to show measured differences between the deterministic pipeline and a trained model rather than merely asserting that the classical approach is preferable.
2. **The supervisor encouraged targeting a real conference submission** at NSysS, held at BUET, rather than producing repeated application work over existing research.

A course project and a conference submission are different objects. A course project must demonstrate that the material was understood. A conference submission must tell the community something it does not already know, and it is read by reviewers who know the prior work. That difference forced a formal novelty assessment before committing further effort.

### Deadlines

| Track | Deadline | Status |
|---|---|---|
| Full paper | 28 August 2026 | **Not achievable.** One day away at time of assessment. |
| **Poster** | **20 November 2026** | **Target.** Roughly twelve weeks available. |

A poster requires an extended abstract rather than a full paper, which is a lower bar in length but not in novelty. The poster track is the correct target.

---

## 2. Literature Search: Method

Direct querying of ACM Digital Library was blocked by an automated bot-protection challenge, and no attempt was made to circumvent it. IEEE Xplore was not queried natively for the same reason.

Instead the search used **OpenAlex**, an open bibliographic database, after first confirming it indexes both publishers:

- ACM coverage confirmed: CardioLive returned with DOI prefix `10.1145/`
- IEEE coverage confirmed: numerous returned records carried DOI prefix `10.1109/`

Abstract-level metadata is sufficient for a novelty check, since a paper measuring a specific effect will name that effect in its title, abstract, or keywords. Ten targeted web searches were also run across the open literature to catch material OpenAlex might index without abstracts.

**Known limitations of this method**, recorded honestly:

- OpenAlex abstract coverage is not complete; records lacking abstracts cannot be keyword-matched.
- The arXiv API rate-limited repeatedly, so preprints from the last few weeks may be missing.
- A study could exist using vocabulary the searches did not cover.

---

## 3. Literature Search: Results

### 3.1 Corpus density

| Query | Result count |
|---|---|
| rPPG corpus (total) | 2,023 |
| rPPG + compression / codec / bitrate | 51 |
| rPPG + skin tone / Fitzpatrick / melanin | 121 |
| **Intersection of the two above** | **3** |
| rPPG + bias / fairness / disparity | 108 |
| ...of which also compression | 6 |

Restricted to 2024 to 2026: 84 skin-tone papers, of which only 2 mention compression at all.

All 3 intersection papers and all 6 bias-by-compression papers were read at abstract level. **None of them measures the interaction between compression and skin tone.** The two recent papers matching both terms are a deepfake-detection systematic review and a general telemedicine rPPG paper that happen to use both words in passing.

Two literatures of 51 and 121 papers that produce an intersection of 3 is the standard signature of an unexplored gap.

### 3.2 What is already occupied

This is the most important section of this document. Four of the five originally planned contributions are taken.

| Original thread | Status | Occupying work |
|---|---|---|
| **rPPG over live video calls / Zoom** | **Taken, recently and thoroughly** | CardioLive (ACM Multimedia 2025): plug-and-play WebRTC middleware deployed in Zoom and YouTube, 1.79 BPM MAE, handles variable frame rate and stream desynchronisation |
| **Compression robustness (Section 5.1)** | **Taken, and actively worked** | At least seven groups; see Section 7 below for the reading list |
| **Confidence / knowing when the output is wrong** | **Taken** | RF-BayesPhysNet (Bayesian uncertainty estimation); optimal signal quality index work in npj Biosensing |
| **Quality-weighted fusion of classical methods (the TRACE core)** | **Effectively taken** | Recent work fuses SNR estimates across multiple rPPG algorithms by consensus; adaptive parameter optimisation covers adjacent ground |
| **Browser / client-side execution (Option A)** | **Taken commercially** | Labvanced and Circadify already ship client-side WebAssembly rPPG; not an academic claim |

The honest conclusion is that the project as originally designed is a strong course project whose individual pieces are incremental. It is not, in that form, a conference contribution.

### 3.3 What remains open

> **Does video compression amplify the skin-tone accuracy gap in rPPG?**

Every search returned skin-tone work **or** compression work, never the interaction.

The mechanism is documented in every adjacent domain but never closed for rPPG:

- Darker skin produces a weaker pulse signal because melanin absorbs more light. Chrominance methods degrade from about 5.2 BPM MAE on Fitzpatrick I to III up to about 14.1 BPM on Fitzpatrick V to VI. Deep models degrade less steeply, from about 6.0 to 9.5 BPM.
- Compression preferentially destroys low-amplitude chroma detail, which is exactly where the pulse signal lives.
- Racial bias in low-rate neural image compression has been demonstrated (FAccT 2025).
- Melanin bias in pulse oximetry is extensively documented, including its clinical consequence of occult hypoxemia.

**Hypothesis:** because a weaker signal crosses the noise floor at a higher bitrate, the disparity should be multiplicative rather than additive. If true, the populations already disadvantaged by the sensing physics are also those most likely to be on constrained network connections, and the two effects compound.

Nobody appears to have measured this.

### 3.4 The framing citation

The 2020 CVPR Workshops paper *Remote Photoplethysmography: Rarely Considered Factors* (DOI 10.1109/cvprw50498.2020.00156) opens by stating:

> "Several major phenomena affecting rPPG signals have been studied (e.g. video compression, distance from person to camera, skin tone, head motions)."

The field naming both factors as separately studied, in a single sentence. The 2026 npj Digital Medicine roadmap does the same thing, synthesising progress across eight domains treated independently.

This is the gap statement in the literature's own words, and it should be quoted directly in the abstract's motivation.

---

## 4. Why This Fits NSysS Specifically

NSysS is a networking, systems and security venue, not a biomedical signal-processing venue. The original framing ("we improved rPPG accuracy") is aimed at the wrong audience and would read as out of scope. The revised framing fits:

- **Bitrate is a systems variable.** The paper becomes a measurement study of how a network-layer decision propagates into a demographic outcome, which is legitimately a systems contribution.
- **The venue is in Bangladesh.** The dominant local skin tones sit exactly in the Fitzpatrick range where the gap appears, and low-bandwidth telehealth is a regional reality rather than a hypothetical. A locally motivated equity result is an asset at this venue.
- **It is a measurement paper**, which is the correct shape for a poster. A clear measured result is required, not a deployed system.
- **The team has a genuine local advantage.** Recruiting Fitzpatrick IV to V participants in Dhaka is substantially easier than for most labs, and the public datasets are documented as under-representing exactly those subjects (UBFC-rPPG contains roughly 5 percent dark-skinned subjects; AFRL contains none).

---

## 5. Revised Contribution Statement

> Remote photoplethysmography is known to perform worse on darker skin, and separately known to degrade under video compression. We present the first measurement of their **interaction**, showing that the skin-tone accuracy gap widens as bitrate falls, and we evaluate whether signal-quality-adaptive fusion narrows that gap.

Note what happens to the original project: **TRACE is not discarded.** It moves from being the headline claim to being the proposed mitigation, which is a more defensible position than it occupied before. The classical pipeline, the quality metric, and the fusion layer are all still built. Only the framing changes.

---

## 6. Experiment Design

### 6.1 The core grid

```
skin tone group  x  bitrate  x  method
```

- **Skin tone groups:** Fitzpatrick I to III versus IV to VI, or finer if subject counts allow
- **Bitrate levels:** at least five points spanning a realistic telehealth range, plus a lossless control
- **Methods:** green channel, CHROM, POS, TRACE fusion, and at least one neural baseline

### 6.2 Required figures

1. **Headline:** MAE against bitrate, one curve per skin-tone group. If the curves fan apart as bitrate drops, the hypothesis is confirmed.
2. **Mitigation:** the same plot with TRACE fusion added, showing whether the fan narrows.
3. **Method comparison:** does the disparity behave differently for learned versus classical methods? Existing data hints that it might, since deep models degrade less steeply across skin tone, but this has never been tested under compression.
4. **Bland-Altman per group**, to expose whether the error is systematic bias rather than random spread.

### 6.3 Statistical requirement

The claim is about an **interaction effect**, not two main effects. Reporting that both factors matter is insufficient. The analysis must test whether the effect of bitrate *differs by* skin-tone group, using a two-way analysis with an interaction term, and must report a confidence interval on that interaction.

This is the single most likely point of methodological attack from a reviewer, and it should be planned before data collection rather than after.

### 6.4 A negative result is still publishable

If the curves stay parallel, the finding is that compression degrades all skin tones equally, which is genuinely useful to know and directly contradicts a reasonable prior expectation. Design the study so that either outcome is reportable, and say so in the abstract.

---

## 7. Required Reading Added by This Search

The compression axis turned out to be actively worked. These must be cited, or a reviewer will assume the team was unaware of them.

1. **Physiological Information Preserving Video Compression for rPPG**, IEEE JBHI 2025. Codec design around rPPG preservation.
2. **Examining the Effects of Compression on Deep Learning Remote Photoplethysmography**, Electronic Imaging 2024.
3. **A comprehensive evaluation of multiple video compression algorithms for preserving BVP signal quality**, Biomedical Signal Processing and Control 2025.
4. **Effects of Video Compression Configuration on Remote Physiological Monitoring**, 2024.
5. **Enhancing H.264 Video Compression for Remote Photoplethysmography**, 2025.
6. **UMCL: Unimodal-generated Multimodal Contrastive Learning for Cross-compression rPPG**, IJCV 2026.
7. **Spatial Artifact Coherence Determines Codec Robustness in Patch-Based rPPG**, arXiv 2026. Defines a codec-artifact metric and proposes four codec-aware algorithms.
8. **Demographic bias in public remote photoplethysmography datasets**, npj Digital Medicine 2025. Source of the 5.2 to 14.1 BPM figures.
9. **Roadmap of remote photoplethysmography from heart rate measurement toward clinical translation**, npj Digital Medicine 2026.
10. **Remote photoplethysmography for camera-based vital sign estimation: a systematic literature review, challenges and deployment guidelines**, 2026. Reports that end-to-end and hybrid deep-learning models account for roughly 74 percent of studies published between 2023 and 2025.
11. **Nowara, McDuff and Veeraraghavan (2020)**, meta-analysis of skin tone and gender. Already in the main plan; now central.
12. **Nowara and McDuff (2019)**, combating the impact of video compression on non-contact vital sign measurement, ICCV Workshops. The compression half of the same group's work.

---

## 8. Consequences for the Existing Plan

### 8.1 The machine-learning baseline is now required, not optional

The 2026 systematic review reports that deep learning accounts for roughly 74 percent of recent rPPG studies. A purely classical evaluation now reads as dated, and reviewers will ask why only methods the field has moved past were tested.

The supervisor's suggestion was therefore correct and should be implemented as follows:

- Use **pretrained checkpoints from rPPG-Toolbox**. Do not train anything. This keeps the cost at two to three days rather than weeks.
- Pick **two models**, not five. One well established and widely cited, one recent.
- The neural model is a **baseline in the results grid**, never a component of the pipeline. Placing it inside the estimation path would destroy the Section 17 method-purity claim and turn the project into one more deep-learning rPPG paper.

### 8.2 The dataset problem is the main practical risk

**MMPD cannot serve as the primary dataset.** Its videos are already compressed to 320x240 for storage and transmission. Re-encoding already-compressed video confounds the study, because there is no clean high-bitrate control condition.

Options in order of preference:

1. **VitalVideo**: 893 subjects across all six Fitzpatrick types, the largest real-world rPPG dataset. Access terms and source video quality must be confirmed early.
2. **Own recordings**: recruiting Fitzpatrick IV to V participants in Dhaka is a genuine local advantage, and a pulse oximeter costs very little. Requires informed consent and an ethics statement.
3. **UBFC-rPPG**: uncompressed and freely available, but contains roughly 5 percent dark-skinned subjects, so it cannot carry the skin-tone axis alone. Useful as a clean control.

Confirming dataset access is the first blocking task.

### 8.3 The HRV capture-duration inconsistency still stands

Unrelated to this pivot but still unresolved: Section 7 step 1 of the main plan specifies a 20 to 30 second capture, while the LF band begins at 0.04 Hz whose period is 25 seconds. A 30 second window contains barely one cycle and cannot produce a valid LF/HF estimate. The Task Force standard specifies five minutes.

The main plan should be updated to specify two capture modes: a short rolling window for live BPM, and a separate longer capture of at least two minutes for the HRV reading.

---

## 9. Timeline to 20 November 2026

| Weeks | Focus |
|---|---|
| **1** | Verification and access. Native ACM DL and IEEE Xplore search by the supervisor as final confirmation. Confirm VitalVideo access and source quality. Read items 7, 8, 10 and 12 from Section 7. |
| **2 to 3** | Build the classical pipeline: green channel, CHROM, POS, quality metric, fusion. This is unchanged from the original plan. |
| **4** | Compression harness. Controlled re-encoding at defined bitrates with a lossless control. Validate that the harness itself does not introduce artifacts. |
| **5** | Neural baselines from rPPG-Toolbox pretrained checkpoints. |
| **6 to 7** | Run the full grid. Collect all results. |
| **8** | Statistical analysis including the interaction test. Bland-Altman per group. |
| **9** | Own data collection if public datasets prove insufficient on the skin-tone axis. |
| **10** | Write the extended abstract. |
| **11** | Design and produce the poster. |
| **12** | Buffer. Do not plan work here. |

Weeks 2 and 3 also deliver the course project, so the two obligations overlap rather than compete.

---

## 10. Open Risks

| Risk | Severity | Mitigation |
|---|---|---|
| A prior study exists that the search missed | High | Supervisor runs native ACM DL and IEEE Xplore search in week 1 before further commitment |
| No dataset with both clean source video and skin-tone diversity | **High** | Confirm VitalVideo in week 1; fall back to own recordings, budgeting week 9 |
| The effect does not exist and curves stay parallel | Medium | Frame the abstract so a negative result is reportable; it contradicts a reasonable prior and is worth knowing |
| Interaction test underpowered by small subject counts per group | Medium | Determine required group sizes before collection, not after |
| Scope creep back toward the original four threads | Medium | The poster makes exactly one claim. HRV, rBCG and SCG all move to future work |

---

## 11. Verification Still Outstanding

The following must be completed before committing the full twelve weeks:

1. **Native ACM Digital Library full-text search** for `rPPG AND (compression OR bitrate) AND (skin tone OR Fitzpatrick)`, using institutional access.
2. **Native IEEE Xplore search**, same terms.
3. **Forward citation chase from Nowara et al. 2020.** Any group extending that meta-analysis into compression would cite it.
4. **Read the 2026 systematic literature review in full.** If it names this gap explicitly, that single citation justifies the entire poster.
5. **Confirm VitalVideo access terms and source video quality.**

Items 1 through 3 should take one supervisor-afternoon and are cheap insurance on a twelve-week commitment.
