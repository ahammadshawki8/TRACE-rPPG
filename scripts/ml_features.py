"""Feature tables for the learned comparison stage (option 2, outside the pipeline).

    .venv/Scripts/python.exe scripts/ml_features.py [--ubfc D:/datasets/ubfc]

TRACE stays classical (CLAUDE.md Rule 1.3.1). This script only describes each
20 s window by numbers the classical pipeline already computes (every
method's BPM, spectral quality and artifact share, how far the methods agree)
so that a small learned selector (`scripts/ml_select.py`, in .venv-nn) can be
compared with TRACE. One row per (window, method); the label says whether that
method's BPM is within 5 BPM of the reference.

    train: UBFC-rPPG windows every 2.5 s against the contact oximeter, plus the
           simulated tuning cohort (results/raw/scen_tune, the set TRACE was
           tuned on; its test set scen_test is never used)
    test:  every volunteer watch reading, as the five read-outs the scoring
           rule uses (collect.score_clip), so TRACE and the learned selector
           are judged on exactly the same windows

Writes results/raw/ml_features.npz (gitignored).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

import numpy as np

from _common import ROOT, UBFC_DIR
sys.path.insert(0, str(ROOT / "app"))
import collect  # noqa: E402
from tracerppg.datasets import load_dataset, reference_hr  # noqa: E402
from tracerppg.roi import Traces  # noqa: E402
from tracerppg.simeval import analyse, frozen_params  # noqa: E402

METHODS = ("green", "chrom", "pos")
NAMES = ["is_green", "is_chrom", "is_pos", "bpm", "quality", "artifact", "quality_share", "quality_rank",
         "dist_to_median", "agree_count", "max_disagreement", "trace_quality", "low_edge", "high_rate"]


def rows_for(a: dict) -> np.ndarray:
    """Three feature rows (one per method) from one read-out of `simeval.analyse`."""
    bpm = np.array([a["methods"][m]["bpm"] for m in METHODS])
    q = np.array([a["methods"][m]["quality"] for m in METHODS])
    art = np.array([a["methods"][m]["artifact"] or 0.0 for m in METHODS])
    med = np.median(bpm)
    rank = np.argsort(np.argsort(-q))
    out = []
    for i in range(3):
        onehot = [1.0 if j == i else 0.0 for j in range(3)]
        agree = sum(abs(bpm[i] - bpm[j]) <= 5 for j in range(3) if j != i)
        out.append(onehot + [bpm[i], q[i], art[i], q[i] / max(q.sum(), 1e-9), rank[i], abs(bpm[i] - med), agree,
                             bpm.max() - bpm.min(), a["quality"], float(bpm[i] < 50), float(bpm[i] > 100)])
    return np.array(out, float)


def main(ubfc_root: Path) -> None:
    P = frozen_params()
    X, y, grp, src = [], [], [], []

    def add(a, ref, group, source):
        f = rows_for(a)
        X.append(f); y.append(np.abs(f[:, 3] - ref) <= 5); grp.extend([group] * 3); src.extend([source] * 3)

    # UBFC-rPPG: cached traces from eval_real_fusion.py
    cache = ROOT / "data" / "cache" / "real" / hashlib.sha1(str(ubfc_root.resolve()).encode()).hexdigest()[:10]
    n_ubfc = 0
    for rec in load_dataset(ubfc_root):
        p = cache / f"{rec.subject}.npz"
        if not p.exists():
            continue
        tr = Traces.load(p)
        ok = tr.n_pixels > 200
        t, rgb = tr.t[ok], tr.rgb[ok]
        ends = np.arange(20.0, min(rec.duration_s, t[-1]) + 1e-9, 2.5)
        refs = reference_hr(rec, [(e - 20.0, e) for e in ends])
        for e, ref in zip(ends, refs):
            a = analyse(t, rgb, e, P)
            if a is not None and np.isfinite(ref):
                add(a, ref, f"ubfc:{rec.subject}", "ubfc"); n_ubfc += 1
    # simulated tuning cohort
    n_sim = 0
    for p in sorted((ROOT / "results" / "raw" / "scen_tune").glob("*.npz")):
        with np.load(p) as z:
            t, rgb, truth = z["t"], z["rgb"], z["truth"]
        for i, e in enumerate(np.arange(20.0, 20.0 + 2.5 * len(truth) - 1e-9, 2.5)):
            if i % 2 or not np.isfinite(truth[i]):
                continue  # every 5 s is plenty and keeps UBFC's weight up
            a = analyse(t, rgb, e, P)
            if a is not None:
                add(a, truth[i], f"sim:{p.stem}", "sim"); n_sim += 1
    Xtr, ytr, gtr, str_ = np.concatenate(X), np.concatenate(y), np.array(grp), np.array(src)

    # volunteers: the same five read-outs per watch reading that collect.score_clip uses
    Xte, meta = [], []
    for m in collect.clips():
        folder = collect.DATA / m["volunteer"] / m["clip"]
        if not (folder / "trace.npz").exists():
            continue
        with np.load(folder / "trace.npz") as z:
            t, rgb, npx = z["t"], z["rgb"], z["npx"]
        ok = np.all(np.isfinite(rgb), axis=1) & (npx > 200)
        t, rgb = t[ok], rgb[ok]
        for k, r in enumerate(m.get("readings", [])):
            lock = r["t"] - (0.0 if r.get("marked") else collect.TYPING_LAG_S)
            ends = [e for e in np.arange(lock - collect.MEDIAN_HALF_S, lock + collect.MEDIAN_HALF_S + 1e-9, collect.MEDIAN_STEP_S) if e >= 20.0]
            for e in ends:
                a = analyse(t, rgb, e, P)
                if a is None:
                    continue
                Xte.append(rows_for(a))
                meta.append({"volunteer": m["volunteer"], "clip": m["clip"], "reading": k, "watch": r["bpm"],
                             "fitzpatrick": m["fitzpatrick"], "trace": a["bpm"], "confident": a["confident"],
                             **{mm: a["methods"][mm]["bpm"] for mm in METHODS}})
    out = ROOT / "results" / "raw"
    out.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(out / "ml_features.npz", Xtr=Xtr, ytr=ytr, gtr=gtr, src=str_, Xte=np.concatenate(Xte),
                        names=np.array(NAMES), meta=np.array(json.dumps(meta)))
    print(f"train windows: UBFC {n_ubfc}, simulated {n_sim}; test read-outs {len(meta)} from volunteers")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--ubfc", default=str(UBFC_DIR))
    main(Path(ap.parse_args().ubfc))
