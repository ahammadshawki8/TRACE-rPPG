"""Tune TRACE v4 on UBFC-rPPG and the simulated tuning cohort; never on volunteers.

    .venv/Scripts/python.exe scripts/tune_fusion_v4.py --ubfc D:/datasets/ubfc

v4 keeps v3 (per-window selection, artifact mask k 4) and adds three options
found on real volunteers (CLAUDE.md 2.2): a band-edge penalty for a lone peak
near the bottom of the band, a prior that makes TRACE leave POS only when
another method is clearly sharper, and a longer window when quality is low.

Selection options change which method is trusted, not any method's spectrum,
so each window's per-method BPM, quality and artifact share are computed once
(20 s and 30 s windows) and every setting is scored from those numbers. The
setting with the lowest mean of UBFC and simulated MAE is frozen with a
confidence threshold refitted by logistic regression (P(within 5 BPM) = 0.5)
into results/fusion_params_v4.json. The volunteers are the untouched test set.
"""

from __future__ import annotations

import argparse
import hashlib
import itertools
import json
from pathlib import Path

import numpy as np

from _common import ROOT, UBFC_DIR
from tracerppg.datasets import load_dataset, reference_hr
from tracerppg.roi import Traces
from tracerppg.simeval import analyse, frozen_params

METHODS = ("green", "chrom", "pos")
LONG_S = 30.0


def window_numbers(t, rgb, e, base):
    """Per-method BPM, quality, artifact share for the 20 s and (if available) 30 s window ending at e."""
    out = {}
    for w in (20.0, LONG_S):
        if w > 20.0 and e - w < t[0] - 0.05:
            out[w] = None
            continue
        a = analyse(t, rgb, e, {**base, "long_quality": 0.0}, win=w)
        out[w] = None if a is None else np.array([[a["methods"][m]["bpm"], a["methods"][m]["quality"],
                                                    a["methods"][m]["artifact"] or 0.0] for m in METHODS])
    return out


def select(nums: np.ndarray, prior_pos: float, edge_bpm: float, edge_pen: float) -> tuple[float, float]:
    """(BPM, fused quality) of the method v4 would select, from one window's numbers."""
    bpm, q, art = nums[:, 0], nums[:, 1], nums[:, 2]
    s = q * np.array([1.0, 1.0, prior_pos])
    for i in range(3):
        if edge_bpm and bpm[i] < edge_bpm and not any(abs(bpm[i] - bpm[j]) <= 5 for j in range(3) if j != i):
            s[i] *= edge_pen
    k = int(np.argmax(s))
    return bpm[k], q[k] / max((1.0 - art[k]) ** 2, 1e-9)  # fused quality = unpenalised SNR of the chosen spectrum


def readout(win_nums, setting):
    prior_pos, edge_bpm, edge_pen, long_q = setting
    b, fq = select(win_nums[20.0], prior_pos, edge_bpm, edge_pen)
    if long_q and fq < long_q and win_nums.get(LONG_S) is not None:
        b2, fq2 = select(win_nums[LONG_S], prior_pos, edge_bpm, edge_pen)
        if fq2 > fq:
            return b2, fq2
    return b, fq


def main(ubfc_root: Path) -> None:
    base = frozen_params(3)
    data = {"ubfc": [], "sim": []}  # (window numbers, reference)
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
    print(f"tuning windows: UBFC {len(data['ubfc'])}, simulated {len(data['sim'])}")

    grid = list(itertools.product((1.0, 1.15, 1.3, 1.5, 2.0), (0.0, 50.0, 55.0), (0.0, 0.3), (0.0, 0.15, 0.25)))
    grid = [g for g in grid if not (g[1] == 0.0 and g[2] != 0.0)]  # the penalty only matters with an edge
    results = []
    for s in grid:
        mae = {k: float(np.mean([abs(readout(n, s)[0] - ref) for n, ref in v])) for k, v in data.items()}
        results.append((0.5 * (mae["ubfc"] + mae["sim"]), s, mae))
    results.sort(key=lambda r: r[0])
    v3 = next(r for r in results if r[1] == (1.0, 0.0, 0.0, 0.0))
    print(f"v3 (no options): UBFC {v3[2]['ubfc']:.2f}  sim {v3[2]['sim']:.2f}")
    print("best settings (prior POS, edge BPM, edge penalty, long-window quality):")
    for obj, s, mae in results[:8]:
        print(f"  {s}  UBFC {mae['ubfc']:.2f}  sim {mae['sim']:.2f}  mean {obj:.2f}")
    best = results[0][1]

    # confidence threshold: logistic P(within 5 BPM | fused quality) on the tuning windows
    q, ok = [], []
    for v in data.values():
        for n, ref in v:
            b, fq = readout(n, best)
            q.append(fq); ok.append(abs(b - ref) <= 5)
    q, ok = np.array(q), np.array(ok, float)
    w = np.zeros(2)
    X = np.column_stack([np.ones_like(q), q])
    for _ in range(200):  # Newton steps for a two-parameter logistic regression
        p = 1 / (1 + np.exp(-X @ w))
        g = X.T @ (ok - p)
        H = (X * (p * (1 - p))[:, None]).T @ X + 1e-6 * np.eye(2)
        w += np.linalg.solve(H, g)
    conf = float(-w[0] / w[1])
    params = {**base, "version": 4, "prior": {"green": 1.0, "chrom": 1.0, "pos": best[0]},
              "edge_bpm": best[1], "edge_penalty": best[2] if best[1] else 1.0,
              "long_quality": best[3], "long_window_s": LONG_S if best[3] else 0.0,
              "confidence": conf, "logistic": [float(w[0]), float(w[1])],
              "tuned_on": f"UBFC-rPPG ({len(data['ubfc'])} windows, 22 subjects, contact oximeter) + simulated tuning cohort "
                          f"(results/raw/scen_tune, {len(data['sim'])} windows); volunteers never used",
              "tuning": {"ubfc_mae": results[0][2]["ubfc"], "sim_mae": results[0][2]["sim"],
                         "v3_ubfc_mae": v3[2]["ubfc"], "v3_sim_mae": v3[2]["sim"]}}
    (ROOT / "results" / "fusion_params_v4.json").write_text(json.dumps(params, indent=1))
    print(f"frozen v4: {best}, confidence {conf:.3f} -> results/fusion_params_v4.json")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--ubfc", default=str(UBFC_DIR))
    main(Path(ap.parse_args().ubfc))
