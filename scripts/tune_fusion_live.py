"""Choose TRACE v3 on one simulated cohort, then test it once on another.

    .venv/Scripts/python.exe scripts/tune_fusion_live.py            (tune on scen_tune, test on scen_test)

The scenario sweep (Section 2.1c of CLAUDE.md) found that TRACE v2 trusts the
right method (POS, 9 of 10 conditions) but its weighted sum still lets two
fooled methods outvote it, and about 10 percent of read-outs sit at double or
half the true rate. Two classical changes are tried:

    gamma      weight exponent: 1 (v2), 2, 4, 8, or inf (winner takes all)
    rho        harmonic continuity (fusion.harmonic_continuity): off, or the
               fraction of peak power that must remain near the previous rate

Every combination is scored on the tuning traces (results/raw/scen_tune,
seeds 8000+). The best by mean absolute error is frozen, its confidence
threshold refitted there (P(within 5 BPM | quality) = 0.5, as step5 did),
and only then scored once on the test traces (seeds 9000+), next to v2.
Writes results/fusion_params_v3.json and results/fusion_v3_test.json.
"""

from __future__ import annotations

import json
from concurrent.futures import ProcessPoolExecutor

import numpy as np

from _common import ROOT
from tracerppg.datasets import resample_uniform
from tracerppg.fusion import artifact_reference, band_limited_pulses, fuse, harmonic_continuity

FS, WIN, HOP = 30.0, 20.0, 2.5
GAMMAS = [1.0, 2.0, 4.0, 8.0, float("inf")]
RHOS = [None, 0.1, 0.2, 0.3, 0.5]
V2 = json.loads((ROOT / "results" / "fusion_params.json").read_text())


def run_file(path: str) -> list[dict]:
    """Every read-out of one saved run, for every gamma, before continuity."""
    z = np.load(path)
    t, rgb, truth = z["t"], z["rgb"], z["truth"]
    scen, fz = str(z["scenario"]), int(z["fitzpatrick"])
    z.close()
    out = []
    for i, te in enumerate(np.arange(WIN, WIN + HOP * len(truth) - 1e-9, HOP)):
        m = (t > te - WIN) & (t <= te)
        if m.sum() < FS * WIN * 0.8 or not np.isfinite(truth[i]):
            continue
        cols = np.column_stack([resample_uniform(t[m], rgb[m, c], FS)[1] for c in range(3)])
        pulses, art = band_limited_pulses(cols, FS), artifact_reference(cols, FS)
        for g in GAMMAS:
            fr = fuse(pulses, FS, g, V2["confidence"], artifact=art, mask_k=V2["mask_k"])
            out.append({"run": path, "scenario": scen, "fz": fz, "i": i, "gamma": g, "truth": float(truth[i]),
                        "fr": fr})
    return out


def score(rows_by_run: dict, gamma: float, rho: float | None) -> list[dict]:
    """Apply continuity in time order within each run; one row per read-out."""
    res = []
    for run, rows in rows_by_run.items():
        prev = None
        for r in sorted((x for x in rows if x["gamma"] == gamma), key=lambda x: x["i"]):
            bpm, fixed = (harmonic_continuity(prev, r["fr"], rho) if rho is not None else (r["fr"].bpm, False))
            prev = bpm
            res.append({"scenario": r["scenario"], "fz": r["fz"], "truth": r["truth"], "bpm": bpm, "fixed": fixed,
                        "quality": r["fr"].quality})
    return res


def metrics(res: list[dict], thr: float | None = None) -> dict:
    e = np.array([abs(r["bpm"] - r["truth"]) for r in res])
    ratio = np.array([r["bpm"] / r["truth"] for r in res])
    out = {"n": len(res), "mae": float(e.mean()), "within5": float((e <= 5).mean()),
           "harmonic": float(((np.abs(ratio - 2) < 0.12) | (np.abs(ratio - 0.5) < 0.06)).mean())}
    if thr is not None:
        c = np.array([r["quality"] >= thr for r in res])
        out.update({"confident": float(c.mean()), "mae_confident": float(e[c].mean()) if c.any() else None,
                    "within5_confident": float((e[c] <= 5).mean()) if c.any() else None,
                    "mae_flagged": float(e[~c].mean()) if (~c).any() else None})
    return out


