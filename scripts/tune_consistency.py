"""TRACE consistency check: distrust a read-out that jumps away from TRACE's own recent read-outs.

    .venv/Scripts/python.exe scripts/tune_consistency.py --ubfc D:/datasets/ubfc [--freeze]

A resting heart rate does not move 15 BPM in a few seconds, but a spectral
peak can (a room-light rhythm, a harmonic, a motion burst wins one window).
So a read-out further than `tol` BPM from the median of TRACE's own read-outs
over the previous `hist` seconds is treated as a glitch:

    flag  the read-out keeps its BPM but is marked low confidence
    hold  TRACE reports that recent median instead (and marks it low confidence)

It only looks backwards, so it runs live exactly as offline; it never sees a
reference. Every recording is read every 2.5 s from 20 s on with the frozen
TRACE v5 selection, then the rule is applied along time. Scoring is unchanged:
volunteers as collect.score_clip (median of five read-outs around the watch
lock), UBFC per window against the oximeter, simulation against the truth.
Settings are compared the same way as v5: chosen on UBFC + sim + the other
volunteers, scored on the one volunteer left out.
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
from tracerppg.simeval import analyse, frozen_params  # noqa: E402

HOP = 2.5
CACHE = ROOT / "results" / "raw" / "consistency_sequences.pkl"


def sequence(t, rgb, P, t0=20.0, t1=None):
    """TRACE's read-out every HOP seconds: list of (end time, bpm, confident)."""
    t1 = t[-1] if t1 is None else t1
    out = []
    for e in np.arange(t0, t1 + 1e-9, HOP):
        a = analyse(t, rgb, e, P)
        if a is not None:
            out.append((float(e), float(a["bpm"]), bool(a["confident"])))
    return out


def build(ubfc_root: Path, P: dict) -> dict:
    data = {"ubfc": [], "sim": [], "vol": []}
    cache = ROOT / "data" / "cache" / "real" / hashlib.sha1(str(ubfc_root.resolve()).encode()).hexdigest()[:10]
    for rec in load_dataset(ubfc_root):
        p = cache / f"{rec.subject}.npz"
        if not p.exists():
            continue
        tr = Traces.load(p)
        ok = tr.n_pixels > 200
        seq = sequence(tr.t[ok], tr.rgb[ok], P, t1=min(rec.duration_s, tr.t[ok][-1]))
        refs = reference_hr(rec, [(e - 20.0, e) for e, _, _ in seq])
        data["ubfc"].append({"seq": seq, "ref": list(map(float, refs))})
    for p in sorted((ROOT / "results" / "raw" / "scen_tune").glob("*.npz")):
        with np.load(p) as z:
            t, rgb, truth = z["t"], z["rgb"], z["truth"]
        seq = sequence(t, rgb, P, t1=20.0 + HOP * (len(truth) - 1))
        ends = np.arange(20.0, 20.0 + HOP * len(truth) - 1e-9, HOP)
        tr = dict(zip(np.round(ends, 2), truth))
        data["sim"].append({"seq": seq, "ref": [float(tr.get(round(e, 2), np.nan)) for e, _, _ in seq]})
    for m in collect.clips():
        F = collect.DATA / m["volunteer"] / m["clip"]
        if not (F / "trace.npz").exists():
            continue
        with np.load(F / "trace.npz") as z:
            t, rgb, npx = z["t"], z["rgb"], z["npx"]
        ok = np.all(np.isfinite(rgb), axis=1) & (npx > 200)
        t, rgb = t[ok], rgb[ok]
        # read-outs on the 2.5 s grid plus the exact ends the scoring rule uses around each lock
        locks = [r["t"] - (0.0 if r.get("marked") else collect.TYPING_LAG_S) for r in m["readings"]]
        extra = sorted({round(float(e), 2) for L in locks for e in np.arange(L - 5, L + 5 + 1e-9, 2.5) if e >= 20.0})
        grid = sorted(set(np.round(np.arange(20.0, t[-1] + 1e-9, HOP), 2)) | set(extra))
        seq = []
        for e in grid:
            a = analyse(t, rgb, e, P)
            if a is not None:
                seq.append((float(e), float(a["bpm"]), bool(a["confident"])))
        data["vol"].append({"person": m["volunteer"], "seq": seq, "locks": locks, "watch": [r["bpm"] for r in m["readings"]]})
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    CACHE.write_bytes(pickle.dumps(data))
    return data


