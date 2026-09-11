"""T4 acceptance: TRACE fusion, tuned on one cohort and tested on another.

1. Mechanics: weights sum to one; gamma = 0 averages; gamma = inf picks.
2. When one method is noise and another is clean, fusion follows the clean one.
3. When an artifact switches on halfway, the green weight falls in that half.
4. Tuning on seeds 1000+ and 2000+ (48 subjects): v1 gamma; v2 gamma and
   mask strength k on a coarse grid; the v2 confidence threshold where a
   logistic fit says a reading becomes more likely wrong than right. All
   frozen to results/fusion_params.json before any test data is touched.
5. Test on a cohort never used for anything (seeds 5000+): the full
   ablation, whatever it shows, and the sensitivity to the nominal pulse
   direction (reported as a property of the method, not asserted).

History kept on purpose (all simulated):
  a. TRACE v1 tuned on seeds 1000+, tested on 2000+: lost to POS
     (15.86 vs 10.24 BPM).
  b. TRACE v2 designed and tuned on seeds 1000+ only (24 subjects, tuning
     MAE 4.64), tested on 4000+: 13.37 vs POS 13.27 and ICA 11.84. It had
     overfit a two-parameter grid on 96 windows, and its confidence rule
     degenerated (kept 100 percent of windows).
  c. This version: more tuning data, a coarser grid, a logistic confidence
     rule, and a fresh test cohort. The full grid (seeds 3000+) is a second,
     larger held-out test.

All cohort numbers are simulated.

Run:  .venv/Scripts/python.exe scripts/step5_fusion.py
"""

from __future__ import annotations

import json
from concurrent.futures import ProcessPoolExecutor

import numpy as np

from _common import ROOT, WORKERS, check, cohort, finish, rule, sim_traces
from tracerppg.datasets import reference_hr, sliding_windows, window_slice
from tracerppg.fusion import artifact_reference, band_limited_pulses, fuse, weights_from_quality
from tracerppg.metrics import summary
from tracerppg.preprocess import clean_pulse
from tracerppg.spectral import (HR_BAND, band_mask, correct_harmonic_lock, estimate_bpm, peak_frequency,
                                spectrum)
from tracerppg.synth import pulse_wave

FS = 30.0
SIM_PBV = (0.33, 0.77, 0.53)  # the simulator's own generating direction, for the sensitivity check
FUSED = ("green", "chrom", "pos")


def subject_windows(cfg):
    """Per-window reference, method pulses, and both artifact references."""
    rec, tr = sim_traces(cfg)
    ws = sliding_windows(rec.duration_s)
    ref = reference_hr(rec, ws)
    pulses = band_limited_pulses(tr.rgb, tr.fps, names=("green", "ica", "chrom", "pos"))
    art = artifact_reference(tr.rgb, tr.fps)
    art_sim = artifact_reference(tr.rgb, tr.fps, pbv=SIM_PBV)
    segs = []
    for a, b in ws:
        sl = window_slice(tr.t, a, b)
        segs.append({**{n: p[sl] for n, p in pulses.items()}, "_art": art[sl], "_art_sim": art_sim[sl]})
    return {"fz": cfg.fitzpatrick, "ref": ref, "segs": segs, "fs": tr.fps}


def run(subjects, kind, gamma=2.0, k=4.0, conf=0.0, art_key="_art"):
    est, qual, ref, grp = [], [], [], []
    for s in subjects:
        for seg, r in zip(s["segs"], s["ref"]):
            if kind in ("green", "ica", "chrom", "pos"):
                e, q = estimate_bpm(seg[kind], s["fs"]), None
                est.append(e.bpm)
                qual.append(e.quality)
            elif kind.startswith("masked_"):
                # One method with the artifact mask but no fusion: separates
                # what the mask buys from what fusion buys.
                name = kind.split("_", 1)[1]
                f, pa = spectrum(seg[art_key], s["fs"], pad_factor=4)
                m = band_mask(f, HR_BAND)
                keep = (1 - np.clip(pa / pa[m].max(), 0, 1)) ** k
                _, p = spectrum(seg[name], s["fs"], pad_factor=4)
                pk = peak_frequency(f, p * keep)
                pk, _ = correct_harmonic_lock(f, p * keep, pk)
                est.append(pk * 60)
                qual.append(0.0)
            else:
                art = seg[art_key] if kind == "v2" else None
                fr = fuse({n: seg[n] for n in FUSED}, s["fs"], gamma, conf, artifact=art, mask_k=k)
                est.append(fr.bpm)
                qual.append(fr.quality)
            ref.append(r)
            grp.append(s["fz"])
    return np.array(est), np.array(qual), np.array(ref), np.array(grp)


