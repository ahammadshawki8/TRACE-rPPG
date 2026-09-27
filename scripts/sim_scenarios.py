"""Scenario sweep: every skin type under every presenter-controllable condition.

    .venv/Scripts/python.exe scripts/sim_scenarios.py [--seconds 60] [--seeds 3] [--workers 4]
        [--seed-base 7000] [--tag sim] [--save-traces]

--rescore TAG re-reads the traces saved by an earlier --save-traces run with
the fusion parameters now in force (no video is rendered), and writes the
app's scenarios.json from them.

--save-traces keeps each run's skin-colour trace (results/raw/scen_<tag>/),
so fusion variants can be re-scored offline without re-rendering video.
Use different --seed-base values for tuning and testing (invariant 14).

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
from tracerppg.simeval import analyse, frozen_params, readouts, stream
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
    name, settings, fz, seed, seconds, trace_dir = job
    sim = LiveSimulator(LiveParams(**{**settings, "fitzpatrick": fz}), seed=seed)
    t, rgb = stream(sim, seconds)
    if trace_dir:
        truth = [sim.true_bpm(te, 20.0) for te in np.arange(20.0, seconds + 1e-9, 2.5)]
        np.savez_compressed(f"{trace_dir}/{name}_{fz}_{seed}.npz", t=t, rgb=rgb, truth=np.array(truth, dtype=float),
                            beats=np.asarray(sim.beat_times), scenario=name, fitzpatrick=fz, seed=seed)
    rows = readouts(t, rgb, sim, seconds, frozen_params())
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


def rescore_one(path: str) -> list[dict]:
    """Read-outs from one saved trace with the current parameters."""
    params = frozen_params()
    with np.load(path) as z:
        t, rgb, truth = z["t"], z["rgb"], z["truth"]
        name, fz, seed = str(z["scenario"]), int(z["fitzpatrick"]), int(z["seed"])
    out = []
    for i, te in enumerate(np.arange(20.0, 20.0 + 2.5 * len(truth) - 1e-9, 2.5)):
        r = analyse(t, rgb, te, params)
        if r is None or not np.isfinite(truth[i]):
            continue
        row = {"scenario": name, "fitzpatrick": fz, "seed": seed, "t": float(te), "truth": float(truth[i]),
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


def write_outputs(df: pd.DataFrame, tag: str, seconds: float, seeds: int, note: str = "") -> dict:
    out = {"source": "simulated", "seconds": seconds, "seeds": seeds, "n_readouts": int(len(df)),
           "scenarios": [], "skins": list(range(1, 7)), "fusion": frozen_params().get("version", 2), "note": note}
    for name, label, settings, how in SCENARIOS:
        d = df[df["scenario"] == name]
        out["scenarios"].append({"id": name, "label": label, "settings": settings, "how": how,
                                 "all": summarise(d),
                                 "by_skin": {str(fz): summarise(d[d["fitzpatrick"] == fz]) for fz in range(1, 7)}})
    out["overall"] = summarise(df)
    return out


def rescore(tag: str, workers: int) -> None:
    files = sorted(str(p) for p in (ROOT / "results" / "raw" / f"scen_{tag}").glob("*.npz"))
    with ProcessPoolExecutor(max_workers=workers) as ex:
        rows = [r for part in ex.map(rescore_one, files, chunksize=4) for r in part]
    df = pd.DataFrame(rows)
    seeds = int(df.groupby(["scenario", "fitzpatrick"])["seed"].nunique().max())
    out = write_outputs(df, tag, 60.0, seeds, f"re-scored from the saved {tag} traces (seeds never used for tuning)")
    (ROOT / "app" / "static" / "lab" / "scenarios.json").write_text(json.dumps(out, indent=1))
    df.to_csv(ROOT / "results" / f"scenarios_{tag}_v{out['fusion']}.csv", index=False)
    o = out["overall"]
    print(f"{len(files)} runs, {len(df)} read-outs, fusion v{out['fusion']}")
    print("overall MAE: " + ", ".join(f"{m} {o['mae'][m]:.2f}" for m in (*METHODS, "trace")))
    print(f"confident on {o['confident']:.0%}: MAE {o['mae_confident']:.2f} vs flagged {o['mae_flagged']:.2f}")


def main(seconds: float, seeds: int, workers: int, seed_base: int = 7000, tag: str = "sim", save: bool = False) -> None:
    trace_dir = ""
    if save:
        d = ROOT / "results" / "raw" / f"scen_{tag}"
        d.mkdir(parents=True, exist_ok=True)
        trace_dir = str(d)
    jobs = [(name, s, fz, seed_base + 100 * i + 10 * fz + k, seconds, trace_dir)
            for i, (name, _, s, _) in enumerate(SCENARIOS) for fz in range(1, 7) for k in range(seeds)]
    print(f"{len(jobs)} runs of {seconds:.0f} s on {workers} workers")
    t0, rows = time.time(), []
    with ProcessPoolExecutor(max_workers=workers) as ex:
        for i, out in enumerate(ex.map(run_one, jobs, chunksize=1)):
            rows.extend(out)
            if (i + 1) % 20 == 0:
                print(f"  {i + 1}/{len(jobs)} runs, {time.time() - t0:.0f} s")
    df = pd.DataFrame(rows)
    df.to_csv(ROOT / "results" / f"scenarios_{tag}.csv", index=False)

    out = {"source": "simulated", "seconds": seconds, "seeds": seeds, "n_readouts": int(len(df)),
           "scenarios": [], "skins": list(range(1, 7))}
    for name, label, settings, how in SCENARIOS:
        d = df[df["scenario"] == name]
        out["scenarios"].append({"id": name, "label": label, "settings": settings, "how": how,
                                 "all": summarise(d),
                                 "by_skin": {str(fz): summarise(d[d["fitzpatrick"] == fz]) for fz in range(1, 7)}})
    out["overall"] = summarise(df)
    if tag == "sim":
        (ROOT / "app" / "static" / "lab" / "scenarios.json").write_text(json.dumps(out, indent=1))
    else:
        (ROOT / "results" / f"scenarios_{tag}.json").write_text(json.dumps(out, indent=1))

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
    ap.add_argument("--seed-base", type=int, default=7000)
    ap.add_argument("--tag", default="sim")
    ap.add_argument("--save-traces", action="store_true")
    ap.add_argument("--rescore", default="")
    a = ap.parse_args()
    if a.rescore:
        rescore(a.rescore, a.workers)
    else:
        main(a.seconds, a.seeds, a.workers, a.seed_base, a.tag, a.save_traces)
