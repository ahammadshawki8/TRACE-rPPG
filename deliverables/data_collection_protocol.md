# TRACE-rPPG: Data Collection Protocol, Consent Form, and Data Handling

Status: ready for supervisor review and, where the institution requires it, ethics review. Nothing has been recorded yet.

## 1. Why own data is needed

The study asks whether video compression widens the skin-tone accuracy gap in remote photoplethysmography. That needs video that is (a) stored losslessly, so every bitrate can be derived from one clean source, and (b) diverse in skin tone, especially Fitzpatrick IV to VI. UBFC-rPPG is lossless but has about 5 percent dark-skinned subjects; MMPD is diverse but already compressed; VitalVideo is diverse but its distributed files may be lossy (to be checked). Recording in Dhaka covers exactly the missing range.

## 2. How many participants

The sample size is fixed before recruiting, from the simulation-based power analysis in `results/power_sim.csv` (produced by `scripts/analyze_grid.py`). It gives the probability of detecting a bitrate x skin-tone interaction of a given size (BPM per halving of bitrate) for a given number of participants per group, using the variance components measured in the simulated pilot.

Rule: choose the smallest group size with at least 80 percent power for the smallest interaction worth reporting, then add 15 percent for dropouts and unusable recordings. Record the chosen number and the reasoning here before the first session.

Groups: Fitzpatrick I to III and IV to VI, balanced. Record the full type (I to VI) for every participant so finer analysis stays possible.

## 3. Equipment

- Webcam: a fixed model for every session (Logitech C920 or similar), 640x480 at 30 fps, manual exposure and white balance locked (auto exposure changes brightness, which is a motion-like artifact).
- Lighting: one diffuse LED panel at about 45 degrees in front of the face, same position and brightness every session; no window light. Measure illuminance at the face with a phone lux app and record it.
- Reference: finger pulse oximeter with a PPG waveform output (CMS50E class, USB), on the left index finger.
- Computer: capture with `ffmpeg` to FFV1 (lossless), never to MP4.
- A printed Fitzpatrick reference card and a neutral grey card.

## 4. Session procedure (about 15 minutes per participant)

1. Welcome, explain the study, answer questions, obtain written consent (Section 6). Assign a participant code (P001, P002...). Never write names in any data file.
2. Fitzpatrick type: self-report questionnaire plus rater assessment against the card, both recorded. Photograph the grey card under the session lighting (for colour calibration).
3. Seat the participant 60 to 80 cm from the camera, face fully in frame, oximeter on the finger, hand resting on the table.
4. Synchronisation: start the oximeter log, then the video, then ask the participant to tap the table once with the oximeter hand (a visible event in the video and a motion spike in the PPG). Note the wall-clock time.
5. Recordings, each 2 minutes, in a fixed order:
   - R1 still: sit still, breathe normally.
   - R2 talking: read a printed paragraph aloud (natural motion).
   - R3 still again (needed for HRV: at least 2 minutes of steady recording).
6. Stop the video, then the oximeter log. Check both files are non-empty and the durations match.

Suggested capture command (Windows, DirectShow; replace the device name):

```
ffmpeg -f dshow -video_size 640x480 -framerate 30 -i video="HD Pro Webcam C920" -c:v ffv1 -level 3 -pix_fmt bgr0 P001_R1.mkv
```

## 5. Files and layout

```
data/own/P001_R1/
    vid.mkv            lossless FFV1
    ground_truth.txt   PPG, HR, time rows (UBFC DATASET_2 layout, written by a converter)
    meta.json          {"fitzpatrick": 5, "fitzpatrick_self": 5, "lux": 420, "sync_offset_s": ..., "recording": "R1"}
```

This layout is exactly what `tracerppg.datasets.load_dataset` reads, so the whole grid runs unchanged:

```
.venv/Scripts/python.exe scripts/run_grid.py --dataset data/own --tag own
.venv/Scripts/python.exe scripts/analyze_grid.py --tag own
```

## 6. Participant information and consent form

**Study title:** Does video compression affect how accurately a camera can measure heart rate on different skin tones?

**What we are doing.** We are testing a method that estimates heart rate from ordinary video of the face. We want to know whether the compression used by video calls makes it less accurate, and whether that depends on skin tone.

**What you will do.** Sit in front of a webcam for about 6 minutes in total, with a clip on one finger that measures your pulse. You will sit still for some of the time and read a short paragraph aloud for some of it. We will also ask you to describe your skin type using a printed chart.

**Risks.** None beyond sitting in a chair. The finger clip is the same kind used in clinics.

**Your video.** Your face will be recorded. The recordings are stored only on an encrypted drive held by the research team, labelled with a code rather than your name. They will never be published, shared outside the research team, or used for anything except this study. Only numbers derived from them (heart rate estimates, error statistics) appear in any publication. Recordings are deleted by (date: one year after the study ends) unless you tick the optional box below.

**No diagnosis.** This is not a medical test. We will not tell you anything about your health, and the measurements cannot be used to diagnose any condition.

**Your choice.** Taking part is voluntary. You may stop at any time during the session, and you may ask for your recordings to be deleted at any time before (date), without giving a reason.

**Contact.** (Supervisor name, department, email.)

Please tick each box and sign:

- [ ] I have read this information and had the chance to ask questions.
- [ ] I agree to be video recorded for this study.
- [ ] I understand my recordings will be kept confidential and deleted by (date).
- [ ] I understand I can withdraw at any time.
- [ ] Optional: I agree that my coded recordings may be kept for up to 5 years for follow-up research by the same team.

Participant code: ______   Signature: ______________   Date: ________

Researcher: ______________   Signature: ______________   Date: ________

## 7. Data handling statement (for the report and poster)

Recordings are stored losslessly on an encrypted drive, labelled by participant code; the key linking codes to names is kept separately on paper. Raw video never leaves the research team's machines and is never uploaded to any cloud service. Only derived numbers are published. Recordings are deleted one year after the study ends unless the participant opted in to longer retention. Participants may withdraw and have their data deleted at any time before that date.

## 8. Checklist before the first session

- [ ] Supervisor approval (and institutional ethics approval if required)
- [ ] Sample size chosen from the power analysis and written in Section 2
- [ ] Camera exposure and white balance locked; settings written down
- [ ] Oximeter export tested and converted to `ground_truth.txt` on a test recording
- [ ] One pilot session on a team member, run through `run_grid.py` end to end
