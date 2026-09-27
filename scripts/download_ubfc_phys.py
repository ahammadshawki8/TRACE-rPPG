"""Download UBFC-Phys rest and talking recordings, laid out like UBFC-rPPG.

    .venv/Scripts/python.exe scripts/download_ubfc_phys.py --dest D:/datasets/ubfcphys --subjects 1 2 3 4

UBFC-Phys (Meziati Sabour et al., IEEE Trans. Affective Computing 2021) films
each person three times with the same kind of camera as UBFC-rPPG: T1 at
rest, T2 giving a speech (talking, natural head motion, expressions) and T3
doing mental arithmetic. A wrist Empatica E4 records the blood volume pulse
(BVP, 64 Hz) during each task, synchronised with the video. T1 against T2 of
the same person is a paired test of what motion does to each method.

Each task becomes its own folder, `s<N>_T<k>/vid.avi` plus a
`ground_truth.txt` in the UBFC DATASET_2 layout (row 0 BVP, row 1 HR left
as NaN because E4 gives none here, row 2 time), so `eval_real_fusion.py`
reads it unchanged. The mirror is phanquythinh/ubfc-phys-s1-s14 on Kaggle
(subjects 1 to 14 of 56); videos are about 5 GB per task.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import numpy as np

import download_ubfc as D
from _common import ROOT  # noqa: F401  (puts src/ on the path)
from tracerppg.datasets import write_ubfc2_ground_truth

KAGGLE = "phanquythinh/ubfc-phys-s1-s14"
BVP_FS = 64.0


def convert_bvp(csv: Path, out: Path) -> None:
    bvp = np.loadtxt(csv, delimiter=",").ravel()
    t = np.arange(bvp.size) / BVP_FS
    write_ubfc2_ground_truth(out, bvp, np.full(bvp.size, np.nan), t)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dest", default="D:/datasets/ubfcphys")
    ap.add_argument("--subjects", type=int, nargs="*", default=[1, 2, 3, 4])
    ap.add_argument("--tasks", type=int, nargs="*", default=[2, 1], help="2 = talking, 1 = rest")
    a = ap.parse_args()
    dest = Path(a.dest)
    size = D.sizes(KAGGLE)
    jobs = [(s, k) for s in a.subjects for k in a.tasks]

    def remote(s: int, k: int, kind: str) -> str:
        return f"s{s}/s{s}/{kind}_s{s}_T{k}.{'avi' if kind == 'vid' else 'csv'}"

    def present(p: Path) -> int:
        part = p.with_name(p.name + ".part")
        return p.stat().st_size if p.exists() else part.stat().st_size if part.exists() else 0

    total = sum(size.get(remote(s, k, "vid"), 0) + size.get(remote(s, k, "bvp"), 0) for s, k in jobs)
    D.PROG = D.Progress(total, sum(present(dest / f"s{s}_T{k}" / "vid.avi") for s, k in jobs))
    for s, k in jobs:
        folder = dest / f"s{s}_T{k}"
        folder.mkdir(parents=True, exist_ok=True)
        print(f"s{s}_T{k}", flush=True)
        for kind, local in (("bvp", "bvp.csv"), ("vid", "vid.avi")):
            for attempt in range(5):
                try:
                    D.fetch(remote(s, k, kind), folder / local, KAGGLE)
                    break
                except Exception as exc:
                    print(f"  retry {attempt + 1} after {exc}", flush=True)
                    time.sleep(10)
            else:
                print(f"PROGRESS WARNING: gave up on s{s}_T{k} {kind}", flush=True)
        if (folder / "bvp.csv").exists() and not (folder / "ground_truth.txt").exists():
            convert_bvp(folder / "bvp.csv", folder / "ground_truth.txt")
    print("PROGRESS finished", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
