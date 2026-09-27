"""Choose the liveness rule's quality threshold on development volunteers.

    .venv/Scripts/python.exe scripts/tune_liveness.py

A pulse is "found" in a read-out when CHROM and POS each reach a quality of
at least Q and agree within 5 BPM; the verdict looks at the last 10 s
(engine.LIVENESS_READOUTS). Development cohort: living faces and photos
(pulse off) under still, talking, flickering lamp, dim room and darkest skin,
seeds 1 to 4. The chosen Q is the one that accepts the most living faces
with no photo ever accepted. step10 then checks it on other seeds.
Writes results/liveness_params.json.
"""

from __future__ import annotations

import json
import sys
from collections import deque
from concurrent.futures import ProcessPoolExecutor

import numpy as np

from _common import ROOT
from tracerppg.datasets import resample_uniform
from tracerppg.fusion import artifact_reference, band_limited_pulses, fuse
from tracerppg.simeval import FS, frozen_params, stream
from tracerppg.simulate import LiveParams, LiveSimulator

sys.path.insert(0, str(ROOT / "app"))
CONDITIONS = {"still": dict(motion=0.1), "talking": dict(motion=1.2), "flicker": dict(flicker_hz=1.5),
              "dim": dict(light=0.35), "dark skin": dict(fitzpatrick=6)}
QS = [0.10, 0.15, 0.20, 0.24, 0.27]


def run(job):
    name, pulse, seed = job
    P = frozen_params()
    t, rgb = stream(LiveSimulator(LiveParams(pulse=pulse, **CONDITIONS[name]), seed=seed), 50)
    votes = []
    for te in np.arange(20, 50.01, 0.5):
        m = (t > te - 20) & (t <= te)
        cols = np.column_stack([resample_uniform(t[m], rgb[m, c], FS)[1] for c in range(3)])
        fr = fuse(band_limited_pulses(cols, FS), FS, P["gamma"], P["confidence"], artifact=artifact_reference(cols, FS), mask_k=P["mask_k"])
        c, p = fr.per_method["chrom"], fr.per_method["pos"]
        votes.append((min(c.quality, p.quality), abs(c.bpm - p.bpm) <= 5.0))
    return name, pulse, seed, votes


def verdicts(votes, q):
    from engine import LIVENESS_READOUTS, _liveness_verdict
    h = deque(maxlen=LIVENESS_READOUTS)
    for qual, agree in votes:
        h.append(qual >= q and agree)
    return _liveness_verdict(h)["verdict"]


def main():
    jobs = [(n, pulse, s) for n in CONDITIONS for pulse in (1.0, 0.0) for s in (1, 2, 3, 4)]
    with ProcessPoolExecutor(4) as ex:
        res = list(ex.map(run, jobs))
    table = []
    for q in QS:
        live = [verdicts(v, q) for n, pulse, s, v in res if pulse == 1.0]
        photo = [verdicts(v, q) for n, pulse, s, v in res if pulse == 0.0]
        row = {"q": q, "live_pulse": live.count("pulse") / len(live), "live_none": live.count("none") / len(live),
               "photo_pulse": photo.count("pulse") / len(photo)}
        table.append(row)
        print(f"  Q {q:.2f}: living -> pulse {row['live_pulse']:.0%}, wrongly 'none' {row['live_none']:.0%} | photo -> wrongly 'pulse' {row['photo_pulse']:.0%}")
    safe = [r for r in table if r["photo_pulse"] == 0]
    best = max(safe, key=lambda r: (r["live_pulse"], -r["live_none"]))
    print(f"\n  chosen Q = {best['q']} (no photo accepted in development, most living faces accepted)")
    (ROOT / "results" / "liveness_params.json").write_text(json.dumps(
        {"min_quality": best["q"], "agree_bpm": 5.0, "chosen_on": "simulated seeds 1 to 4, 5 conditions, living and photo",
         "table": table}, indent=1))


if __name__ == "__main__":
    main()
