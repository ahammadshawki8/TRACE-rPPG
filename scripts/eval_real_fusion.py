"""Score every method and both TRACE versions on real recordings with a contact reference.

    set TRACE_UBFC_DIR=D:/datasets/ubfc
    .venv/Scripts/python.exe scripts/eval_real_fusion.py [--dataset PATH] [--tag ubfc]

UBFC-rPPG's reference is a contact pulse oximeter (CMS50E) recorded in sync
with the video, so every 20 s window has a true heart rate. Each subject's
skin-colour trace is extracted once and cached (data/cache/real/), then
green, CHROM, POS, TRACE v2 (frozen) and TRACE v3 (results/fusion_params_v3.json)
are read out every 2.5 s exactly as the live app would. Output:
results/real_fusion_<tag>.json and a table on screen.
"""

from __future__ import annotations

import argparse
import json

import numpy as np
from pathlib import Path

from _common import ROOT, UBFC_DIR
from tracerppg.datasets import load_dataset, reference_hr, resample_uniform
from tracerppg.fusion import artifact_reference, band_limited_pulses, fuse, harmonic_continuity
from tracerppg.roi import Traces, extract_traces

FS, WIN, HOP = 30.0, 20.0, 2.5
METHODS = ("green", "chrom", "pos")


def traces_for(rec, cache_dir) -> Traces:
    p = cache_dir / f"{rec.subject}.npz"
    if p.exists():
        return Traces.load(p)
    print(f"  extracting {rec.subject} (first run only)")
    tr = extract_traces(rec.video_path)
    tr.save(p)
    return tr


def evaluate(rec, tr: Traces, v2: dict, v3: dict) -> list[dict]:
    ok = tr.n_pixels > 200
    t, rgb = tr.t[ok], tr.rgb[ok]
    ends = np.arange(WIN, min(rec.duration_s, t[-1]) + 1e-9, HOP)
    refs = reference_hr(rec, [(e - WIN, e) for e in ends])
    rows, prev = [], None
    for te, ref in zip(ends, refs):
        m = (t > te - WIN) & (t <= te)
        if m.sum() < FS * WIN * 0.8:
            continue
        cols = np.column_stack([resample_uniform(t[m], rgb[m, c], FS)[1] for c in range(3)])
        pulses, art = band_limited_pulses(cols, FS), artifact_reference(cols, FS)
        f2 = fuse(pulses, FS, v2["gamma"], v2["confidence"], artifact=art, mask_k=v2["mask_k"])
        f3 = fuse(pulses, FS, v3["gamma"], v3["confidence"], artifact=art, mask_k=v3["mask_k"])
        b3 = f3.bpm
        if v3.get("continuity_rho") is not None:
            b3, _ = harmonic_continuity(prev, f3, v3["continuity_rho"])
        prev = b3
        rows.append({"t": float(te), "ref": float(ref), "v2": f2.bpm, "v2_conf": bool(f2.confident),
                     "v3": b3, "v3_conf": bool(f3.quality >= v3["confidence"]),
                     **{k: f2.per_method[k].bpm for k in METHODS},
                     **{f"w_{k}": f3.weights[k] for k in METHODS}})
    return rows


def summary(rows: list[dict]) -> dict:
    out = {"n": len(rows)}
    for k in (*METHODS, "v2", "v3"):
        e = np.array([abs(r[k] - r["ref"]) for r in rows])
        out[k] = {"mae": float(e.mean()), "within5": float((e <= 5).mean())}
    for v in ("v2", "v3"):
        c = np.array([r[f"{v}_conf"] for r in rows])
        e = np.array([abs(r[v] - r["ref"]) for r in rows])
        out[f"{v}_confident"] = {"share": float(c.mean()), "mae": float(e[c].mean()) if c.any() else None}
        out[f"{v}_flagged_mae"] = float(e[~c].mean()) if (~c).any() else None
    out["mean_weights_v3"] = {k: float(np.mean([r[f"w_{k}"] for r in rows])) for k in METHODS}
    return out


def main(root, tag: str) -> None:
    v2 = json.loads((ROOT / "results" / "fusion_params.json").read_text())
    p3 = ROOT / "results" / "fusion_params_v3.json"
    v3 = json.loads(p3.read_text()) if p3.exists() else {**v2, "continuity_rho": None}
    recs = load_dataset(root)
    # A subject still downloading has its ground truth but no finished video
    # yet; skip it now and it is picked up (and cached) on the next run.
    waiting = [r.subject for r in recs if not r.video_path.exists()]
    if waiting:
        print(f"  skipping (video not finished): {', '.join(waiting)}")
    recs = [r for r in recs if r.video_path.exists()]
    if not recs:
        raise SystemExit(f"No recordings found under {root}")
    # Keyed by the dataset folder too: two datasets can both have a "subject1".
    import hashlib
    cache = ROOT / "data" / "cache" / "real" / hashlib.sha1(str(Path(root).resolve()).encode()).hexdigest()[:10]
    cache.mkdir(parents=True, exist_ok=True)
    per, allrows = {}, []
    for rec in recs:
        rows = evaluate(rec, traces_for(rec, cache), v2, v3)
        per[rec.subject] = summary(rows)
        allrows += rows
        s = per[rec.subject]
        print(f"  {rec.subject:10s} " + " ".join(f"{k} {s[k]['mae']:5.1f}" for k in (*METHODS, "v2", "v3")))
    tot = summary(allrows)
    print(f"\n  {len(recs)} subjects, {tot['n']} windows. MAE / within 5 BPM against the contact oximeter:")
    for k in (*METHODS, "v2", "v3"):
        print(f"    {k:6s} {tot[k]['mae']:6.2f}  {tot[k]['within5']:.0%}")
    for v in ("v2", "v3"):
        c = tot[f"{v}_confident"]
        print(f"    {v} confident on {c['share']:.0%}: MAE {c['mae']}")
    (ROOT / "results" / f"real_fusion_{tag}.json").write_text(json.dumps({"overall": tot, "subjects": per}, indent=1))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", default=str(UBFC_DIR))
    ap.add_argument("--tag", default="ubfc")
    a = ap.parse_args()
    from pathlib import Path
    main(Path(a.dataset), a.tag)
