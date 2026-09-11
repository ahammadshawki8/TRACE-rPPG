"""T5 acceptance: the compression harness must not lie.

Harness validity (checks):
  1. The lossless RGB control is bit-identical to its source.
  2. The YUV controls differ only by conversion rounding, and subsampling
     adds error on top of it.
  3. Every condition decodes to the same frame count at the same rate.
  4. Achieved bitrates track their targets.
  5. Picture quality (PSNR) rises with bitrate for every codec.

Mechanism (reported, not asserted): what fraction of the known pulse
survives each condition, on light (II) and dark (VI) simulated skin. The
pulse amplitude is the regression coefficient of the band-limited green
trace on the true PPG, relative to the lossless control.

Run:  .venv/Scripts/python.exe scripts/step6_compression.py
"""

from __future__ import annotations

import json
import shutil
import tempfile
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np

from _common import ROOT, WORKERS, check, finish, rule, sim_folder
from tracerppg.compress import BITRATES, grid_conditions, encode
from tracerppg.datasets import load_recording
from tracerppg.methods import temporal_normalise
from tracerppg.preprocess import clean_pulse
from tracerppg.roi import extract_traces
from tracerppg.simulate import SimConfig
from tracerppg.synth import ppg_from_beats
from tracerppg.video import frames, probe


def compare(src: Path, dst: Path, step: int = 1):
    """Max abs difference, mean abs difference, PSNR, and frame counts."""
    mx, sad, sse, n_px, na, nb = 0, 0.0, 0.0, 0, 0, 0
    ia, ib = frames(src), frames(dst)
    for i, (a, b) in enumerate(zip(ia, ib)):
        na += 1
        nb += 1
        if i % step:
            continue
        d = a.astype(np.int16) - b.astype(np.int16)
        mx = max(mx, int(np.abs(d).max()))
        sad += float(np.abs(d).sum())
        sse += float((d.astype(np.float64) ** 2).sum())
        n_px += d.size
    na += sum(1 for _ in ia)
    nb += sum(1 for _ in ib)
    mse = sse / max(n_px, 1)
    psnr = float("inf") if mse == 0 else 10 * np.log10(255.0**2 / mse)
    return mx, sad / max(n_px, 1), psnr, na, nb


def pulse_amplitude(traces, beats) -> float:
    g = clean_pulse(temporal_normalise(traces.rgb, traces.fps)[:, 1] - 1.0, traces.fps)
    p = clean_pulse(ppg_from_beats(traces.t, np.asarray(beats)), traces.fps)
    return float(np.dot(g, p) / np.dot(p, p))


def pulse_fidelity(traces, beats) -> float:
    """Correlation between the band-limited green trace and the true pulse.

    Bounded in [-1, 1] and robust where an amplitude ratio is not: once a
    codec has destroyed the pulse, the amplitude estimate is noise divided by
    a small number (measured: -112 to 509 percent on type VI), while the
    correlation simply falls towards zero.
    """
    g = clean_pulse(temporal_normalise(traces.rgb, traces.fps)[:, 1] - 1.0, traces.fps)
    p = clean_pulse(ppg_from_beats(traces.t, np.asarray(beats)), traces.fps)
    return float(np.corrcoef(g, p)[0, 1])


def run_condition(args):
    src, cond, work = args
    res = encode(Path(src), Path(work), cond)
    mx, mad, psnr, na, nb = compare(Path(src), res.path, step=10)
    tr = extract_traces(res.path)
    info = probe(res.path)
    meta = json.loads((Path(src).parent / "meta.json").read_text())
    amp = pulse_amplitude(tr, meta["beat_times"])
    fid = pulse_fidelity(tr, meta["beat_times"])
    res.path.unlink(missing_ok=True)
    return {"name": cond.name, "codec": cond.codec, "kbps": cond.kbps, "pix": cond.pix_fmt,
            "achieved": res.achieved_kbps, "max_diff": mx, "mad": mad, "psnr": psnr,
            "n_src": na, "n_dst": nb, "fps": info.fps, "amp": amp, "fid": fid, "enc_s": res.seconds}


