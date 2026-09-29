"""TRACE v5: per-method priors for all three methods, judged three ways.

    .venv/Scripts/python.exe scripts/tune_fusion_v5.py --ubfc D:/datasets/ubfc [--freeze]

v4 gave only POS a prior. Real volunteers showed green winning windows it
should not (a sharp but wrong peak), so v5 also lets green and CHROM have a
prior below 1. Selection options change which method is trusted, never a
method's own read-out, so every window's per-method numbers are computed once
(scripts/tune_fusion_v4.window_numbers) and every setting is scored from them.

Three evaluations, so nothing is judged on the data it was tuned on:
  A. tuned on UBFC-rPPG + simulated tuning cohort, scored on the volunteers
  B. leave one volunteer out: tuned on UBFC + sim + the other volunteers,
     scored on the one left out, for every volunteer in turn
  C. the frozen v4, for reference, on the same readings
Volunteers are scored per watch reading exactly like collect.score_clip
(median of five read-outs around the lock time).

--freeze writes results/fusion_params_v5.json from the setting chosen on
UBFC + sim + all volunteers (the version the app would run); its volunteer
score is then in-sample, so the leave-one-out figure (B) is the honest one.
"""

from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import pickle
import sys
from pathlib import Path

import numpy as np

from _common import ROOT, UBFC_DIR
sys.path.insert(0, str(ROOT / "app"))
import collect  # noqa: E402
from tracerppg.datasets import load_dataset, reference_hr  # noqa: E402
from tracerppg.roi import Traces  # noqa: E402
from tracerppg.simeval import frozen_params  # noqa: E402
from tune_fusion_v4 import LONG_S, window_numbers  # noqa: E402

CACHE = ROOT / "results" / "raw" / "v5_window_numbers.pkl"


def select(nums: np.ndarray, prior: tuple[float, float, float], edge_bpm: float) -> tuple[float, float]:
    bpm, q, art = nums[:, 0], nums[:, 1], nums[:, 2]
    s = q * np.array(prior)
    for i in range(3):
        if edge_bpm and bpm[i] < edge_bpm and not any(abs(bpm[i] - bpm[j]) <= 5 for j in range(3) if j != i):
            s[i] = 0.0
    k = int(np.argmax(s))
    return bpm[k], q[k] / max((1.0 - art[k]) ** 2, 1e-9)


def readout(w, setting) -> tuple[float, float]:
    prior, edge_bpm, long_q = setting[:3], setting[3], setting[4]
    b, fq = select(w[20.0], prior, edge_bpm)
    if long_q and fq < long_q and w.get(LONG_S) is not None:
        b2, fq2 = select(w[LONG_S], prior, edge_bpm)
        if fq2 > fq:
            return b2, fq2
    return b, fq


def build(ubfc_root: Path) -> dict:
    base = frozen_params(3)
    data = {"ubfc": [], "sim": [], "vol": []}
    cache = ROOT / "data" / "cache" / "real" / hashlib.sha1(str(ubfc_root.resolve()).encode()).hexdigest()[:10]
    for rec in load_dataset(ubfc_root):
        p = cache / f"{rec.subject}.npz"
        if not p.exists():
            continue
        tr = Traces.load(p)
        ok = tr.n_pixels > 200
        t, rgb = tr.t[ok], tr.rgb[ok]
        ends = np.arange(20.0, min(rec.duration_s, t[-1]) + 1e-9, 2.5)
        for e, ref in zip(ends, reference_hr(rec, [(x - 20.0, x) for x in ends])):
            n = window_numbers(t, rgb, e, base)
            if n[20.0] is not None and np.isfinite(ref):
                data["ubfc"].append((n, ref))
    for p in sorted((ROOT / "results" / "raw" / "scen_tune").glob("*.npz")):
        with np.load(p) as z:
            t, rgb, truth = z["t"], z["rgb"], z["truth"]
        for i, e in enumerate(np.arange(20.0, 20.0 + 2.5 * len(truth) - 1e-9, 2.5)):
            if i % 2 == 0 and np.isfinite(truth[i]):
                n = window_numbers(t, rgb, e, base)
                if n[20.0] is not None:
                    data["sim"].append((n, truth[i]))
    for m in collect.clips():
        F = collect.DATA / m["volunteer"] / m["clip"]
        if not (F / "trace.npz").exists():
            continue
        with np.load(F / "trace.npz") as z:
            t, rgb, npx = z["t"], z["rgb"], z["npx"]
        ok = np.all(np.isfinite(rgb), axis=1) & (npx > 200)
        t, rgb = t[ok], rgb[ok]
        for r in m.get("readings", []):
            lock = r["t"] - (0.0 if r.get("marked") else collect.TYPING_LAG_S)
            ends = [e for e in np.arange(lock - collect.MEDIAN_HALF_S, lock + collect.MEDIAN_HALF_S + 1e-9, collect.MEDIAN_STEP_S) if e >= 20.0]
            ws = [w for w in (window_numbers(t, rgb, e, base) for e in ends) if w[20.0] is not None]
            if ws:
                data["vol"].append({"person": m["volunteer"], "watch": r["bpm"], "windows": ws})
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    CACHE.write_bytes(pickle.dumps(data))
    return data


def err_windows(rows, s) -> np.ndarray:
    return np.array([abs(readout(n, s)[0] - ref) for n, ref in rows])


def err_readings(rows, s) -> np.ndarray:
    return np.array([abs(float(np.median([readout(w, s)[0] for w in r["windows"]])) - r["watch"]) for r in rows])


def single(rows, k) -> np.ndarray:
    return np.array([abs(float(np.median([w[20.0][k, 0] for w in r["windows"]])) - r["watch"]) for r in rows])


