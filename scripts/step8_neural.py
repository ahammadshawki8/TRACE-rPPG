"""T6 acceptance: pretrained neural baselines (inference only).

Checks that both checkpoints load with no unexplained key mismatch, that
they are trained on a dataset we never evaluate on (PURE), that they return
one prediction per frame, and that they recover heart rate on clean
simulated video. Their accuracy on dark skin and compressed video is
reported, not asserted: that is what the grid measures.

Run:  .venv/Scripts/python.exe scripts/step8_neural.py
"""

from __future__ import annotations

import shutil
import subprocess

import numpy as np

from _common import ROOT, WORKERS, check, finish, rule, sim_folder
from tracerppg.compress import Condition, encode
from tracerppg.datasets import load_recording, reference_hr, sliding_windows, window_slice
from tracerppg.preprocess import clean_pulse
from tracerppg.roi import extract_traces
from tracerppg.simulate import SimConfig
from tracerppg.spectral import estimate_bpm

NN_PY = ROOT / ".venv-nn" / "Scripts" / "python.exe"
CHECKPOINTS = {"physnet": "PURE_PhysNet_DiffNormalized.pth",
               "factorizephys": "PURE_FactorizePhys_FSAM_Res.pth"}
EVALUATED_ON = ("UBFC-rPPG", "simulated")

if __name__ == "__main__":
    rule("0. Environment")
    ok = NN_PY.exists() and (ROOT / "third_party" / "rPPG-Toolbox").exists()
    check("separate .venv-nn and a toolbox checkout exist (torch stays out of the core venv)", ok)
    core_has_torch = subprocess.run([str(ROOT / ".venv" / "Scripts" / "python.exe"), "-c", "import torch"],
                                    capture_output=True).returncode == 0
    check("the core pipeline environment has no torch", not core_has_torch)
    if not ok:
        finish()

    rule("1. No train/test overlap")
    for m, ck in CHECKPOINTS.items():
        trained_on = ck.split("_")[0]
        check(f"{m} is trained on {trained_on}, never an evaluation set",
              trained_on == "PURE" and trained_on not in EVALUATED_ON, ck)

    rule("2. Inference on simulated video")
    work = ROOT / "data" / "work" / "step8"
    shutil.rmtree(work, ignore_errors=True)
    work.mkdir(parents=True)
    cases = {}
    for fz in (2, 6):
        folder = sim_folder(SimConfig(fitzpatrick=fz, duration_s=30.0, motion=0.3, seed=800 + fz))
        rec = load_recording(folder)
        for cond in (Condition("lossless_rgb", "ffv1", None, "bgr0"), Condition("h264_100k", "h264", 100)):
            video = rec.video_path if cond.lossless else encode(rec.video_path, work, cond).path
            tr = extract_traces(video, crop_size=72)
            key = f"t{fz}_{cond.name}"
            np.save(work / f"{key}_crops.npy", tr.crops)
            cases[key] = (rec, tr)
    run = subprocess.run([str(NN_PY), str(ROOT / "scripts" / "nn_infer.py"), str(work), str(work)],
                         capture_output=True, text=True)
    check("both checkpoints load and run (only the documented bias1 key is absent)", run.returncode == 0,
          run.stderr.strip().splitlines()[-1] if run.returncode else "physnet, factorizephys")
    if run.returncode:
        finish()

    print("  case                 model           MAE (BPM)   frames")
    maes = {}
    for key, (rec, tr) in cases.items():
        z = np.load(work / f"{key}_nn.npz")
        ws = sliding_windows(min(rec.duration_s, tr.t[-1]))
        ref = reference_hr(rec, ws)
        for m in CHECKPOINTS:
            p = clean_pulse(z[m], tr.fps)
            est = np.array([estimate_bpm(p[window_slice(tr.t, a, b)], tr.fps).bpm for a, b in ws])
            maes[(key, m)] = float(np.mean(np.abs(est - ref)))
            print(f"  {key:20s} {m:14s} {maes[(key, m)]:8.2f}     {len(z[m])}/{len(tr.t)}")
            if key == "t2_lossless_rgb":
                check(f"{m} returns one prediction per frame", len(z[m]) == len(tr.t))
    for m in CHECKPOINTS:
        check(f"{m} recovers HR on clean light-skin simulated video (MAE < 3 BPM)",
              maes[("t2_lossless_rgb", m)] < 3.0, f"{maes[('t2_lossless_rgb', m)]:.2f} BPM")
    shutil.rmtree(work, ignore_errors=True)
    finish()
