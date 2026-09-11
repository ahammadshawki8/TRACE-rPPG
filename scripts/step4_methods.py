"""T3 acceptance: green, ICA, CHROM and POS.

Theory first: after temporal normalisation a pure brightness change is the
vector (1, 1, 1) in RGB, and both CHROM and POS map it to zero exactly. Then
behaviour: with a brightness artifact four times the pulse, the projections
recover the rate and the green channel does not. Finally a simulated cohort
across all six Fitzpatrick types, reported per method and skin-tone group.

Run:  .venv/Scripts/python.exe scripts/step4_methods.py
"""

from __future__ import annotations

from concurrent.futures import ProcessPoolExecutor

import numpy as np

from _common import ROOT, check, cohort, finish, rule, sim_traces
from tracerppg.datasets import load_dataset, reference_hr, sliding_windows, windowed_bpm
from tracerppg.methods import METHODS, POS_PROJECTION, chrom, green, ica, pos
from tracerppg.metrics import summary
from tracerppg.roi import extract_traces
from tracerppg.spectral import estimate_bpm
from tracerppg.preprocess import clean_pulse
from tracerppg.simulate import PULSE_DIRECTION
from tracerppg.synth import pulse_wave

FS = 30.0


def evaluate(cfg):
    rec, tr = sim_traces(cfg)
    ws = sliding_windows(rec.duration_s)
    ref = reference_hr(rec, ws)
    out = {"fz": cfg.fitzpatrick, "ref": ref}
    for name, fn in METHODS.items():
        out[name] = windowed_bpm(tr.t, fn(tr.rgb, tr.fps), tr.fps, ws)[0]
    return out


if __name__ == "__main__":
    t = np.arange(int(30 * FS)) / FS
    rng = np.random.default_rng(5)
    k = 5
    art = np.convolve(rng.normal(size=len(t) + k), np.ones(k) / k, "valid")[: len(t)]
    art = 0.02 * art / np.std(art)  # broadband brightness change, 2 percent RMS
    skin = np.array([180.0, 140.0, 110.0])

    # -----------------------------------------------------------------------
    rule("1. The projections cancel a pure brightness change exactly")
    bright = skin[None, :] * (1.0 + art[:, None])
    print(f"  POS projection of (1,1,1): {POS_PROJECTION @ np.ones(3)}")
    res = {n: float(np.std(f(bright, FS))) for n, f in (("green", green), ("chrom", chrom), ("pos", pos))}
    print(f"  output RMS for a 2 percent brightness flicker: green {res['green']:.2e}, "
          f"CHROM {res['chrom']:.2e}, POS {res['pos']:.2e}")
    check("POS output is zero for pure brightness change", res["pos"] < 1e-9 * res["green"],
          f"{res['pos']:.1e} vs green {res['green']:.1e}")
    check("CHROM output is zero for pure brightness change", res["chrom"] < 1e-9 * res["green"],
          f"{res['chrom']:.1e}")

    # -----------------------------------------------------------------------
    rule("2. A pulse under a brightness artifact four times its size")
    pulse = pulse_wave(t, 72.0)
    pulse = pulse / np.ptp(pulse) * 0.005  # 0.5 percent peak to peak in green
    colour = skin[None, :] * (1.0 + np.outer(pulse, PULSE_DIRECTION / PULSE_DIRECTION[1]))
    traces = colour * (1.0 + 4 * art[:, None] / 2)
    for name, fn in (("green", green), ("ica", ica), ("chrom", chrom), ("pos", pos)):
        e = estimate_bpm(clean_pulse(fn(traces, FS), FS), FS)
        print(f"  {name:6s} {e.bpm:7.2f} BPM   quality {e.quality:.3f}")
        if name in ("chrom", "pos"):
            check(f"{name.upper()} recovers 72 BPM through the artifact", abs(e.bpm - 72.0) < 2.0,
                  f"{e.bpm:.2f} BPM")
        if name == "green":
            check("green is misled by the artifact (the reason projections exist)",
                  abs(e.bpm - 72.0) > 2.0 or e.quality < 0.3, f"{e.bpm:.2f} BPM, quality {e.quality:.2f}")

    # -----------------------------------------------------------------------
    rule("3. ICA is deterministic")
    a1, a2 = ica(traces, FS), ica(traces, FS)
    check("same input, same output", np.allclose(a1, a2))

    # -----------------------------------------------------------------------
    rule("4. Simulated cohort, uncompressed: 6 types x 4 subjects x 40 s")
    cfgs = cohort(n_per_type=4, duration_s=40.0)
    with ProcessPoolExecutor(max_workers=12) as ex:
        rows = list(ex.map(evaluate, cfgs))
    groups = {"I to III": [r for r in rows if r["fz"] <= 3], "IV to VI": [r for r in rows if r["fz"] >= 4]}
    table = {}
    print("  method   group      MAE    RMSE     r     within 5")
    for name in METHODS:
        for g, rs in groups.items():
            s = summary(np.concatenate([r[name] for r in rs]), np.concatenate([r["ref"] for r in rs]))
            table[(name, g)] = s
            print(f"  {name:7s}  {g:9s} {s['mae']:6.2f}  {s['rmse']:6.2f}  {s['r']:5.2f}   {s['within5']:6.1%}")
    light = {n: table[(n, "I to III")]["mae"] for n in METHODS}
    check("CHROM and POS beat green on types I to III (the published ordering)",
          light["chrom"] < light["green"] and light["pos"] < light["green"],
          f"green {light['green']:.2f}, CHROM {light['chrom']:.2f}, POS {light['pos']:.2f}")
    for n in ("chrom", "pos"):
        gap = table[(n, "IV to VI")]["mae"] - table[(n, "I to III")]["mae"]
        print(f"  {n.upper()} skin-tone gap before any compression: {gap:+.2f} BPM (simulated)")

    # -----------------------------------------------------------------------
    rule("5. Real UBFC-rPPG (only if downloaded to data/ubfc/)")
    ubfc = ROOT / "data" / "ubfc"
    if ubfc.exists() and any(ubfc.iterdir()):
        est = {n: [] for n in METHODS}
        refs = []
        for rec in load_dataset(ubfc):
            tr = extract_traces(rec.video_path)
            ws = sliding_windows(min(rec.duration_s, tr.t[-1]))
            refs.append(reference_hr(rec, ws))
            for n, fn in METHODS.items():
                est[n].append(windowed_bpm(tr.t, fn(tr.rgb, tr.fps), tr.fps, ws)[0])
        for n in METHODS:
            s = summary(np.concatenate(est[n]), np.concatenate(refs))
            print(f"  UBFC {n:6s} MAE {s['mae']:6.2f}  RMSE {s['rmse']:6.2f}  r {s['r']:.2f}")
    else:
        print("  SKIPPED: data/ubfc/ not present.")

    finish()