def fit_threshold(res: list[dict]) -> tuple[float, list[float]]:
    """Logistic P(within 5 | quality) by Newton's method; threshold at 0.5."""
    q = np.array([r["quality"] for r in res])
    y = np.array([abs(r["bpm"] - r["truth"]) <= 5 for r in res], dtype=float)
    X = np.column_stack([np.ones_like(q), q])
    b = np.zeros(2)
    for _ in range(50):
        p = 1 / (1 + np.exp(-X @ b))
        W = p * (1 - p) + 1e-9
        b += np.linalg.solve(X.T @ (X * W[:, None]), X.T @ (y - p))
    return float(-b[0] / b[1]), [float(b[0]), float(b[1])]


def load(tag: str) -> dict:
    files = sorted(str(p) for p in (ROOT / "results" / "raw" / f"scen_{tag}").glob("*.npz"))
    with ProcessPoolExecutor(max_workers=4) as ex:
        chunks = list(ex.map(run_file, files, chunksize=4))
    by_run: dict = {}
    for rows in chunks:
        for r in rows:
            by_run.setdefault(r["run"], []).append(r)
    print(f"  {tag}: {len(files)} runs, {sum(len(v) for v in by_run.values()) // len(GAMMAS)} read-outs")
    return by_run


def by_scenario(res: list[dict], thr: float) -> dict:
    return {s: metrics([r for r in res if r["scenario"] == s], thr) for s in sorted({r["scenario"] for r in res})}


def main() -> None:
    print("tuning set")
    tune = load("tune")
    grid = []
    for g in GAMMAS:
        for rho in RHOS:
            m = metrics(score(tune, g, rho))
            grid.append({"gamma": g, "rho": rho, **m})
            print(f"  gamma {g:>4}  rho {str(rho):>4}  MAE {m['mae']:6.2f}  within5 {m['within5']:.1%}  harmonic {m['harmonic']:.1%}")
    best = min(grid, key=lambda x: x["mae"])
    g, rho = best["gamma"], best["rho"]
    tune_best = score(tune, g, rho)
    thr, logistic = fit_threshold(tune_best)
    print(f"\n  chosen on tuning set: gamma {g}, rho {rho}; confidence threshold refitted {thr:.3f}")

    print("\ntest set (used once)")
    test = load("test")
    v2 = score(test, 1.0, None)
    v3 = score(test, g, rho)
    m2, m3 = metrics(v2, V2["confidence"]), metrics(v3, thr)
    for name, m in (("v2 (frozen)", m2), ("v3", m3)):
        print(f"  {name:12s} MAE {m['mae']:6.2f}  within5 {m['within5']:.1%}  harmonic {m['harmonic']:.1%}  "
              f"confident {m['confident']:.0%} -> MAE {m['mae_confident']:.2f}, flagged {m['mae_flagged']:.2f}")
    s2, s3 = by_scenario(v2, V2["confidence"]), by_scenario(v3, thr)
    print("\n  per condition, test MAE v2 -> v3")
    for s in s2:
        print(f"    {s:10s} {s2[s]['mae']:6.2f} -> {s3[s]['mae']:6.2f}")

    params = {"version": 3, "gamma": g, "mask_k": V2["mask_k"], "confidence": thr, "logistic": logistic,
              "continuity_rho": rho, "pbv_nominal": V2.get("pbv_nominal"),
              "tuned_on": "live-simulator scenario sweep, seeds 8000+ (10 conditions x 6 skin types x 2 volunteers x 60 s)",
              "tested_on": "seeds 9000+ (x 3 volunteers), scored once", "v2": {k: V2[k] for k in ("gamma", "mask_k", "confidence")}}
    (ROOT / "results" / "fusion_params_v3.json").write_text(json.dumps(params, indent=1))
    (ROOT / "results" / "fusion_v3_test.json").write_text(json.dumps(
        {"grid_tuning": grid, "test": {"v2": m2, "v3": m3, "v2_by_scenario": s2, "v3_by_scenario": s3}}, indent=1,
        default=lambda x: None if x is None else float(x)))
    print("\nwrote results/fusion_params_v3.json and results/fusion_v3_test.json")


if __name__ == "__main__":
    main()
