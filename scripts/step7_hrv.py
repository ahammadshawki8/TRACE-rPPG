"""T9 acceptance: HRV and the second Fourier transform.

Theory: the PSD is scaled so band powers are in ms^2 (Parseval), and a known
sinusoidal RR modulation comes back at the right LF/HF. An independent
implementation (scipy.signal.welch) must agree. Engineering: beat timing
below one frame, missed beats rejected, short captures refused. Then HRV
from simulated face video against the exact beat times, compared with the
WaveHRV reference accuracy (RMSSD MAE about 10.5 ms, SDNN about 6.15 ms on
UBFC-rPPG). Video numbers are simulated.

Run:  .venv/Scripts/python.exe scripts/step7_hrv.py
"""

from __future__ import annotations

import json
from concurrent.futures import ProcessPoolExecutor

import numpy as np
from scipy.signal import welch

from _common import ROOT, WORKERS, check, finish, rule, sim_traces
from tracerppg.fusion import band_limited_pulses
from tracerppg.hrv import (
    HF_BAND,
    HRV_METHOD,
    LF_BAND,
    RR_FS,
    band_power,
    clean_rr,
    detect_beats,
    hrv_from_beats,
    hrv_from_pulse,
    match_beats,
    psd,
    resample_rr,
)
from tracerppg.simulate import SimConfig
from tracerppg.synth import heart_rhythm, ppg_from_beats


def video_hrv(cfg):
    rec, tr = sim_traces(cfg)
    pulses = band_limited_pulses(tr.rgb, tr.fps)
    # HRV uses POS. Picking the method by spectral quality chose green on
    # three of six subjects and found only half the beats (measured,
    # 2026-09-11); POS found 79 percent.
    name = HRV_METHOD
    est, beats = hrv_from_pulse(pulses[name], tr.fps)
    true_beats = np.array(rec.meta["beat_times"])
    true_beats = true_beats[true_beats <= tr.t[-1]]
    truth = hrv_from_beats(true_beats)
    err = match_beats(beats, true_beats)
    return {"fz": cfg.fitzpatrick, "method": name, "coverage": len(err) / len(true_beats),
            "timing_rms_ms": float(np.sqrt(np.mean(err**2)) * 1000) if len(err) else float("nan"),
            "sdnn": (est.sdnn_ms, truth.sdnn_ms), "rmssd": (est.rmssd_ms, truth.rmssd_ms),
            "lf_hf": (est.lf_hf, truth.lf_hf), "resp": (est.resp_hz, truth.resp_hz, cfg.resp_hz),
            "indicator": est.indicator()}