def apply(seq, tol: float, hist: float, mode: str):
    """The live rule along one recording: returns {end: (bpm, confident)}."""
    out = {}
    for i, (e, b, c) in enumerate(seq):
        prev = [bb for ee, bb, _ in seq[:i] if e - hist <= ee < e]
        if tol and len(prev) >= 3 and abs(b - float(np.median(prev))) > tol:
            out[e] = (float(np.median(prev)) if mode == "hold" else b, False)
        else:
            out[e] = (b, c)
    return out


def score_windows(rows, s):
    err, conf = [], []
    for r in rows:
        o = apply(r["seq"], *s)
        for (e, _, _), ref in zip(r["seq"], r["ref"]):
            if np.isfinite(ref):
                b, c = o[e]
                err.append(abs(b - ref)); conf.append(c)
    return np.array(err), np.array(conf)


def score_vol(rows, s):
    err, conf, who = [], [], []
    for r in rows:
        o = apply(r["seq"], *s)
        for L, w in zip(r["locks"], r["watch"]):
            ends = [round(float(e), 2) for e in np.arange(L - 5, L + 5 + 1e-9, 2.5) if e >= 20.0]
            vals = [o[e] for e in ends if e in o]
            if not vals:
                continue
            err.append(abs(float(np.median([v[0] for v in vals])) - w))
            conf.append(sum(v[1] for v in vals) > len(vals) / 2)
            who.append(r["person"])
    return np.array(err), np.array(conf), np.array(who)


GRID = [(0.0, 0.0, "flag")] + [(tol, hist, mode) for tol, hist, mode in itertools.product((10.0, 15.0, 20.0), (10.0, 20.0, 30.0), ("flag", "hold"))]


def main(ubfc_root: Path, freeze: bool) -> None:
    P = frozen_params(5)
    data = pickle.loads(CACHE.read_bytes()) if CACHE.exists() else build(ubfc_root, P)
    people = sorted({r["person"] for r in data["vol"]})
    fmt = lambda e: f"{e.mean():5.2f} ({np.mean(e <= 5):.0%})"
    cf = lambda e, c: f"confident {c.mean():.0%} at {e[c].mean():.2f}, flagged {e[~c].mean() if (~c).any() else float('nan'):.2f}"
    res = {s: (score_windows(data["ubfc"], s), score_windows(data["sim"], s), score_vol(data["vol"], s)) for s in GRID}
    print(f"volunteers: {len(people)} people, {len(res[GRID[0]][2][0])} readings\n")
    print("setting (tol, history s, mode) | UBFC | sim | volunteers | volunteer confidence")
    for s in GRID:
        (eu, cu), (es, cs), (ev, cv, _) = res[s]
        print(f"  {str(s):22s} | {eu.mean():5.2f} | {es.mean():5.2f} | {fmt(ev)} | {cf(ev, cv)}")

    ev0, cv0, who = res[GRID[0]][2]
    loo = np.zeros(len(ev0)); looc = np.zeros(len(ev0), bool)
    picks = []
    for p in people:
        keep = who != p
        obj = {s: (res[s][0][0].mean() + res[s][1][0].mean() + res[s][2][0][keep].mean()) / 3 for s in GRID}
        s = min(GRID, key=obj.get)
        picks.append(s)
        loo[who == p] = res[s][2][0][who == p]; looc[who == p] = res[s][2][1][who == p]
    from collections import Counter
    print(f"\nleave one volunteer out: {fmt(loo)}, {cf(loo, looc)}")
    print(f"   without the check (v5):  {fmt(ev0)}, {cf(ev0, cv0)}")
    print("   settings chosen:", Counter(picks).most_common(3))
    if freeze:
        s = Counter(picks).most_common(1)[0][0]
        p5 = json.loads((ROOT / "results" / "fusion_params_v5.json").read_text())
        p5["consistency"] = {"tol_bpm": s[0], "history_s": s[1], "mode": s[2]}
        p5["evaluation"]["consistency_leave_one_out_mae"] = float(loo.mean())
        p5["evaluation"]["consistency_leave_one_out_within5"] = float(np.mean(loo <= 5))
        p5["evaluation"]["consistency_confident_share"] = float(looc.mean())
        p5["evaluation"]["consistency_confident_mae"] = float(loo[looc].mean())
        (ROOT / "results" / "fusion_params_v5.json").write_text(json.dumps(p5, indent=1))
        print(f"frozen into v5: {p5['consistency']}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--ubfc", default=str(UBFC_DIR))
    ap.add_argument("--freeze", action="store_true")
    ap.add_argument("--rebuild", action="store_true")
    a = ap.parse_args()
    if a.rebuild and CACHE.exists():
        CACHE.unlink()
    main(Path(a.ubfc), a.freeze)
