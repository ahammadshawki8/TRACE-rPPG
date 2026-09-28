# Today's data collection: step by step

Two jobs for today, then hand the data to Claude to fold into the project
before tomorrow's presentation.

- **Part A:** download about 10 subjects of UBFC-rPPG (about 20 GB) to the D drive.
- **Part B:** record 20 to 30 volunteers in the app with a smartwatch.
- **Part C:** what to tell Claude when you are done.

Part A is mostly waiting for downloads, so start it first and do Part B while it runs.

---

## Part A: UBFC-rPPG subset

UBFC-rPPG DATASET_2 has 42 people filmed at 640x480, 30 fps, uncompressed.
Each recording comes with a finger pulse oximeter signal (CMS50E) recorded at
the same time. That oximeter is our "true" heart rate. Each subject is about
1.5 to 2 GB, so 10 subjects is roughly 20 GB.

### A1. Make the folders

```powershell
mkdir D:\datasets\ubfc
```

At the end every subject must look like this. Other nesting also works,
because the loader searches recursively.

```
D:\datasets\ubfc\
  subject1\
    vid.avi
    ground_truth.txt
  subject3\
    vid.avi
    ground_truth.txt
  ...
```

Keep each `vid.avi` and its `ground_truth.txt` together in the same folder.
Do not rename them.

### A2. Download: route 0, the project script (easiest, no account)

The Kaggle mirror serves single files without signing in, so one command
fetches 14 spread-out subjects (about 24 GB), resumes after interruptions and
prints overall progress with an ETA at every 10 percent:

```powershell
.venv\Scripts\python.exe scripts\download_ubfc.py --dest D:\datasets\ubfc
```

Choose your own subjects with `--subjects 1 3 5 ...`. Routes 1 and 2 below
are the manual fallbacks.

### A2b. Download: route 1, Kaggle by hand

The Kaggle mirror is `malekdinarito/ubfc-rppg-dataset`. It is 73 GB in total,
but you only download individual files.

**In the browser (simplest):**