if __name__ == "__main__":
    rng = np.random.default_rng(3)

    # -----------------------------------------------------------------------
    rule("1. PSD scaling obeys Parseval")
    x = rng.normal(0, 40.0, 4 * 300)  # ms, 300 s at 4 Hz
    f, p = psd(x, RR_FS)
    total = float(np.trapezoid(p, f))
    check("integrated PSD equals the variance (within 10 percent)", abs(total / np.var(x) - 1) < 0.10,
          f"{total:.0f} vs {np.var(x):.0f} ms^2")

    # -----------------------------------------------------------------------
    rule("2. A known modulation comes back at the right LF/HF")
    t = np.arange(0, 300, 1 / RR_FS)
    a_lf, a_hf = 30.0, 20.0
    rr = 850 + a_lf * np.sin(2 * np.pi * 0.10 * t) + a_hf * np.sin(2 * np.pi * 0.25 * t)
    f, p = psd(rr, RR_FS)
    ratio = band_power(f, p, LF_BAND) / band_power(f, p, HF_BAND)
    expect = (a_lf / a_hf) ** 2
    check("LF/HF of a two-tone RR series matches (A_lf/A_hf)^2", abs(ratio / expect - 1) < 0.05,
          f"{ratio:.3f} vs {expect:.3f}")
    fw, pw = welch(rr, RR_FS, nperseg=256, detrend="linear")
    ratio_sp = band_power(fw, pw, LF_BAND) / band_power(fw, pw, HF_BAND)
    check("independent scipy.signal.welch agrees", abs(ratio_sp / ratio - 1) < 0.05,
          f"scipy {ratio_sp:.3f} vs ours {ratio:.3f}")

    # -----------------------------------------------------------------------
    rule("3. LF/HF from a generated heart rhythm (5 min, no wander)")
    rh = heart_rhythm(300.0, mean_bpm=68, lf_bpm=3.0, hf_bpm=2.5, wander_bpm=0.0, seed=4)
    h = hrv_from_beats(rh.beat_times)
    check("LF/HF within 25 percent of the generating ratio", abs(h.lf_hf / rh.lf_hf_nominal - 1) < 0.25,
          f"{h.lf_hf:.2f} vs nominal {rh.lf_hf_nominal:.2f}")
    check("respiration rate recovered from the HF peak", abs(h.resp_hz - 0.25) < 0.02,
          f"{h.resp_hz:.3f} Hz = {h.resp_hz * 60:.1f} breaths/min")

    # -----------------------------------------------------------------------
    rule("4. Beat timing below one frame")
    rh = heart_rhythm(180.0, mean_bpm=75, seed=6)
    fs = 30.0
    tt = np.arange(0, 180.0, 1 / fs)
    sig = ppg_from_beats(tt, rh.beat_times) + 0.05 * rng.normal(size=len(tt))
    beats = detect_beats(sig, fs)
    err = match_beats(beats, rh.beat_times[rh.beat_times < 179.5])
    rms = float(np.sqrt(np.mean(err**2)) * 1000)
    check("beat timing RMS error under 10 ms at 30 fps (a frame is 33 ms)", rms < 10.0, f"{rms:.2f} ms")
    h_est, h_true = hrv_from_beats(beats), hrv_from_beats(rh.beat_times)
    check("RMSSD within 5 ms of truth on a clean pulse", abs(h_est.rmssd_ms - h_true.rmssd_ms) < 5.0,
          f"{h_est.rmssd_ms:.1f} vs {h_true.rmssd_ms:.1f} ms")

    # -----------------------------------------------------------------------
    rule("5. A missed beat does not wreck the statistics")
    missed = np.delete(rh.beat_times, [40, 120])
    _, rr_c = clean_rr(missed)
    sdnn_raw = float(np.std(np.diff(missed), ddof=1) * 1000)
    sdnn_clean = float(np.std(rr_c, ddof=1) * 1000)
    check("the Malik rule removes the doubled intervals", abs(sdnn_clean / h_true.sdnn_ms - 1) < 0.10,
          f"SDNN {sdnn_raw:.1f} ms raw, {sdnn_clean:.1f} cleaned, {h_true.sdnn_ms:.1f} true")

    # -----------------------------------------------------------------------
    rule("6. Short captures are refused for LF/HF")
    short = hrv_from_beats(rh.beat_times[rh.beat_times < 30])
    check("30 s gives no LF/HF and says why", not short.valid_frequency and "2 minutes" in short.indicator(),
          short.indicator())

    def table(rows):
        print("  type method  beats found  timing RMS   SDNN est/true   RMSSD est/true   LF/HF est/true")
        for r in rows:
            lf = r["lf_hf"]
            print(f"   {r['fz']}   {r['method']:6s}  {r['coverage']:8.1%}   {r['timing_rms_ms']:7.1f} ms   "
                  f"{r['sdnn'][0]:5.1f} / {r['sdnn'][1]:5.1f}    {r['rmssd'][0]:5.1f} / {r['rmssd'][1]:5.1f}     "
                  f"{(lf[0] or float('nan')):5.2f} / {(lf[1] or float('nan')):5.2f}")
        sd = float(np.mean([abs(a - b) for a, b in (r["sdnn"] for r in rows)]))
        rm = float(np.mean([abs(a - b) for a, b in (r["rmssd"] for r in rows)]))
        print(f"  SDNN MAE {sd:.2f} ms, RMSSD MAE {rm:.2f} ms")
        return sd, rm

    # -----------------------------------------------------------------------
    rule("7. End to end on clean simulated video (150 s, still, no screen light)")
    clean = [SimConfig(fitzpatrick=fz, duration_s=150.0, motion=0.0, screen_light=0.0, mean_bpm=bpm, seed=760 + i)
             for i, (fz, bpm) in enumerate([(2, 68), (5, 76)])]
    with ProcessPoolExecutor(max_workers=WORKERS) as ex:
        crow = list(ex.map(video_hrv, clean))
    csd, crm = table(crow)
    check("on clean video at least 90 percent of beats are found, both skin types",
          min(r["coverage"] for r in crow) >= 0.90, f"worst {min(r['coverage'] for r in crow):.1%}")
    check("on clean video SDNN is within 10 ms of truth", csd < 10.0, f"SDNN MAE {csd:.1f} ms")

    # -----------------------------------------------------------------------
    rule("8. Natural sitting (motion and screen light): reported, not asserted")
    cfgs = [SimConfig(fitzpatrick=fz, duration_s=150.0, motion=0.3, mean_bpm=bpm, seed=700 + i)
            for i, (fz, bpm) in enumerate([(2, 66), (2, 78), (3, 72), (5, 70), (5, 82), (6, 74)])]
    with ProcessPoolExecutor(max_workers=WORKERS) as ex:
        rows = list(ex.map(video_hrv, cfgs))
    sd, rm = table(rows)
    print("  (WaveHRV on real UBFC-rPPG: SDNN 6.15, RMSSD 10.5 ms. Beat-level timing is far more fragile than")
    print("   heart rate: one missed or extra beat moves RMSSD by tens of ms.)")
    print(f"  example read-out: {rows[0]['indicator']}")
    (ROOT / "results").mkdir(exist_ok=True)
    (ROOT / "results" / "hrv_sim.json").write_text(json.dumps(
        {"clean": crow, "natural": rows, "clean_sdnn_mae": csd, "clean_rmssd_mae": crm,
         "natural_sdnn_mae": sd, "natural_rmssd_mae": rm}, indent=1, default=float))
    finish()
