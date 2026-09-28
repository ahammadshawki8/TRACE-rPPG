"""Neural baselines on the volunteer videos (option 1), scored like every other method.

    .venv/Scripts/python.exe scripts/nn_volunteers.py

1. crops:  tracks the face in each saved volunteer video (the classical
           tracker) and stores 72x72 face crops, as the grid runner does
2. infer:  runs the pretrained PhysNet and FactorizePhys checkpoints in
           .venv-nn (scripts/nn_infer.py). Both were trained on PURE, never
           on our volunteers, so nothing here is fitted to this data.
3. score:  each predicted pulse goes through our own clean_pulse and FFT, and
           each watch reading is scored with the same rule as TRACE (median of
           five read-outs around the lock time; collect.score_clip)

Neural models stay outside the TRACE path (CLAUDE.md Rule 1.3.1); they are
comparison columns only. Caveat: they read the saved video (near-lossless
H.264 4:4:4), while the classical methods read the live trace for most clips.
Writes results/nn_volunteers.json; crops live in data/work/nn_vol (gitignored).
"""

from __future__ import annotations

import json
import subprocess
import sys
from collections import defaultdict

import numpy as np

from _common import ROOT
sys.path.insert(0, str(ROOT / "app"))
import collect  # noqa: E402
from tracerppg.preprocess import clean_pulse  # noqa: E402
from tracerppg.roi import extract_traces  # noqa: E402
from tracerppg.spectral import estimate_bpm  # noqa: E402

WORK = ROOT / "data" / "work" / "nn_vol"
MODELS = ("physnet", "factorizephys")


def main() -> None:
    WORK.mkdir(parents=True, exist_ok=True)
    clips = [m for m in collect.clips() if (collect.DATA / m["volunteer"] / m["clip"] / "video.mkv").exists()]
    for m in clips:
        key = f"{m['volunteer']}__{m['clip']}"
        if (WORK / f"{key}_nn.npz").exists() or (WORK / f"{key}_crops.npy").exists():
            continue
        tr = extract_traces(collect.DATA / m["volunteer"] / m["clip"] / "video.mkv", crop_size=72)
        np.save(WORK / f"{key}_crops.npy", tr.crops)
        np.save(WORK / f"{key}_t.npy", tr.t)
        print(f"crops {key}: {len(tr.t)} frames", flush=True)
    if list(WORK.glob("*_crops.npy")):
        subprocess.run([str(ROOT / ".venv-nn" / "Scripts" / "python.exe"), str(ROOT / "scripts" / "nn_infer.py"),
                        str(WORK), str(WORK)], check=True)

    err = defaultdict(list)
    per = defaultdict(lambda: defaultdict(list))
    for m in clips:
        key = f"{m['volunteer']}__{m['clip']}"
        t = np.load(WORK / f"{key}_t.npy")
        fs = (len(t) - 1) / (t[-1] - t[0])
        with np.load(WORK / f"{key}_nn.npz") as z:
            pulses = {mm: clean_pulse(z[mm][: len(t)], fs) for mm in MODELS}
        for r in m.get("readings", []):
            lock = r["t"] - (0.0 if r.get("marked") else collect.TYPING_LAG_S)
            ends = [e for e in np.arange(lock - collect.MEDIAN_HALF_S, lock + collect.MEDIAN_HALF_S + 1e-9, collect.MEDIAN_STEP_S) if e >= 20.0]
            for mm, p in pulses.items():
                reads = [estimate_bpm(p[(t > e - 20.0) & (t <= e)], fs).bpm for e in ends if e <= t[-1] + 0.5]
                if reads:
                    e_ = abs(float(np.median(reads)) - r["bpm"])
                    err[mm].append(e_)
                    per[m["volunteer"]][mm].append(e_)
    out = {"n_people": len(per), "n_readings": len(err[MODELS[0]]),
           "mae": {mm: float(np.mean(err[mm])) for mm in MODELS},
           "within5": {mm: float(np.mean(np.array(err[mm]) <= 5)) for mm in MODELS},
           "per_person": {v: {mm: float(np.mean(d[mm])) for mm in MODELS} for v, d in per.items()},
           "checkpoints": "PURE_PhysNet_DiffNormalized, PURE_FactorizePhys_FSAM_Res (rPPG-Toolbox, trained on PURE)"}
    (ROOT / "results" / "nn_volunteers.json").write_text(json.dumps(out, indent=1))
    print(json.dumps({k: out[k] for k in ("n_people", "n_readings", "mae", "within5")}, indent=1))
    for v, d in sorted(out["per_person"].items()):
        print(f"  {v}  " + "  ".join(f"{mm} {x:5.1f}" for mm, x in d.items()))


if __name__ == "__main__":
    main()
