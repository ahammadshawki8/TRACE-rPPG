"""T2 acceptance: from video frames to RGB traces.

Checks that lossless decoding is bit-exact, that the face tracker keeps a box
on every frame across all six Fitzpatrick types, that the extraction path
recovers heart rate end to end on still video, and that the quality score
falls when motion makes the green channel unreliable.

Results on simulated video are labelled as such.

Run:  .venv/Scripts/python.exe scripts/step3_video.py
"""

from __future__ import annotations

from concurrent.futures import ProcessPoolExecutor

import numpy as np

from _common import ROOT, WORKERS, check, finish, rule, sim_folder
from tracerppg.datasets import load_dataset, load_recording, reference_hr, sliding_windows, windowed_bpm
from tracerppg.roi import Traces, extract_traces
from tracerppg.simulate import SimConfig, _motion_track, render
from tracerppg.video import frames, probe


def green_eval(cfg: SimConfig) -> dict:
    folder = sim_folder(cfg)
    rec = load_recording(folder)
    tr = extract_traces(rec.video_path)
    ws = sliding_windows(rec.duration_s)
    ref = reference_hr(rec, ws)
    bpm, q = windowed_bpm(tr.t, tr.rgb[:, 1], tr.fps, ws)
    # The simulator's head translation is known exactly: the tracked box
    # centre minus the true displacement should be a constant offset.
    mv = _motion_track(len(tr.t), cfg.fps, cfg.motion, np.random.default_rng(cfg.seed))
    c = tr.boxes[:, :2] + tr.boxes[:, 2:] / 2
    ok = ~np.isnan(c[:, 0])
    track_err = float(max(np.std(c[ok, 0] - mv["dx"][ok]), np.std(c[ok, 1] - mv["dy"][ok])))
    return {
        "fz": cfg.fitzpatrick, "motion": cfg.motion,
        "mae": float(np.mean(np.abs(bpm - ref))), "q": float(np.mean(q)),
        "box_frames": float(np.mean(ok)), "track_err": track_err,
        "detect": tr.detect_rate, "px": float(np.mean(tr.n_pixels)),
    }


if __name__ == "__main__":
    # -----------------------------------------------------------------------
    rule("1. Lossless decoding is bit-exact")
    cfg = SimConfig(fitzpatrick=3, duration_s=4.0, seed=41)
    folder = sim_folder(cfg)
    rendered, _, _, _ = render(cfg)
    info = probe(folder / "vid.mkv")
    worst, count = 0, 0
    for a, (b, _) in zip(frames(folder / "vid.mkv", info), rendered):
        worst = max(worst, int(np.max(np.abs(a.astype(int) - b.astype(int)))))
        count += 1
    check("FFV1 RGB video decodes to exactly the rendered frames", worst == 0 and count == 120,
          f"{count} frames, max pixel difference {worst}")

    # -----------------------------------------------------------------------
    rule("2. Tracking across skin types (simulated, mild motion)")
    cfgs = [SimConfig(fitzpatrick=f, duration_s=40.0, motion=0.5, seed=100 + f) for f in range(1, 7)]
    # Still clips isolate the extraction path: no motion, no screen relighting.
    cfgs += [SimConfig(fitzpatrick=f, duration_s=40.0, motion=0.0, screen_light=0.0, seed=200 + f)
             for f in (2, 5)]
    with ProcessPoolExecutor(max_workers=WORKERS) as ex:
        rows = list(ex.map(green_eval, cfgs))
    moving = [r for r in rows if r["motion"] > 0]
    still = [r for r in rows if r["motion"] == 0]
    print("  type  box on frame  track error  fresh detections  skin px  green MAE  quality")
    for r in moving:
        print(f"   {r['fz']}      {r['box_frames']:6.1%}      {r['track_err']:5.2f} px        {r['detect']:6.1%}"
              f"       {r['px']:6.0f}   {r['mae']:6.2f}    {r['q']:.3f}")
    check("a face box exists on at least 99 percent of frames for every type",
          min(r["box_frames"] for r in moving) >= 0.99,
          f"worst {min(r['box_frames'] for r in moving):.1%}")
    worst_track = max(r["track_err"] for r in rows)
    check("phase-correlation tracking follows the true head motion to under 0.5 px",
          worst_track < 0.5, f"worst per-axis error std {worst_track:.2f} px")
    dark = np.mean([r["detect"] for r in moving if r["fz"] >= 4])
    light = np.mean([r["detect"] for r in moving if r["fz"] <= 3])
    print(f"  fresh Haar detection rate: types I to III {light:.1%}, IV to VI {dark:.1%}"
          "  (a detector disparity, reported as a finding, not hidden)")

    # -----------------------------------------------------------------------
    rule("3. End to end on still video: frames to BPM")
    for r in still:
        print(f"  still, type {r['fz']}: green MAE {r['mae']:.2f} BPM, quality {r['q']:.3f}")
    check("green channel recovers HR on still simulated video (MAE < 1.5 BPM)",
          max(r["mae"] for r in still) < 1.5, f"worst {max(r['mae'] for r in still):.2f} BPM")

    # -----------------------------------------------------------------------
    rule("4. The quality score sees motion damage")
    q_still = np.mean([r["q"] for r in still])
    q_move = np.mean([r["q"] for r in moving if r["fz"] in (2, 5)])
    mae_move = np.mean([r["mae"] for r in moving if r["fz"] in (2, 5)])
    check("quality falls when motion breaks the green channel",
          q_move < q_still, f"still {q_still:.3f} vs moving {q_move:.3f} (moving green MAE {mae_move:.1f} BPM)")

    # -----------------------------------------------------------------------
    rule("5. Traces persist")
    rec = load_recording(folder)
    tr = extract_traces(rec.video_path)
    tr.save(ROOT / "data" / "cache" / "_traces_check.npz")
    back = Traces.load(ROOT / "data" / "cache" / "_traces_check.npz")
    check("saved traces load back identically", np.array_equal(tr.rgb, back.rgb) and back.fps == tr.fps)

    # -----------------------------------------------------------------------
    rule("6. Real UBFC-rPPG (only if downloaded to data/ubfc/)")
    ubfc = ROOT / "data" / "ubfc"
    if ubfc.exists() and any(ubfc.iterdir()):
        maes = []
        for rec in load_dataset(ubfc):
            tr = extract_traces(rec.video_path)
            ws = sliding_windows(min(rec.duration_s, tr.t[-1]))
            bpm, _ = windowed_bpm(tr.t, tr.rgb[:, 1], tr.fps, ws)
            maes.append(np.mean(np.abs(bpm - reference_hr(rec, ws))))
            print(f"  {rec.subject:10s} green MAE {maes[-1]:6.2f}  box {np.mean(~np.isnan(tr.boxes[:, 0])):.1%}")
        print(f"  UBFC green MAE over {len(maes)} subjects: {np.mean(maes):.2f} BPM (published GREEN about 19.7)")
    else:
        print("  SKIPPED: data/ubfc/ not present.")

    finish()