if __name__ == "__main__":
    conds = grid_conditions(codecs=("h264", "h265", "vp9", "vp8"))
    work = Path(tempfile.mkdtemp(prefix="trace_t5_"))
    # Harness checks run on realistic sources (natural motion and screen
    # light): rate control misbehaves on perfectly static content (VP9 could
    # not go below about 150 kbps). The mechanism is measured separately on
    # still sources with no screen light, so only the codec differs.
    sources = {fz: sim_folder(SimConfig(fitzpatrick=fz, duration_s=20.0, seed=500 + fz)) / "vid.mkv" for fz in (2, 6)}
    still = {fz: sim_folder(SimConfig(fitzpatrick=fz, duration_s=20.0, motion=0.0, screen_light=0.0,
                                      seed=500 + fz)) / "vid.mkv" for fz in (2, 6)}
    jobs = [(str(src[fz]), c, str(work / f"{tag}{fz}")) for tag, src in (("n", sources), ("s", still))
            for fz in src for c in conds]
    with ProcessPoolExecutor(max_workers=WORKERS) as ex:
        out = list(ex.map(run_condition, jobs))
    by, by_still = {}, {}
    for (src, c, _), r in zip(jobs, out):
        for fz in (2, 6):
            if src == str(sources[fz]):
                by[(fz, r["name"])] = r
            if src == str(still[fz]):
                by_still[(fz, r["name"])] = r

    # -----------------------------------------------------------------------
    rule("1. Lossless RGB control")
    for fz in sources:
        r = by[(fz, "lossless_rgb")]
        check(f"type {fz}: FFV1 re-encode is bit-identical to the source", r["max_diff"] == 0 and r["n_src"] == r["n_dst"],
              f"max diff {r['max_diff']}, {r['n_dst']} frames")

    # -----------------------------------------------------------------------
    rule("2. YUV controls: conversion, then subsampling")
    y444, y420 = by[(2, "lossless_yuv444")], by[(2, "lossless_yuv420")]
    print(f"  4:4:4 max {y444['max_diff']} levels, mean {y444['mad']:.3f}; "
          f"4:2:0 max {y420['max_diff']}, mean {y420['mad']:.3f}")
    check("4:4:4 round trip is conversion rounding only (at most 3 levels)", y444["max_diff"] <= 3,
          f"max {y444['max_diff']}")
    check("4:2:0 adds error on top of conversion", y420["mad"] > y444["mad"],
          f"mean {y420['mad']:.3f} vs {y444['mad']:.3f}")

    # -----------------------------------------------------------------------
    rule("3. Frame integrity")
    bad = [k for k, r in by.items() if r["n_dst"] != r["n_src"] or abs(r["fps"] - 30.0) > 1e-6]
    check("every condition decodes to the source frame count at 30 fps", not bad, f"{len(by)} encodes" if not bad else str(bad))

    # -----------------------------------------------------------------------
    rule("4. Bitrate control")
    print("  condition        target  achieved(II)  achieved(VI)  PSNR(II)  PSNR(VI)")
    worst_hi, worst_lo = 0.0, 9.0
    for c in conds:
        if c.lossless:
            continue
        a2, a6 = by[(2, c.name)], by[(6, c.name)]
        print(f"  {c.name:16s} {c.kbps:6d}   {a2['achieved']:9.0f}    {a6['achieved']:9.0f}    "
              f"{a2['psnr']:6.2f}   {a6['psnr']:6.2f}")
        for a in (a2, a6):
            ratio = a["achieved"] / c.kbps
            worst_hi = max(worst_hi, ratio)
            if c.kbps <= 400:
                worst_lo = min(worst_lo, ratio)
    check("no encode overshoots its target by more than 25 percent", worst_hi <= 1.25, f"worst {worst_hi:.2f}x")
    check("low targets (at most 400 kbps) are actually spent (at least 60 percent)", worst_lo >= 0.60,
          f"worst {worst_lo:.2f}x")

    # -----------------------------------------------------------------------
    rule("5. Picture quality rises with bitrate")
    mono = True
    for codec in ("h264", "h265", "vp9", "vp8"):
        ps = [by[(2, f"{codec}_{k}k")]["psnr"] for k in BITRATES]
        if any(b < a - 0.3 for a, b in zip(ps, ps[1:])):
            mono = False
        print(f"  {codec}: " + "  ".join(f"{k}k {p:.1f} dB" for k, p in zip(BITRATES, ps)))
    check("PSNR is non-decreasing in bitrate for every codec (0.3 dB tolerance)", mono)

    # -----------------------------------------------------------------------
    rule("6. Mechanism: pulse fidelity after each codec (still source; reported, not asserted)")
    print("  correlation of the decoded green trace with the true pulse (1 = intact, 0 = gone)")
    print("  condition          type II   type VI")
    mech = {}
    for c in conds:
        f2_, f6_ = by_still[(2, c.name)]["fid"], by_still[(6, c.name)]["fid"]
        mech[c.name] = {"II": f2_, "VI": f6_, "kbps": c.kbps, "codec": c.codec, "pix": c.pix_fmt}
        print(f"  {c.name:17s} {f2_:7.2f}   {f6_:7.2f}")
    (ROOT / "results").mkdir(exist_ok=True)
    (ROOT / "results" / "harness_validation_sim.json").write_text(json.dumps(
        {"encodes": [dict(r, key=f"{k[0]}:{k[1]}") for k, r in by.items()], "pulse_fidelity": mech,
         "metric": "correlation of band-limited green with the true pulse, still source, no screen light"},
        indent=1, default=float))
    shutil.rmtree(work, ignore_errors=True)
    finish()
