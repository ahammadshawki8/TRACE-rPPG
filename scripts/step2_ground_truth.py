"""T1 acceptance: recordings, ground truth, and analysis windows.

Checks the dataset readers, uniform resampling, windowing, and that the
ground-truth heart rate we derive from a reference PPG (with our own
spectral estimator) agrees with the heart rate that generated it.

If a real UBFC-rPPG download exists under data/ubfc/, it is checked too;
otherwise that part is reported as skipped, not passed.

Run:  .venv/Scripts/python.exe scripts/step2_ground_truth.py
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))
from _common import UBFC_DIR  # noqa: E402

from tracerppg.datasets import (  # noqa: E402
    WIN_S,
    load_dataset,
    load_recording,
    provided_hr,
    read_ubfc1_ground_truth,
    read_ubfc2_ground_truth,
    reference_hr,
    resample_uniform,
    sliding_windows,
    write_ubfc2_ground_truth,
)
from tracerppg.simulate import SimConfig, simulate_recording, write_ground_truth  # noqa: E402
from tracerppg.synth import heart_rhythm  # noqa: E402

results: list[tuple[str, bool, str]] = []


def check(name: str, passed: bool, detail: str = "") -> None:
    results.append((name, passed, detail))
    print(f"  [{'PASS' if passed else 'FAIL'}] {name}" + (f"  --  {detail}" if detail else ""))


def rule(title: str) -> None:
    print(f"\n{title}\n" + "-" * len(title))


tmp = Path(tempfile.mkdtemp(prefix="trace_t1_"))

# ---------------------------------------------------------------------------
rule("1. Ground-truth file formats round-trip")

tg = np.arange(0, 10, 1 / 60)
ppg = np.sin(2 * np.pi * 1.2 * tg)
hr = np.full_like(tg, 72.0)
write_ubfc2_ground_truth(tmp / "ground_truth.txt", ppg, hr, tg)
p2, h2, t2 = read_ubfc2_ground_truth(tmp / "ground_truth.txt")
err = max(np.max(np.abs(p2 - ppg)), np.max(np.abs(t2 - tg)))
check("DATASET_2 layout (PPG, HR, time rows) round-trips", err < 1e-5, f"max error {err:.1e}")

rows = np.column_stack([tg * 1000, hr, np.full_like(tg, 98.0), ppg])
np.savetxt(tmp / "gtdump.xmp", rows, delimiter=",")
p1, h1, t1 = read_ubfc1_ground_truth(tmp / "gtdump.xmp")
check("DATASET_1 layout (ms, HR, SpO2, PPG) parses",
      np.allclose(p1, ppg) and np.allclose(t1, tg), "time converted from ms to s")

# ---------------------------------------------------------------------------
rule("2. Uniform resampling repairs jittered timestamps")

rng = np.random.default_rng(0)
t_nom = np.arange(0, 30, 1 / 30)
t_jit = t_nom + rng.uniform(-0.25, 0.25, len(t_nom)) / 30
t_jit = np.delete(t_jit, rng.choice(len(t_jit), 45, replace=False))  # dropped frames
x_jit = np.sin(2 * np.pi * 1.3 * t_jit)
tu, xu = resample_uniform(t_jit, x_jit, 30.0)
spacing_ok = np.allclose(np.diff(tu), 1 / 30)
recon = float(np.max(np.abs(xu - np.sin(2 * np.pi * 1.3 * tu))))
check("output grid is exactly uniform after 45 dropped frames and jitter", spacing_ok)
check("the signal survives resampling", recon < 0.06, f"max error {recon:.3f} on unit amplitude")

# ---------------------------------------------------------------------------
rule("3. Analysis windows")

w = sliding_windows(60.0)
check("a one-minute recording yields nine 20 s windows at 5 s hop",
      len(w) == 9 and w[0] == (0.0, 20.0) and w[-1] == (40.0, 60.0), f"{len(w)} windows")
check("windows never run past the recording", all(b <= 60.0 for _, b in sliding_windows(59.9)))

# ---------------------------------------------------------------------------
rule("4. Reference HR from PPG matches the rhythm that generated it")

bin_bpm = 60.0 / WIN_S
worst = 0.0
print("  rate   windows  max |ref - true|")
for i, bpm in enumerate((48, 60, 72, 88, 104, 124)):
    folder = tmp / f"rate{bpm}"
    folder.mkdir()
    cfg = SimConfig(mean_bpm=bpm, duration_s=60.0, seed=10 + i)
    rhythm = heart_rhythm(cfg.duration_s + 1.0, mean_bpm=bpm, lf_bpm=cfg.lf_bpm,
                          hf_bpm=cfg.hf_bpm, resp_hz=cfg.resp_hz, seed=cfg.seed)
    write_ground_truth(folder, cfg, rhythm)
    rec = load_recording(folder)
    ws = sliding_windows(rec.duration_s)
    ref = reference_hr(rec, ws)
    true = provided_hr(rec, ws)
    e = float(np.max(np.abs(ref - true)))
    worst = max(worst, e)
    print(f"  {bpm:4d}   {len(ws):5d}    {e:6.2f} BPM")
check("reference HR within one resolution bin of the true rate, 48 to 124 BPM",
      worst <= bin_bpm, f"worst {worst:.2f} BPM, bin {bin_bpm:.1f} BPM")

# ---------------------------------------------------------------------------
rule("5. Simulated recording on disk loads like a real dataset")

sim_root = tmp / "sim"
simulate_recording(sim_root / "subject3", SimConfig(fitzpatrick=5, duration_s=12.0, seed=3))
recs = load_dataset(sim_root)
ok = (len(recs) == 1 and recs[0].fitzpatrick == 5 and recs[0].video_path.exists()
      and abs(recs[0].duration_s - 12.0) < 0.05 and recs[0].meta.get("source") == "simulated")
check("folder layout, lossless video, metadata and duration all present", ok,
      f"{recs[0].video_path.name}, Fitzpatrick {recs[0].fitzpatrick}, {recs[0].duration_s:.2f} s")

# ---------------------------------------------------------------------------
rule("6. Real UBFC-rPPG (only if downloaded to data/ubfc/)")

ubfc = UBFC_DIR
if ubfc.exists() and any(ubfc.iterdir()):
    recs = load_dataset(ubfc)
    diffs = []
    for rec in recs:
        ws = sliding_windows(rec.duration_s)
        d = np.abs(reference_hr(rec, ws) - provided_hr(rec, ws))
        diffs.append(np.nanmedian(d))
        print(f"  {rec.subject:10s} median |ref - provided| {np.nanmedian(d):5.2f} BPM")
    check("reference HR agrees with provided HR on real subjects (median, per subject)",
          max(diffs) <= bin_bpm, f"{len(recs)} subjects, worst median {max(diffs):.2f} BPM")
else:
    print("  SKIPPED: no UBFC data (set TRACE_UBFC_DIR or use data/ubfc/). Set TRACE_UBFC_DIR to the download to run it.")

# ---------------------------------------------------------------------------
print("\n" + "=" * 62)
passed = sum(1 for _, ok, _ in results if ok)
print(f"  {passed}/{len(results)} checks passed")
for name, ok, detail in results:
    if not ok:
        print(f"    FAILED: {name}: {detail}")
print("=" * 62)
sys.exit(0 if passed == len(results) else 1)
