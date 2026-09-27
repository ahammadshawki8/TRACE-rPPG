"""Scenario sweep: every skin type under every presenter-controllable condition.

    .venv/Scripts/python.exe scripts/sim_scenarios.py [--seconds 60] [--seeds 3] [--workers 4]

Each run renders one simulated volunteer with the live simulator and reads
it with exactly the analysis the app performs (tracerppg.simeval), every
2.5 s from 20 s on. Output:
    results/scenarios_sim.csv          one row per read-out
    app/static/lab/scenarios.json      per-scenario and per-skin summaries for the app

Everything here is simulated. It answers "which method does TRACE trust in
which condition, and is the result right", with the true rate known exactly.
"""

from __future__ import annotations

import argparse
import json
import time
from concurrent.futures import ProcessPoolExecutor

import numpy as np
import pandas as pd

from _common import ROOT
from tracerppg.simeval import evaluate
from tracerppg.simulate import LiveParams, LiveSimulator

METHODS = ("green", "chrom", "pos")

# name, label, settings, what the presenter would do to cause it
SCENARIOS = [
    ("still", "Still, good light", dict(motion=0.1), "Sit still facing a lamp"),
    ("natural", "Natural sitting", dict(motion=0.5), "Sit normally"),
    ("talking", "Talking", dict(motion=1.2), "Talk or nod"),
    ("restless", "Restless", dict(motion=2.5), "Turn the head, shift in the chair"),
    ("dim", "Dim room", dict(light=0.35), "Turn most lights off"),
    ("bright", "Very bright light", dict(light=1.45), "Strong lamp close to the face"),
    ("flicker", "Flickering lamp (90/min)", dict(flicker_hz=1.5, flicker_depth=0.03), "A lamp whose brightness pulses"),
    ("screen", "Screen glow", dict(screen_light=0.008), "Face lit by a changing screen"),
    ("fast", "Fast heart (120 BPM)", dict(bpm=120.0), "After exercise"),
    ("slow", "Slow heart (52 BPM)", dict(bpm=52.0), "Deep rest"),
]


def run_one(job: tuple) -> list[dict]:
    name, settings, fz, seed, seconds = job
    params = LiveParams(**{**settings, "fitzpatrick": fz})
    rows = evaluate(LiveSimulator(params, seed=seed), seconds)
    out = []
    for r in rows:
        row = {"scenario": name, "fitzpatrick": fz, "seed": seed, "t": r["t"], "truth": r["truth"],
               "trace": r["bpm"], "quality": r["quality"], "confident": r["confident"], "p_correct": r["p_correct"],
               "green_amp": r["green_amp"]}
        for m in METHODS:
            row[m] = r["methods"][m]["bpm"]
            row[f"q_{m}"] = r["methods"][m]["quality"]
            row[f"a_{m}"] = r["methods"][m]["artifact"]
            row[f"w_{m}"] = r["weights"][m]
        out.append(row)
    return out


def summarise(d: pd.DataFrame) -> dict:
    err = {m: (d[m] - d["truth"]).abs() for m in (*METHODS, "trace")}
    w = d[[f"w_{m}" for m in METHODS]].to_numpy()
    dom = w.argmax(axis=1)
    conf = d["confident"].astype(bool)
    ratio = d["trace"] / d["truth"]
    return {
        "n": int(len(d)),
        "mae": {m: float(e.mean()) for m, e in err.items()},
        "within5": {m: float((e <= 5).mean()) for m, e in err.items()},
        "weights": {m: float(d[f"w_{m}"].mean()) for m in METHODS},
        "dominant": {m: float(np.mean(dom == i)) for i, m in enumerate(METHODS)},
        "confident": float(conf.mean()),
        "mae_confident": float(err["trace"][conf].mean()) if conf.any() else None,
        "mae_flagged": float(err["trace"][~conf].mean()) if (~conf).any() else None,
        "within5_confident": float((err["trace"][conf] <= 5).mean()) if conf.any() else None,
        "harmonic": float((((ratio - 2).abs() < 0.12) | ((ratio - 0.5).abs() < 0.06)).mean()),
    }


def main(seconds: float, seeds: int, workers: int) -> None:
    jobs = [(name, s, fz, 7000 + 100 * i + 10 * fz + k, seconds)
            for i, (name, _, s, _) in enumerate(SCENARIOS) for fz in range(1, 7) for k in range(seeds)]
    print(f"{len(jobs)} runs of {seconds:.0f} s on {workers} workers")
    t0, rows = time.time(), []
    with ProcessPoolExecutor(max_workers=workers) as ex:
        for i, out in enumerate(ex.map(run_one, jobs, chunksize=1)):
            rows.extend(out)
            if (i + 1) % 20 == 0:
                print(f"  {i + 1}/{len(jobs)} runs, {time.time() - t0:.0f} s")
    df = pd.DataFrame(rows)
    df.to_csv(ROOT / "results" / "scenarios_sim.csv", index=False)

    out = {"source": "simulated", "seconds": seconds, "seeds": seeds, "n_readouts": int(len(df)),
           "scenarios": [], "skins": list(range(1, 7))}
    for name, label, settings, how in SCENARIOS:
        d = df[df["scenario"] == name]
        out["scenarios"].append({"id": name, "label": label, "settings": settings, "how": how,
                                 "all": summarise(d),
                                 "by_skin": {str(fz): summarise(d[d["fitzpatrick"] == fz]) for fz in range(1, 7)}})
    out["overall"] = summarise(df)
    (ROOT / "app" / "static" / "lab" / "scenarios.json").write_text(json.dumps(out, indent=1))

    print(f"\n{'scenario':26s} {'green':>6s} {'chrom':>6s} {'pos':>6s} {'TRACE':>6s}  trusted most  confident  harmonic")
    for s in out["scenarios"]:
        a = s["all"]
        top = max(a["dominant"], key=a["dominant"].get)
        print(f"{s['label']:26s} " + " ".join(f"{a['mae'][m]:6.1f}" for m in (*METHODS, "trace")) +
              f"  {top.upper():6s} {a['dominant'][top]:.0%}   {a['confident']:.0%}      {a['harmonic']:.0%}")
    o = out["overall"]
    print(f"\noverall MAE: " + ", ".join(f"{m} {o['mae'][m]:.2f}" for m in (*METHODS, "trace")))
    print(f"confident on {o['confident']:.0%} of read-outs: MAE {o['mae_confident']:.2f} vs flagged {o['mae_flagged']:.2f}")
    print(f"total time {time.time() - t0:.0f} s")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--seconds", type=float, default=60.0)
    ap.add_argument("--seeds", type=int, default=3)
    ap.add_argument("--workers", type=int, default=4)
    a = ap.parse_args()
    main(a.seconds, a.seeds, a.workers)