def mae_of(res):
    e, _, r, _ = res
    return float(np.mean(np.abs(e - r)))


if __name__ == "__main__":
    t = np.arange(int(20 * FS)) / FS
    rng = np.random.default_rng(9)

    # -----------------------------------------------------------------------
    rule("1. Weighting mechanics")
    q = {"green": 0.2, "chrom": 0.5, "pos": 0.8}
    w0, w2, wi = (weights_from_quality(q, g) for g in (0.0, 2.0, float("inf")))
    check("weights sum to one", all(abs(sum(w.values()) - 1) < 1e-12 for w in (w0, w2, wi)))
    check("gamma 0 is an equal average", all(abs(v - 1 / 3) < 1e-12 for v in w0.values()))
    check("gamma inf selects the best-scoring method", wi == {"green": 0.0, "chrom": 0.0, "pos": 1.0})

    # -----------------------------------------------------------------------
    rule("2. Fusion follows the clean method")
    clean = clean_pulse(pulse_wave(t, 66.0) + 0.3 * rng.normal(size=len(t)), FS)
    noise = clean_pulse(rng.normal(size=len(t)), FS)
    fr = fuse({"green": noise, "chrom": noise * 0.7 + 0.01, "pos": clean}, FS)
    check("fused rate is the clean method's rate", abs(fr.bpm - 66.0) < 1.5, f"{fr.bpm:.2f} BPM")
    check("the clean method carries most of the weight", fr.weights["pos"] > 0.6, f"{fr.weights['pos']:.2f}")

    # -----------------------------------------------------------------------
    rule("3. Weights move when conditions change")
    n = len(t)
    art = np.zeros(n)
    art[n // 2:] = 3.0 * rng.normal(size=n - n // 2)
    base = pulse_wave(t, 80.0)
    green_like = clean_pulse(base + art + 0.3 * rng.normal(size=n), FS)
    pos_like = clean_pulse(base + 0.3 * rng.normal(size=n), FS)
    half = n // 2
    w_first = fuse({"green": green_like[:half], "pos": pos_like[:half]}, FS).weights["green"]
    w_second = fuse({"green": green_like[half:], "pos": pos_like[half:]}, FS).weights["green"]
    check("green's weight falls once motion corrupts it", w_second < 0.5 * w_first,
          f"{w_first:.2f} in the calm half, {w_second:.2f} in the corrupted half")

    # -----------------------------------------------------------------------
    rule("4. Tune on seeds 1000+ and 2000+ (48 subjects), then freeze")
    with ProcessPoolExecutor(max_workers=WORKERS) as ex:
        tune = list(ex.map(subject_windows, cohort(n_per_type=4, duration_s=40.0, seed0=1000)
                           + cohort(n_per_type=4, duration_s=40.0, seed0=2000)))
    v1 = {g: mae_of(run(tune, "v1", g)) for g in (0.0, 1.0, 2.0, 4.0, 8.0, float("inf"))}
    g1 = min(v1, key=v1.get)
    print("  v1 gamma: " + "  ".join(f"{g}: {m:.2f}" for g, m in v1.items()) + f"  -> {g1}")
    ks, gs = (2.0, 4.0, 8.0), (1.0, 2.0, 4.0)
    v2 = {(g, k): mae_of(run(tune, "v2", g, k)) for g in gs for k in ks}
    g2, k2 = min(v2, key=v2.get)
    print("  v2 tuning MAE (rows gamma, columns mask k):")
    print("        " + "  ".join(f"k={k:<4}" for k in ks))
    for g in gs:
        print(f"  g={g:<4} " + "  ".join(f"{v2[(g, k)]:6.2f}" for k in ks))
    e, qv, r, _ = run(tune, "v2", g2, k2)
    correct = (np.abs(e - r) <= 5.0).astype(float)
    # Confidence threshold: where a logistic fit of P(correct | quality)
    # crosses one half, i.e. below it a reading is more likely wrong than right.
    import statsmodels.api as sm
    fit = sm.Logit(correct, sm.add_constant(qv)).fit(disp=0)
    b0, b1 = fit.params
    thr = float(np.clip(-b0 / b1, 0.0, 1.0)) if b1 > 0 else 0.0
    print(f"  logistic P(correct) = 1 / (1 + exp(-({b0:.2f} + {b1:.2f} q)))  ->  threshold q = {thr:.3f}")
    print(f"  frozen v2: gamma {g2}, mask k {k2}, confidence {thr:.3f} "
          f"(tuning MAE {v2[(g2, k2)]:.2f}, keeps {np.mean(qv >= thr):.0%} of tuning windows)")
    params = {"version": 2, "gamma": g2, "mask_k": k2, "confidence": thr, "pbv_nominal": [0.27, 0.80, 0.54],
              "v1_gamma": g1, "tuned_on": "simulated cohorts seeds 1000+ and 2000+ (48 subjects x 40 s)",
              "tuning_mae_v2": v2[(g2, k2)], "tuning_mae_v1": v1[g1], "logistic": [float(b0), float(b1)]}
    (ROOT / "results").mkdir(exist_ok=True)
    (ROOT / "results" / "fusion_params.json").write_text(json.dumps(params, indent=2))

    # -----------------------------------------------------------------------
    rule("5. Test on a never-used cohort (seeds 5000+)")
    with ProcessPoolExecutor(max_workers=WORKERS) as ex:
        test = list(ex.map(subject_windows, cohort(n_per_type=4, duration_s=40.0, seed0=5000)))
    rows = {
        "green": run(test, "green"), "ica": run(test, "ica"), "chrom": run(test, "chrom"), "pos": run(test, "pos"),
        "POS + artifact mask (no fusion)": run(test, "masked_pos", k=k2),
        f"TRACE v1 (gamma {g1})": run(test, "v1", g1),
        "TRACE v2 equal weights": run(test, "v2", 0.0, k2),
        f"TRACE v2 (gamma {g2}, k {k2})": run(test, "v2", g2, k2, thr),
        "TRACE v2, simulator's own PBV": run(test, "v2", g2, k2, thr, art_key="_art_sim"),
    }
    print("  method                            MAE all  I-III  IV-VI   RMSE    r    within 5")
    maes = {}
    for label, (e, _, r, gp) in rows.items():
        s = summary(e, r)
        lo, hi = gp <= 3, gp >= 4
        maes[label] = s["mae"]
        print(f"  {label:33s} {s['mae']:6.2f} {np.mean(np.abs(e[lo] - r[lo])):6.2f} "
              f"{np.mean(np.abs(e[hi] - r[hi])):6.2f}  {s['rmse']:6.2f}  {s['r']:5.2f}  {s['within5']:6.1%}")
    tl = f"TRACE v2 (gamma {g2}, k {k2})"
    best_single = min(("green", "chrom", "pos", "ica"), key=lambda n: maes[n])
    verdict = "beats" if maes[tl] < maes[best_single] else "does not beat"
    print(f"  TRACE v2 {verdict} the best single method ({best_single}, {maes[best_single]:.2f}) on unseen data")
    check("ablation table produced on a cohort never used for tuning or design", True,
          f"TRACE v2 {maes[tl]:.2f} vs best single {best_single} {maes[best_single]:.2f} BPM")
    sim_key = "TRACE v2, simulator's own PBV"
    print(f"  sensitivity to the nominal pulse direction (reported, not asserted): "
          f"{maes[tl]:.2f} with the literature-style vector vs {maes[sim_key]:.2f} with the simulator's own")

    e, qv_t, r, _ = rows[tl]
    conf = qv_t >= thr
    mae_c = float(np.mean(np.abs(e[conf] - r[conf]))) if conf.any() else float("nan")
    mae_u = float(np.mean(np.abs(e[~conf] - r[~conf]))) if (~conf).any() else float("nan")
    check("the confidence gate separates good windows from bad ones on unseen data",
          conf.any() and (~conf).any() and mae_c < mae_u,
          f"confident {mae_c:.2f} BPM on {conf.mean():.0%} of windows vs flagged {mae_u:.2f} BPM")

    out = {k: float(v) for k, v in maes.items()}
    out.update({"confident_mae": mae_c, "flagged_mae": mae_u, "coverage": float(conf.mean()),
                "history": {"v1_tuned1000_tested2000": {"trace_v1": 15.86, "pos": 10.24},
                            "v2_tuned1000_tested4000": {"trace_v2": 13.37, "pos": 13.27, "ica": 11.84}}})
    (ROOT / "results" / "fusion_ablation_sim.json").write_text(json.dumps(out, indent=2))
    finish()
