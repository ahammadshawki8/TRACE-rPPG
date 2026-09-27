"""Build the research console's evidence file from the grid results.

    .venv/Scripts/python.exe scripts/build_dashboard_data.py [--tag sim]

Writes app/static/lab/results.json. Every number the Experiments and
Compression screens show comes from here, so the page never recomputes
pipeline results in JavaScript (the build_viz pattern).

The central question for the fusion is whether per-window weighting beats a
fixed choice of method. Three comparisons answer it from the same windows:
  - each single method used for the whole grid (a fixed bet),
  - TRACE (quality-weighted fusion),
  - the per-window oracle: whichever of green, CHROM, POS happened to be
    closest in that window. No real system can do this; it is the ceiling.
And one direct check of the weights themselves: how often the method TRACE
weighted most was also the most accurate of the three in that window.
"""

from __future__ import annotations

import argparse
import json

import numpy as np
import pandas as pd

from _common import ROOT

CLASSICAL = ("green", "chrom", "pos")
SHOWN = ("green", "chrom", "pos", "trace", "pos_mask", "ica", "physnet", "factorizephys")
LABELS = {"green": "Green", "chrom": "CHROM", "pos": "POS", "trace": "TRACE", "pos_mask": "POS + mask",
          "ica": "ICA", "physnet": "PhysNet", "factorizephys": "FactorizePhys"}
RATES = ["lossless", "1600", "800", "400", "200", "100"]
CODECS = ("h264", "h265", "vp9")


def cond_name(codec: str, rate: str) -> str:
    return "lossless_rgb" if rate == "lossless" else f"{codec}_{rate}k"


def subject_mae(d: pd.DataFrame) -> pd.Series:
    """MAE per subject first, then averaged: every subject counts once."""
    e = (d["est_bpm"] - d["ref_bpm"]).abs()
    return e.groupby(d["subject"]).mean()


def selection_stats(g: pd.DataFrame) -> dict:
    """Per-window comparison of TRACE's weights with the three methods' errors."""
    key = ["subject", "condition", "window"]
    err = g[g["method"].isin(CLASSICAL)].assign(err=lambda d: (d["est_bpm"] - d["ref_bpm"]).abs())
    wide = err.pivot_table(index=key, columns="method", values="err")
    tr = g[g["method"] == "trace"].set_index(key)
    tr = tr.join(wide, how="inner")
    w = tr[["w_green", "w_chrom", "w_pos"]].to_numpy()
    e = tr[list(CLASSICAL)].to_numpy()
    dominant = w.argmax(axis=1)
    best = e.argmin(axis=1)
    # A window where two methods are within 1 BPM of each other has no real
    # "best"; count the dominant method as right if it is within 1 BPM of best.
    near_best = e[np.arange(len(e)), dominant] <= e.min(axis=1) + 1.0
    trace_err = (tr["est_bpm"] - tr["ref_bpm"]).abs().to_numpy()
    oracle = e.min(axis=1)
    return {
        "windows": int(len(tr)),
        "dominant_share": {m: float(np.mean(dominant == i)) for i, m in enumerate(CLASSICAL)},
        "best_share": {m: float(np.mean(best == i)) for i, m in enumerate(CLASSICAL)},
        "dominant_is_best": float(np.mean(near_best)),
        "fixed_is_best": {m: float(np.mean(e[:, i] <= e.min(axis=1) + 1.0)) for i, m in enumerate(CLASSICAL)},
        "chance": float(np.mean([np.mean(e[:, i] <= e.min(axis=1) + 1.0) for i in range(3)])),
        "mae": {**{m: float(np.mean(e[:, i])) for i, m in enumerate(CLASSICAL)},
                "trace": float(np.mean(trace_err)), "oracle": float(np.mean(oracle))},
        "within5": {**{m: float(np.mean(e[:, i] <= 5)) for i, m in enumerate(CLASSICAL)},
                    "trace": float(np.mean(trace_err <= 5)), "oracle": float(np.mean(oracle <= 5))},
        "mean_weight": {m: float(np.mean(w[:, i])) for i, m in enumerate(CLASSICAL)},
    }


def main(tag: str) -> None:
    res = ROOT / "results"
    g = pd.read_csv(res / f"grid_{tag}.csv")
    g["group"] = np.where(g["fitzpatrick"] <= 3, "I-III", "IV-VI")
    cells = pd.read_csv(res / f"cells_{tag}.csv")
    fid = json.loads((res / f"harness_validation_{tag}.json").read_text()).get("pulse_fidelity", {})

    compression: dict = {}
    for codec in CODECS:
        compression[codec] = {}
        for rate in RATES:
            cn = cond_name(codec, rate)
            d = g[g["condition"] == cn]
            if d.empty:
                continue
            methods = {}
            for m in SHOWN:
                dm = d[d["method"] == m]
                if dm.empty:
                    continue
                c = cells[(cells["method"] == m) & (cells["condition"] == cn)]
                methods[m] = {
                    "mae": float(subject_mae(dm).mean()),
                    "within5": float(((dm["est_bpm"] - dm["ref_bpm"]).abs() <= 5).mean()),
                    "groups": {r["group"]: {"mae": float(r["mae"]), "lo": float(r["ci_low"]), "hi": float(r["ci_high"])}
                               for _, r in c.iterrows()},
                }
            tw = d[d["method"] == "trace"]
            weights = {
                "all": {m: float(tw[f"w_{m}"].mean()) for m in CLASSICAL},
                **{grp: {m: float(tw.loc[tw["group"] == grp, f"w_{m}"].mean()) for m in CLASSICAL}
                   for grp in ("I-III", "IV-VI")},
            }
            f = fid.get(cn)
            compression[codec][rate] = {
                "methods": methods, "weights": weights,
                "fidelity": {"II": f["II"], "VI": f["VI"]} if f else None,
                "selection": selection_stats(d),
            }

    held = res / f"fusion_ablation_{tag}.json"
    out = {
        "source": "simulated" if tag == "sim" else tag,
        "n_subjects": int(g["subject"].nunique()),
        "n_windows": int(len(g[g["method"] == "trace"])),
        "labels": LABELS, "rates": RATES, "codecs": list(CODECS),
        "compression": compression,
        "selection_all": selection_stats(g),
        "held_out": json.loads(held.read_text()) if held.exists() else None,
        "params": json.loads((res / "fusion_params.json").read_text()),
    }
    dest = ROOT / "app" / "static" / "lab" / "results.json"
    dest.write_text(json.dumps(out, indent=1))
    s = out["selection_all"]
    print(f"results.json: {out['n_subjects']} subjects, {s['windows']} windows")
    print("  MAE over every window: " + ", ".join(f"{k} {v:.2f}" for k, v in s["mae"].items()))
    print(f"  dominant weight on a best-or-tied method: {s['dominant_is_best']:.3f} (fixed-method average {s['chance']:.3f})")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--tag", default="sim")
    main(ap.parse_args().tag)