1. Sign in at kaggle.com and open https://www.kaggle.com/datasets/malekdinarito/ubfc-rppg-dataset
2. In the **Data Explorer** on the right, open the DATASET_2 folders.
3. For each chosen subject, download `vid.avi` and `ground_truth.txt` (use the
   download icon next to each file). Save them into `D:\datasets\ubfc\subjectN\`.
4. If a file arrives as a `.zip`, extract it into the same subject folder.

**Or with the Kaggle command line (good for many files):**

```powershell
.venv\Scripts\python.exe -m pip install kaggle
```

1. On kaggle.com go to Settings, then API, then **Create New Token**. This downloads `kaggle.json`.
2. Put `kaggle.json` in `C:\Users\Shawki\.kaggle\`.
3. List the files and note the exact paths of the subjects you want:

```powershell
.venv\Scripts\kaggle.exe datasets files malekdinarito/ubfc-rppg-dataset --page-size 200
```

4. Download one file at a time into its subject folder. Replace the quoted path
   with the path exactly as the listing shows it:

```powershell
.venv\Scripts\kaggle.exe datasets download malekdinarito/ubfc-rppg-dataset -f "DATASET_2/subject1/vid.avi" -p D:\datasets\ubfc\subject1
.venv\Scripts\kaggle.exe datasets download malekdinarito/ubfc-rppg-dataset -f "DATASET_2/subject1/ground_truth.txt" -p D:\datasets\ubfc\subject1
```

Large files may arrive zipped (`vid.avi.zip`). Extract them in place.

### A3. Download: route 2, the official page (if Kaggle fails)

https://sites.google.com/view/ybenezeth/ubfcrppg links to a Google Drive
folder. This page was blocked on the university network before (a certificate
error), so try it from a mobile hotspot or home internet. Download the same
two files per subject.

### A4. Which subjects

Take **10 subjects**. If you can see the faces in the Kaggle previews, include
every darker-skinned subject you can find. UBFC is mostly lighter skin, and the
few darker faces are the most valuable ones for us. Otherwise take subjects
spread across the list, for example 1, 3, 5, 8, 10, 12, 14, 17, 20, 23.
If you have more time and disk, 15 is better than 10.

### A5. Check the download (takes seconds)

```powershell
cd C:\Users\Shawki\Desktop\Signal200
set TRACE_UBFC_DIR=D:\datasets\ubfc
.venv\Scripts\python.exe scripts\step2_ground_truth.py
```

This check reads every `ground_truth.txt` and confirms our heart rate from the
oximeter matches the rate the dataset provides. It should end with all checks
passed. If a subject fails, re-download that subject's two files.

### A6. Run the evaluation (optional today, Claude can do it)

```powershell
.venv\Scripts\python.exe scripts\eval_real_fusion.py --dataset D:\datasets\ubfc
```

The first run tracks the face in every video once and caches the colour
traces, so it can take several minutes per subject. It writes
`results\real_fusion_ubfc.json`, and the Scenarios screen shows it
automatically after a page refresh. Close other heavy programs while it runs:
this laptop has little free memory.

---

## Part B: record volunteers

### B1. What you need

- The laptop with the app running:
  ```powershell
  cd C:\Users\Shawki\Desktop\Signal200
  .venv\Scripts\python.exe app\server.py
  ```
  Then open http://127.0.0.1:8000 and go to **Collect**.
- A smartwatch that shows heart rate. Write down its model name.
- A lamp or a window for even light on the face. Avoid light coming from behind the person.
- A chair, so the person sits at arm's length from the webcam, about 50 to 70 cm.
- Close every other app that uses the camera (Zoom, Teams, the Camera app).

### B2. Who to record

- 20 to 30 people. **Aim for a range of skin types.** Deliberately recruit
  darker-skinned volunteers (types IV to VI), because they are the whole point
  of the skin-tone part of the project and the public datasets lack them.
- Adults are simplest. Anyone under 18 needs a parent or guardian to agree,
  and the form has a box for that.
- Mix of glasses and no glasses is fine. Ask them to push hair off the forehead.

### B3. Set up the room once

1. Light in front of the face, not behind. Turn off the overhead light if it flickers.
2. Keep the laptop screen dim, or angle it away. A bright screen lighting the
   face is the one condition that defeats every method.
3. Put the webcam at eye height if you can.
4. In Collect, type the **smartwatch model** once. It is remembered.

### B4. Register each volunteer (1 minute)

1. Click **New volunteer**.
2. Name or username is optional. It stays on this laptop and is never exported.
3. Choose the age group and, if they want, sex.
4. **Skin type, as the volunteer describes it:** read them the six descriptions
   and let them choose. Then, optionally, add your own rating under "as you rate it".
5. Read the consent text to them (or let them read it). Tick
   **"The volunteer has read this and agrees"**. For under 18, also tick the guardian box.
6. Save. The volunteer gets a code such as `V07`.

### B5. Record four clips per volunteer (about 6 minutes)

The PROTOCOL list under the volunteer shows the four clips. Click one to load its settings:

| Clip | What the volunteer does |
|---|---|
| still / room light | Sits still, looks at the camera, breathes normally |
| talking / room light | Talks naturally (count, describe their day) |
| still / dim room | Sits still with the lamp turned down or off, some light still on the face |
| head movement / room light | Slowly turns the head left and right, nods |

For each clip:

1. Put the watch on the volunteer's wrist, snug. They keep that arm on the
   table and still, even in the talking and movement clips.
2. Click **Start camera**. Wait until FACE, LIGHT and STILL show ready.
3. Start a heart-rate measurement on the watch **and** click **Start recording** at the same moment.
4. The watch measures for about 20 seconds and then shows a number. **The
   instant it shows the number, press Mark (or Space).** That freezes the
   time. Then type the number calmly and press Enter: typing speed no longer
   matters.
5. Restart the watch measurement straight away and repeat: Mark, type, restart.
   Readings count from 0:20 on, so a 90 s clip fits three of them.
6. At 1:30 capture stops and waits. If the watch is showing a last number,
   Mark it, type it, then click **Save recording**.
7. The result appears under **Just recorded**, a table of watch against TRACE,
   Green, CHROM and POS. You are done with that clip.

You read the watch and type. The volunteer only sits.

**Keep video?** Leave it off unless the volunteer explicitly agrees. Without
video only the colour averages are saved (about 60 KB per clip), which is all
the analysis needs. Video is about 100 MB per minute.

### B6. If something goes wrong

- **A reading was missed or mistyped:** discard the clip and record it again.
- **Face lost (the red box disappears):** ask them to face the camera, and add more light.
- **The camera shows a frozen picture:** click Stop camera, then Start camera.
  If that fails, restart the server (Ctrl+C in the terminal, then run it again).
- **A volunteer wants their data removed:** open their card under **Manage volunteers and recordings** and choose
  **Withdraw**. Everything is deleted and the deletion is logged.

### B7. Where the data is

`C:\Users\Shawki\Desktop\Signal200\data\own\`, one folder per volunteer code.
It is never committed to git. Back it up to the D drive at the end of the day:

```powershell
robocopy C:\Users\Shawki\Desktop\Signal200\data\own D:\trace-backup\own /E
```

### B8. Aim for today

| | Target |
|---|---|
| Volunteers | 20 minimum, 30 if possible |
| Clips | 4 per volunteer (80 to 120 clips) |
| Watch readings | 3 per clip (240 to 360 readings) |
| Skin types | At least 5 people of type IV or darker |
| Time | About 8 minutes per person, so about 3 to 4 hours for 25 people |

Two people make it faster: one runs the laptop, one briefs the next volunteer.

---

## Part C: when you are done

Tell Claude:

1. "UBFC is in D:\datasets\ubfc with N subjects", plus the output of `step2_ground_truth.py`.
2. "Volunteers are recorded, N people", and whether anything unusual happened
   (a watch that read strangely, a volunteer with heavy motion).

Claude will then run the UBFC evaluation, check the volunteer scoring, update
the Scenarios screen, and put the real numbers into the slides, the README and
the speech. Please do this before the night, so there is time to rehearse with the real numbers.