GRID = [(g, c, p, e, l) for g, c, p, e, l in itertools.product((1.0, 0.8, 0.6, 0.4, 0.2), (1.0, 0.8, 0.6), (1.0, 1.15, 1.3, 1.5, 2.0),
                                                                 (0.0, 55.0), (0.0, 0.25))]


def main(ubfc_root: Path, freeze: bool) -> None:
    data = pickle.loads(CACHE.read_bytes()) if CACHE.exists() else build(ubfc_root)
    vol = data["vol"]
    people = sorted({r["person"] for r in vol})
    print(f"windows: UBFC {len(data['ubfc'])}, sim {len(data['sim'])}; volunteers {len(people)} people, {len(vol)} readings")

    # cache every setting's errors once
    ub = {s: err_windows(data["ubfc"], s) for s in GRID}
    sm = {s: err_windows(data["sim"], s) for s in GRID}
    vr = {s: err_readings(vol, s) for s in GRID}
    by_person = {p: np.array([r["person"] == p for r in vol]) for p in people}

    v4 = (1.0, 1.0, 1.3, 55.0, 0.25)
    singles = {k: single(vol, i) for i, k in enumerate(("green", "chrom", "pos"))}
    fmt = lambda e: f"{e.mean():5.2f} ({np.mean(e <= 5):.0%})"
    print("\nVolunteers, single methods:  " + "  ".join(f"{k} {fmt(e)}" for k, e in singles.items()))
    print(f"C. frozen v4 {v4}:  volunteers {fmt(vr[v4])}")

    # A: choose on UBFC + sim only
    objA = {s: 0.5 * (ub[s].mean() + sm[s].mean()) for s in GRID}
    sA = min(GRID, key=objA.get)
    print(f"A. tuned on UBFC + sim: {sA}  UBFC {ub[sA].mean():.2f}, sim {sm[sA].mean():.2f} -> volunteers {fmt(vr[sA])}")

    # B: leave one volunteer out (UBFC, sim and the other volunteers weigh equally)
    loo = np.zeros(len(vol))
    chosen = {}
    for p in people:
        keep = ~by_person[p]
        obj = {s: (ub[s].mean() + sm[s].mean() + vr[s][keep].mean()) / 3 for s in GRID}
        s = min(GRID, key=obj.get)
        chosen[p] = s
        loo[by_person[p]] = vr[s][by_person[p]]
    print(f"B. leave one volunteer out: volunteers {fmt(loo)}")
    from collections import Counter
    print("   settings chosen across folds:", Counter(chosen.values()).most_common(3))

    # the effect the user asked about: lowering green's prior, everything else as v4
    print("\nGreen prior sweep (CHROM 1, POS 1.3, edge 55, long 0.25): UBFC / sim / volunteers")
    for g in (1.0, 0.8, 0.6, 0.4, 0.2):
        s = (g, 1.0, 1.3, 55.0, 0.25)
        print(f"   green {g:.1f}: {ub[s].mean():5.2f} / {sm[s].mean():5.2f} / {fmt(vr[s])}")

    if freeze:
        obj = {s: (ub[s].mean() + sm[s].mean() + vr[s].mean()) / 3 for s in GRID}
        s = min(GRID, key=obj.get)
        q, ok = [], []
        for rows in (data["ubfc"], data["sim"]):
            for n, ref in rows:
                b, fq = readout(n, s)
                q.append(fq); ok.append(abs(b - ref) <= 5)
        for r in vol:
            for w in r["windows"]:
                b, fq = readout(w, s)
                q.append(fq); ok.append(abs(b - r["watch"]) <= 5)
        q, ok = np.array(q), np.array(ok, float)
        wv = np.zeros(2)
        X = np.column_stack([np.ones_like(q), q])
        for _ in range(200):
            pr = 1 / (1 + np.exp(-X @ wv))
            wv += np.linalg.solve((X * (pr * (1 - pr))[:, None]).T @ X + 1e-6 * np.eye(2), X.T @ (ok - pr))
        base = frozen_params(4)
        params = {**base, "version": 5, "prior": {"green": s[0], "chrom": s[1], "pos": s[2]}, "edge_bpm": s[3], "edge_penalty": 0.0,
                  "long_quality": s[4], "long_window_s": LONG_S if s[4] else 0.0,
                  "confidence": float(-wv[0] / wv[1]), "logistic": [float(wv[0]), float(wv[1])],
                  "tuned_on": f"UBFC-rPPG ({len(data['ubfc'])} windows) + simulated tuning cohort ({len(data['sim'])} windows) + "
                              f"{len(people)} volunteers ({len(vol)} watch readings), equal weight",
                  "evaluation": {"volunteers_leave_one_out_mae": float(loo.mean()), "volunteers_leave_one_out_within5": float(np.mean(loo <= 5)),
                                 "volunteers_in_sample_mae": float(vr[s].mean()), "ubfc_mae": float(ub[s].mean()), "sim_tune_mae": float(sm[s].mean()),
                                 "v4_volunteers_mae": float(vr[v4].mean()),
                                 "pos_volunteers_mae": float(singles["pos"].mean())}}
        (ROOT / "results" / "fusion_params_v5.json").write_text(json.dumps(params, indent=1))
        print(f"\nfrozen v5: {s}, confidence {params['confidence']:.3f}; in-sample volunteers {vr[s].mean():.2f}, "
              f"leave-one-out {loo.mean():.2f}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--ubfc", default=str(UBFC_DIR))
    ap.add_argument("--freeze", action="store_true")
    ap.add_argument("--rebuild", action="store_true")
    a = ap.parse_args()
    if a.rebuild and CACHE.exists():
        CACHE.unlink()
    main(Path(a.ubfc), a.freeze)
