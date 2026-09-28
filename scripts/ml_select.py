"""A learned method selector, compared with TRACE (option 2). Runs in .venv-nn.

    .venv-nn/Scripts/python.exe scripts/ml_select.py

Outside the physiological pipeline (CLAUDE.md Rule 1.3.1): it never changes a
number TRACE reports, it is scored next to it. Trained only on UBFC-rPPG and
the simulated tuning cohort (results/raw/ml_features.npz from
scripts/ml_features.py), then applied once to the volunteers. For each window
the model estimates, for green, CHROM and POS, the chance that the method is
within 5 BPM, and picks the most likely one; each watch reading is then scored
with the same five read-out median as every other method.

Also reports the oracle: the per-window pick of whichever method is closest to
the watch. It is not a method (it looks at the answer); it is the ceiling any
selector, TRACE or learned, could reach with these three methods.
"""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

import numpy as np
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.model_selection import GroupKFold

ROOT = Path(__file__).resolve().parents[1]
METHODS = ("green", "chrom", "pos")


def model() -> HistGradientBoostingClassifier:
    return HistGradientBoostingClassifier(max_depth=3, max_iter=200, learning_rate=0.05, l2_regularization=1.0,
                                          random_state=0)


def pick(proba: np.ndarray) -> np.ndarray:
    """Rows come in threes (green, CHROM, POS) per window: the index of the most likely method."""
    return proba.reshape(-1, 3).argmax(axis=1)


def main() -> None:
    z = np.load(ROOT / "results" / "raw" / "ml_features.npz", allow_pickle=False)
    Xtr, ytr, gtr, src, Xte = z["Xtr"], z["ytr"], z["gtr"], z["src"], z["Xte"]
    meta = json.loads(str(z["meta"]))
    ref_w = Xtr[:, 3].reshape(-1, 3)  # method BPMs per training window

    # sanity check on the training data itself: leave whole subjects out
    cv_pick = np.zeros(len(Xtr) // 3, int)
    groups = gtr[::3]
    for tr_i, te_i in GroupKFold(n_splits=5).split(np.zeros(len(groups)), groups=groups):
        rows = lambda w: (w[:, None] * 3 + np.arange(3)).ravel()
        m = model().fit(Xtr[rows(tr_i)], ytr[rows(tr_i)])
        cv_pick[te_i] = pick(m.predict_proba(Xtr[rows(te_i)])[:, 1])
    ok = ytr.reshape(-1, 3)
    ubfc = src[::3] == "ubfc"
    print("Held-out check on the training sources (subjects left out), share of windows within 5 BPM:")
    for name, mask in (("UBFC", ubfc), ("simulated", ~ubfc)):
        sel = ok[mask, cv_pick[mask]].mean()
        print(f"  {name:10s} selector {sel:.0%} | green {ok[mask, 0].mean():.0%} chrom {ok[mask, 1].mean():.0%} "
              f"pos {ok[mask, 2].mean():.0%} | oracle {ok[mask].any(axis=1).mean():.0%}")

    # final model on everything, applied once to the volunteers
    final = model().fit(Xtr, ytr)
    choice = pick(final.predict_proba(Xte)[:, 1])
    bpm_te = Xte[:, 3].reshape(-1, 3)
    per = defaultdict(lambda: defaultdict(list))
    for i, r in enumerate(meta):
        key = (r["volunteer"], r["clip"], r["reading"])
        per[key]["watch"] = r["watch"]
        per[key]["vol"] = r["volunteer"]
        per[key]["fz"] = r["fitzpatrick"]
        for m in METHODS:
            per[key][m].append(r[m])
        per[key]["trace"].append(r["trace"])
        per[key]["ml"].append(bpm_te[i, choice[i]])
        per[key]["oracle"].append(bpm_te[i, np.argmin(np.abs(bpm_te[i] - r["watch"]))])
    cols = (*METHODS, "trace", "ml", "oracle")
    err = {c: [] for c in cols}
    by_vol = defaultdict(lambda: {c: [] for c in cols})
    for k, d in per.items():
        for c in cols:
            e = abs(float(np.median(d[c])) - d["watch"])
            err[c].append(e)
            by_vol[d["vol"]][c].append(e)
    n = len(err["pos"])
    print(f"\nVolunteers: {len(by_vol)} people, {n} watch readings (median of the five read-outs per reading)")
    names = {"trace": "TRACE", "ml": "TRACE+ML selector", "oracle": "oracle (ceiling)"}
    for c in cols:
        e = np.array(err[c])
        print(f"  {names.get(c, c):18s} MAE {e.mean():6.2f}  within 5 {np.mean(e <= 5):4.0%}")
    print("\nPer person (MAE):  " + "  ".join(f"{c[:5]:>6s}" for c in cols))
    for v, d in sorted(by_vol.items()):
        print(f"  {v:5s}            " + "  ".join(f"{np.mean(d[c]):6.1f}" for c in cols))
    out = {"n_people": len(by_vol), "n_readings": n,
           "mae": {c: float(np.mean(err[c])) for c in cols},
           "within5": {c: float(np.mean(np.array(err[c]) <= 5)) for c in cols},
           "per_person": {v: {c: float(np.mean(d[c])) for c in cols} for v, d in by_vol.items()},
           "trained_on": "UBFC-rPPG (22 subjects, 410 windows) + simulated tuning cohort (1080 windows)",
           "model": "HistGradientBoostingClassifier(max_depth=3, 200 iterations), picks the method most likely within 5 BPM",
           "trace_version": int(json.loads((ROOT / "results" / "fusion_params_v4.json").read_text())["version"]) if (ROOT / "results" / "fusion_params_v4.json").exists() else 3}
    (ROOT / "results" / "ml_volunteers.json").write_text(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
