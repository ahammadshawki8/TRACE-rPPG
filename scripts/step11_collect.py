"""Acceptance checks for the volunteer data collection portal (app/collect.py).

    .venv/Scripts/python.exe scripts/step11_collect.py

A real webcam and a real smartwatch are replaced by the live simulator and
its known heart rate, so the storage, consent rules, scoring and deletion
can be verified end to end without a person. Uses a scratch folder, never
the real data/own.
"""

from __future__ import annotations

import json
import shutil
import sys

import numpy as np

from _common import ROOT, check, finish, rule

sys.path.insert(0, str(ROOT / "app"))
import collect  # noqa: E402
from tracerppg.roi import FaceTracker, skin_mean  # noqa: E402
from tracerppg.simulate import LiveParams, LiveSimulator  # noqa: E402

SCRATCH = ROOT / "data" / "work" / "collect_check"


def refuses(body: dict) -> bool:
    try:
        collect.upsert_volunteer(body)
        return False
    except ValueError:
        return True


def main() -> None:
    shutil.rmtree(SCRATCH, ignore_errors=True)
    collect.DATA = SCRATCH

    rule("1. Consent and volunteer records")
    base = {"age_group": "18-29", "fitzpatrick_self": 4, "consent": True}
    check("nothing is stored without consent", refuses({**base, "consent": False}) and not (SCRATCH / "volunteers.json").exists())
    check("under 18 needs a parent or guardian", refuses({**base, "age_group": "under 18"}))
    check("a skin type is required", refuses({**base, "fitzpatrick_self": 0}))
    a = collect.upsert_volunteer({**base, "sex": "female"})
    b = collect.upsert_volunteer({**base, "age_group": "under 18", "guardian_consent": True, "fitzpatrick_self": 6})
    c = collect.upsert_volunteer({**base, "name": "Test Person"})
    check("volunteers get codes, and an optional name is kept", a["code"] == "V01" and b["code"] == "V02"
          and c["name"] == "Test Person" and a["name"] == "", f"{list(collect.volunteers())}")

    rule("2. Recording, storage and scoring (simulator stands in for webcam and watch)")
    sim = LiveSimulator(LiveParams(fitzpatrick=4, motion=0.1, bpm=78), seed=11)
    rec = collect.Recorder("V01", {"lighting": "room light", "motion": "still"}, 60, "simulated watch", False, {"backend": "sim"})
    # The protocol: the watch measures ~20 s and locks, so readings come at
    # 0:20, 0:40 and, after capture stops at 1:00, a final one.
    tracker, next_reading = FaceTracker(), 20.0
    for _ in range(int(62 * 30)):
        frame, t = sim.next_frame()
        box, _ = tracker.update(frame)
        mean, npx = skin_mean(frame, box) if box is not None else (None, 0)
        rec.add(frame, t, mean if npx > 200 else None, npx, box)
        if rec.capture_done:
            rec.watch_reading(round(sim.true_bpm(rec.elapsed, 20.0)))
            break
        if rec.elapsed >= next_reading and next_reading < rec.duration:
            rec.watch_reading(round(sim.true_bpm(t, 20.0)))  # a watch shows whole BPM
            next_reading += 20.0
    out = rec.finish(True)
    files = sorted(p.name for p in rec.dir.iterdir())
    check("a clip stores the trace and metadata, and no video unless asked",
          files == ["meta.json", "trace.npz"], f"{files}")
    with np.load(rec.dir / "trace.npz") as z:
        shapes = {k: z[k].shape for k in z.files}
    check("the stored trace holds colour averages, not images",
          shapes["rgb"] == (shapes["t"][0], 3) and all(len(s) <= 2 for s in shapes.values()),
          f"{shapes['t'][0]} frames, {(rec.dir / 'trace.npz').stat().st_size / 1e3:.0f} KB")
    s = out["score"]
    for r in s["rows"]:
        print(f"    t {r['t']:5.1f} watch {r['watch']:5.1f} TRACE {r['trace']:5.1f} green {r['green']:5.1f} chrom {r['chrom']:5.1f} pos {r['pos']:5.1f}")
    check("the three protocol readings (0:20, 0:40, 1:00) are all scored", s["n"] == 3 and [round(r["t"]) for r in s["rows"]] == [20, 40, 60],
          f"{[round(r['t']) for r in s['rows']]}")
    from tracerppg.simeval import analyse, frozen_params
    with np.load(rec.dir / "trace.npz") as z:
        keep = np.all(np.isfinite(z["rgb"]), axis=1) & (z["npx"] > 200)  # as score_clip does
        tt, rr = z["t"][keep], z["rgb"][keep]
    def lock_median(r):  # the scoring rule, restated independently: median read-out around the watch's lock time
        lock = r["t"] - collect.TYPING_LAG_S
        ends = [e for e in np.arange(lock - 5.0, lock + 5.0 + 1e-9, 2.5) if e >= 20.0]
        return float(np.median([analyse(tt, rr, e, frozen_params())["bpm"] for e in ends]))
    same = all(abs(lock_median(r) - r["trace"]) < 1e-9 for r in s["rows"])
    check("each score is the median read-out around the moment the watch locked", same,
          f"TRACE vs simulated watch MAE {s['mae']['trace']:.1f} BPM on this one volunteer (accuracy itself is judged in step10 and the sweep)")

    st = collect.study()
    check("the study summary groups by motion, lighting, skin type and age",
          st["n_readings"] == 3 and "still" in st["by_motion"] and "4" in st["by_skin"] and "18-29" in st["by_age"],
          f"{st['n_readings']} readings, {st['n_volunteers_scored']} volunteer")

    rows = collect.study()["rows"]
    check("names never reach the analysis or the CSV export", all("name" not in r for r in rows), f"{len(rows)} rows checked")

    rule("3. Withdrawal")
    collect.delete_volunteer("V01")
    check("withdrawing a volunteer deletes their record and every recording",
          not (SCRATCH / "V01").exists() and "V01" not in collect.volunteers())
    shutil.rmtree(SCRATCH, ignore_errors=True)
    finish()


if __name__ == "__main__":
    main()
