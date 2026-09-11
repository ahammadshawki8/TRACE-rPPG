"""Build the demo app's assets (T10).

1. Replay clips: simulated volunteers (lighter and darker skin, calm and
   restless) rendered losslessly, then stored as near-lossless H.264 4:4:4 so
   the app only has to decode, not render. The pulse retained by that storage
   step is measured and printed: it must be close to 100 percent, or the
   replays would already be a compressed condition.
2. Compression-lab data from the grid's cell table (results/cells_sim.csv).
3. Face thumbnails at every H.264 bitrate, so compression is visible.

Run after the grid and analysis:
    .venv/Scripts/python.exe scripts/build_app_assets.py [--skip-replays]
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
from pathlib import Path

import cv2
import numpy as np
import pandas as pd

from _common import ROOT
from tracerppg.compress import BITRATES, Condition, encode
from tracerppg.methods import temporal_normalise
from tracerppg.preprocess import clean_pulse
from tracerppg.roi import extract_traces
from tracerppg.simulate import SimConfig, simulate_recording
from tracerppg.synth import ppg_from_beats
from tracerppg.video import frames

REPLAY = ROOT / "data" / "replay"
LAB = ROOT / "app" / "static" / "lab"
CLIPS = {"type2_calm": (2, 0.3), "type5_calm": (5, 0.3), "type2_restless": (2, 1.6), "type5_restless": (5, 1.6)}


def fidelity(tr, beats) -> float:
    """Correlation of the band-limited green trace with the true pulse."""
    g = clean_pulse(temporal_normalise(tr.rgb, tr.fps)[:, 1] - 1.0, tr.fps)
    p = clean_pulse(ppg_from_beats(tr.t, np.asarray(beats)), tr.fps)
    return float(np.corrcoef(g, p)[0, 1])


def build_replays() -> None:
    REPLAY.mkdir(parents=True, exist_ok=True)
    for name, (fz, motion) in CLIPS.items():
        dest = REPLAY / f"{name}.mkv"
        if dest.exists():
            print(f"  {name}: exists")
            continue
        tmp = REPLAY / f"_{name}"
        cfg = SimConfig(fitzpatrick=fz, motion=motion, duration_s=180.0, mean_bpm=70.0 + 4 * fz, seed=9000 + 10 * fz + int(motion * 10))
        simulate_recording(tmp, cfg)
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(tmp / "vid.mkv"), "-c:v", "libx264", "-preset", "veryfast",
                        "-crf", "4", "-pix_fmt", "yuv444p", str(dest)], check=True)
        meta = json.loads((tmp / "meta.json").read_text())
        (REPLAY / f"{name}.json").write_text(json.dumps({"fitzpatrick": fz, "motion": motion,
                                                         "beat_times": meta["beat_times"]}))
        f_src = fidelity(extract_traces(tmp / "vid.mkv"), meta["beat_times"])
        f_dst = fidelity(extract_traces(dest), meta["beat_times"])
        mb = dest.stat().st_size / 1e6
        print(f"  {name}: {mb:.0f} MB, pulse fidelity lossless {f_src:.3f} vs stored {f_dst:.3f}")
        shutil.rmtree(tmp, ignore_errors=True)


def build_thumbs() -> dict:
    LAB.mkdir(parents=True, exist_ok=True)
    out: dict = {}
    for fz, key in ((2, "II"), (5, "V")):
        src = ROOT / "data" / "work" / f"thumb_{fz}"
        simulate_recording(src, SimConfig(fitzpatrick=fz, duration_s=3.0, motion=0.3, seed=9500 + fz))
        conds = [("lossless", None)] + [(k, Condition(f"h264_{k}k", "h264", k)) for k in BITRATES]
        for rate, cond in conds:
            video = src / "vid.mkv" if cond is None else encode(src / "vid.mkv", src, cond).path
            frame = None
            for i, f in enumerate(frames(video)):
                if i == 60:
                    frame = f
                    break
            box = (230, 110, 200, 200)  # face region of the simulator's base frame
            x, y, w, h = box
            crop = frame[y : y + h, x : x + w]
            crop = cv2.resize(crop, (400, 400), interpolation=cv2.INTER_NEAREST)  # keep the blocks visible
            name = f"t{key}_{rate}.jpg"
            cv2.imwrite(str(LAB / name), cv2.cvtColor(crop, cv2.COLOR_RGB2BGR), [cv2.IMWRITE_JPEG_QUALITY, 95])
            out.setdefault(str(rate), {})[key] = f"/static/lab/{name}"
        shutil.rmtree(src, ignore_errors=True)
    return out


def build_lab(thumbs: dict) -> None:
    cells = pd.read_csv(ROOT / "results" / "cells_sim.csv")
    labels = {"green": "Green", "chrom": "CHROM", "pos": "POS", "ica": "ICA", "trace": "TRACE",
              "physnet": "PhysNet", "factorizephys": "FactorizePhys"}
    methods = [m for m in ("green", "chrom", "pos", "trace", "physnet", "factorizephys") if m in set(cells["method"])]
    rates = ["lossless"] + [str(k) for k in sorted(BITRATES, reverse=True)]
    mae: dict = {}
    for m in methods:
        mae[m] = {}
        for r in rates:
            cond = "lossless_rgb" if r == "lossless" else f"h264_{r}k"
            d = cells[(cells["method"] == m) & (cells["condition"] == cond)]
            mae[m][r] = {g: float(d.loc[d["group"] == g, "mae"].iloc[0]) for g in ("I-III", "IV-VI")
                         if (d["group"] == g).any()}
    kept = {}
    hv = ROOT / "results" / "harness_validation_sim.json"
    if hv.exists():
        fid = json.loads(hv.read_text()).get("pulse_fidelity", {})
        for k, v in fid.items():
            if k == "lossless_rgb":
                kept["lossless"] = {"II": v["II"], "VI": v["VI"]}
            elif v["codec"] == "h264" and v["pix"] == "yuv420p" and v["kbps"]:
                kept[str(v["kbps"])] = {"II": v["II"], "VI": v["VI"]}
    n = int(cells["n_subjects"].max())
    lab = {"rates": rates, "methods": methods, "labels": labels, "mae": mae, "kept": kept,
           "thumbs": thumbs, "n_subjects": int(n * 2), "source": "simulated"}
    (LAB / "lab.json").write_text(json.dumps(lab, indent=1))
    print(f"  lab.json: {len(methods)} methods x {len(rates)} rates")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--skip-replays", action="store_true")
    args = ap.parse_args()
    if not args.skip_replays:
        print("replay clips")
        build_replays()
    print("thumbnails")
    th = build_thumbs()
    print("lab data")
    build_lab(th)
