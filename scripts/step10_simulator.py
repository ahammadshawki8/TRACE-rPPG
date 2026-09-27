"""Acceptance checks for the live simulator and the conditions it can create.

    .venv/Scripts/python.exe scripts/step10_simulator.py

The live app lets a presenter change skin type, heart rate, motion and
lighting while a simulated volunteer is on screen. These checks prove each
control does what it claims, and that the pipeline responds the way the
physics says it should: motion and a flickering lamp corrupt the green
channel, TRACE moves its weight away from it, and a change of heart rate is
followed. Everything is read with the app's own analysis (tracerppg.simeval).
"""

from __future__ import annotations

import time

import numpy as np

from _common import check, finish, rule
from tracerppg.simeval import evaluate, stream
from tracerppg.simulate import LiveParams, LiveSimulator


def err(rows, key):
    return np.array([abs((r["bpm"] if key == "trace" else r["methods"][key]["bpm"]) - r["truth"]) for r in rows])


def weight(rows, key):
    """Mean trust (share of the three quality scores). Under TRACE v3 the
    weights themselves are 1 for the selected method and 0 otherwise."""
    return float(np.mean([r["scores"][key] for r in rows]))


def main() -> None:
    rule("1. The simulator itself")
    sim = LiveSimulator(LiveParams(), seed=1)
    t0 = time.perf_counter()
    for _ in range(300):
        frame, t = sim.next_frame()
    ms = 1000 * (time.perf_counter() - t0) / 300
    check("renders 640x480 RGB frames fast enough for 30 fps next to the pipeline",
          frame.shape == (480, 640, 3) and frame.dtype == np.uint8 and ms < 20, f"{ms:.1f} ms per frame (budget 33)")
    p = sim.set(fitzpatrick=9, bpm=500, motion=-1, nonsense=3)
    check("settings are clamped and unknown keys ignored",
          p.fitzpatrick == 6 and p.bpm == 180 and p.motion == 0, f"type {p.fitzpatrick}, {p.bpm:.0f} BPM, motion {p.motion}")

    sim = LiveSimulator(LiveParams(bpm=72), seed=2)
    for _ in range(30 * 30):
        sim.next_frame()
    before = sim.true_bpm(30.0, 20)
    sim.set(bpm=110)
    for _ in range(30 * 30):
        sim.next_frame()
    after = sim.true_bpm(60.0, 10)
    check("the true heart rate follows the control", abs(before - 72) < 1.5 and abs(after - 110) < 2,
          f"{before:.1f} BPM at 72, {after:.1f} BPM 30 s after setting 110")

    amp = {}
    for fz in (1, 6):
        s = LiveSimulator(LiveParams(fitzpatrick=fz, motion=0.0, screen_light=0.0), seed=3)
        s.a[:] = 0.0  # pulse off: measure the pulse by difference below
        t_off, rgb_off = stream(s, 10)
        s = LiveSimulator(LiveParams(fitzpatrick=fz, motion=0.0, screen_light=0.0), seed=3)
        t_on, rgb_on = stream(s, 10)
        n = min(len(rgb_on), len(rgb_off))
        g = rgb_on[:n, 1] - rgb_off[:n, 1]
        amp[fz] = float(np.ptp(g) / np.mean(rgb_on[:n, 1]))
    check("darker skin carries a smaller relative pulse (melanin)", amp[6] < 0.8 * amp[1],
          f"green pulse depth type I {100 * amp[1]:.2f} percent, type VI {100 * amp[6]:.2f} percent")

    rule("2. What the pipeline does under each control")
    runs = {
        "still": LiveParams(motion=0.1),
        "talking": LiveParams(motion=1.2),
        "flicker": LiveParams(motion=0.3, flicker_hz=1.5, flicker_depth=0.03),
        "fast": LiveParams(motion=0.3, bpm=120),
    }
    rows = {k: evaluate(LiveSimulator(v, seed=40 + i), 60) for i, (k, v) in enumerate(runs.items())}
    for k, r in rows.items():
        print(f"  {k:8s} MAE green {err(r, 'green').mean():5.1f} chrom {err(r, 'chrom').mean():5.1f} "
              f"pos {err(r, 'pos').mean():5.1f} TRACE {err(r, 'trace').mean():5.1f}  weights "
              f"g {weight(r, 'green'):.2f} c {weight(r, 'chrom'):.2f} p {weight(r, 'pos'):.2f}")

    w5 = float(np.mean(err(rows["still"], "trace") <= 5))
    check("still volunteer: TRACE within 5 BPM on most readings", w5 >= 0.8, f"{w5:.0%} of {len(rows['still'])} readings")

    # One 60 s volunteer varies too much to judge motion (one seed's green
    # happened to survive talking), so this uses three per condition.
    still3 = [r for s in (70, 71, 72) for r in evaluate(LiveSimulator(LiveParams(motion=0.1), seed=s), 60)]
    talk3 = [r for s in (70, 71, 72) for r in evaluate(LiveSimulator(LiveParams(motion=1.2), seed=s), 60)]
    g, tr = err(talk3, "green").mean(), err(talk3, "trace").mean()
    check("talking corrupts green but not TRACE (3 volunteers)", g > 3 * tr and tr < 5, f"green {g:.1f} vs TRACE {tr:.1f} BPM")
    check("TRACE trusts green less when volunteers talk (3 volunteers)",
          weight(talk3, "green") < weight(still3, "green"),
          f"green trust {weight(still3, 'green'):.2f} still, {weight(talk3, 'green'):.2f} talking")

    ge = float(np.median(err(rows["flicker"], "green")))
    pe = float(np.mean(err(rows["flicker"], "pos") <= 5))
    check("a flickering lamp fools green, while POS cancels it", ge > 10 and pe >= 0.8,
          f"green median error {ge:.1f} BPM, POS within 5 on {pe:.0%}")
    te = float(np.median(err(rows["flicker"], "trace")))
    tw = float(np.mean(err(rows["flicker"], "trace") <= 5))
    check("TRACE is right on most readings under the flickering lamp", te < 3 and tw >= 0.7,
          f"median error {te:.1f} BPM, within 5 on {tw:.0%}, mean {err(rows['flicker'], 'trace').mean():.1f}")

    fw = float(np.mean(err(rows["fast"], "trace") <= 5))
    check("a fast heart (120 BPM) is followed", fw >= 0.7, f"within 5 BPM on {fw:.0%}")

    live = evaluate(LiveSimulator(LiveParams(motion=0.2, bpm=70), seed=50), 75, schedule={25.0: {"bpm": 110}}, first=50)
    lw = float(np.mean(err(live, "trace") <= 5))
    check("a change of heart rate mid-run is followed", lw >= 0.7,
          f"70 then 110 BPM at 25 s: within 5 on {lw:.0%} of readings after 50 s, truth {live[-1]['truth']:.1f}")

    rule("3. Liveness: a photo has no pulse")
    import sys
    from collections import deque
    sys.path.insert(0, str(__import__("_common").ROOT / "app"))
    from engine import LIVENESS_Q, LIVENESS_READOUTS, _liveness_verdict
    from tracerppg.simeval import analyse, frozen_params
    verdicts = {}
    for pulse in (1.0, 0.0):
        for seed in (61, 62):
            s = LiveSimulator(LiveParams(motion=0.1, pulse=pulse), seed=seed)
            t, rgb = stream(s, 45)
            h = deque(maxlen=LIVENESS_READOUTS)
            for te in np.arange(20, 45.01, 0.5):
                a = analyse(t, rgb, te, frozen_params())
                m, thr = a["methods"], LIVENESS_Q
                h.append(min(m["chrom"]["quality"], m["pos"]["quality"]) >= thr and abs(m["chrom"]["bpm"] - m["pos"]["bpm"]) <= 5)
            verdicts.setdefault(pulse, []).append(_liveness_verdict(h)["verdict"])
    check("a photo (no pulse) is never taken for a living face", "pulse" not in verdicts[0.0], f"photo: {verdicts[0.0]}")
    check("a still living face is recognised", all(v == "pulse" for v in verdicts[1.0]), f"living: {verdicts[1.0]}")

    rule("4. Does the confidence mean something")
    # Judged on the held-out test cohort (3,060 read-outs, tune_fusion_live.py):
    # a handful of runs here leaves too few flagged read-outs to compare.
    import json as _json
    tv = _json.loads((__import__("_common").ROOT / "results" / "fusion_v3_test.json").read_text())["test"]["v3"]
    check("confident read-outs are far more accurate than flagged ones (held-out test set)",
          tv["mae_confident"] < tv["mae_flagged"] / 3,
          f"confident {tv['confident']:.0%}: MAE {tv['mae_confident']:.1f} vs flagged {tv['mae_flagged']:.1f} BPM, {tv['n']} read-outs")
    finish()


if __name__ == "__main__":
    main()
