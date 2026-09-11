"""Recordings, ground truth, and analysis windows. Tier T1.

A recording is a video file plus a reference PPG waveform with timestamps.
Everything downstream (methods, fusion, the compression grid) is evaluated
per analysis window, and the ground-truth heart rate for a window comes from
running the same spectral estimator on the reference PPG over the same span.
Using one estimator for both sides means a disagreement is a disagreement
about the pulse, not about how two tools define "heart rate".

Supported layouts
-----------------
UBFC-rPPG DATASET_2 (and our simulator, which writes the same layout)::

    subject1/
        vid.avi            (or vid.mkv for simulated FFV1)
        ground_truth.txt   row 0: PPG, row 1: HR (BPM), row 2: time (s)
        meta.json          optional: fitzpatrick, fps, simulator parameters

UBFC-rPPG DATASET_1::

    subject/
        vid.avi
        gtdump.xmp         CSV rows: time (ms), HR, SpO2, PPG

The DATASET_2 row order follows rPPG-Toolbox's reader. Verify it against a
real download before trusting results (CLAUDE.md, T1).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from .preprocess import clean_pulse
from .spectral import HR_BAND, estimate_bpm

VIDEO_NAMES = ("vid.avi", "vid.mkv", "vid.mp4")

# Evaluation windows used everywhere unless a script says otherwise.
# 20 s gives a 3 BPM bin before interpolation; a 5 s hop gives nine windows
# on a one-minute recording.
WIN_S = 20.0
HOP_S = 5.0


@dataclass
class Recording:
    """One subject session: where the video is, and what the heart did."""

    subject: str
    video_path: Path
    ppg: np.ndarray
    ppg_t: np.ndarray
    hr_provided: np.ndarray | None = None
    meta: dict = field(default_factory=dict)

    @property
    def duration_s(self) -> float:
        return float(self.ppg_t[-1] - self.ppg_t[0])

    @property
    def fitzpatrick(self) -> int | None:
        v = self.meta.get("fitzpatrick")
        return int(v) if v is not None else None


def read_ubfc2_ground_truth(path: Path) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Parse a DATASET_2 ground_truth.txt into (ppg, hr, t)."""
    rows = [r for r in Path(path).read_text().splitlines() if r.strip()]
    if len(rows) < 3:
        raise ValueError(f"{path}: expected 3 rows (PPG, HR, time), found {len(rows)}")
    ppg, hr, t = (np.array([float(v) for v in r.split()]) for r in rows[:3])
    if not (len(ppg) == len(hr) == len(t)):
        raise ValueError(f"{path}: row lengths differ ({len(ppg)}, {len(hr)}, {len(t)})")
    return ppg, hr, t


def read_ubfc1_ground_truth(path: Path) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Parse a DATASET_1 gtdump.xmp (time ms, HR, SpO2, PPG) into (ppg, hr, t)."""
    data = np.loadtxt(path, delimiter=",")
    return data[:, 3], data[:, 1], data[:, 0] / 1000.0


def write_ubfc2_ground_truth(path: Path, ppg: np.ndarray, hr: np.ndarray, t: np.ndarray) -> None:
    """Write the DATASET_2 layout, so simulated data exercises the real reader."""
    with open(path, "w") as fh:
        for row in (ppg, hr, t):
            fh.write(" ".join(f"{v:.6e}" for v in row) + "\n")


def load_recording(folder: Path) -> Recording:
    """Load one subject folder in either UBFC layout."""
    folder = Path(folder)
    video = next((folder / n for n in VIDEO_NAMES if (folder / n).exists()), None)
    if (folder / "ground_truth.txt").exists():
        ppg, hr, t = read_ubfc2_ground_truth(folder / "ground_truth.txt")
    elif (folder / "gtdump.xmp").exists():
        ppg, hr, t = read_ubfc1_ground_truth(folder / "gtdump.xmp")
    else:
        raise FileNotFoundError(f"{folder}: no ground_truth.txt or gtdump.xmp")
    meta = {}
    if (folder / "meta.json").exists():
        meta = json.loads((folder / "meta.json").read_text())
    return Recording(
        subject=folder.name,
        video_path=video if video is not None else folder / VIDEO_NAMES[0],
        ppg=ppg,
        ppg_t=t - t[0],
        hr_provided=hr,
        meta=meta,
    )


def load_dataset(root: Path) -> list[Recording]:
    """Every subject folder under `root`, in natural subject order."""
    root = Path(root)

    def key(p: Path):
        digits = "".join(c for c in p.name if c.isdigit())
        return (int(digits) if digits else 0, p.name)

    folders = sorted(
        (p for p in root.iterdir() if p.is_dir()
         and ((p / "ground_truth.txt").exists() or (p / "gtdump.xmp").exists())),
        key=key,
    )
    return [load_recording(p) for p in folders]


def resample_uniform(t: np.ndarray, x: np.ndarray, fs: float) -> tuple[np.ndarray, np.ndarray]:
    """Put an unevenly sampled trace onto a uniform grid.

    The DFT assumes uniform spacing. Dropped webcam frames and jittery
    oximeter timestamps both break that, so everything is resampled onto a
    clean grid before any spectral step.

    Cubic, not linear: linear interpolation across a gap of h seconds errs by
    up to (omega h)^2 / 8 of the amplitude, which is 8 percent for a 78 BPM
    pulse across three dropped frames at 30 fps (measured in step2).
    """
    from scipy.interpolate import CubicSpline

    t = np.asarray(t, dtype=float)
    order = np.argsort(t)
    t, x = t[order], np.asarray(x, dtype=float)[order]
    keep = np.concatenate([[True], np.diff(t) > 0])
    t, x = t[keep], x[keep]
    tu = np.arange(t[0], t[-1], 1.0 / fs)
    return tu, CubicSpline(t, x)(tu)


def sliding_windows(duration_s: float, win_s: float = WIN_S, hop_s: float = HOP_S) -> list[tuple[float, float]]:
    """Analysis windows (start, end) in seconds that fit inside the recording."""
    out = []
    start = 0.0
    while start + win_s <= duration_s + 1e-9:
        out.append((start, start + win_s))
        start += hop_s
    return out


def window_slice(t: np.ndarray, start: float, end: float) -> slice:
    """Indices of a uniform time axis falling inside [start, end)."""
    i0 = int(np.searchsorted(t, start, side="left"))
    i1 = int(np.searchsorted(t, end, side="left"))
    return slice(i0, i1)


def windowed_bpm(
    t: np.ndarray,
    signal: np.ndarray,
    fs: float,
    windows: list[tuple[float, float]],
    already_clean: bool = False,
) -> tuple[np.ndarray, np.ndarray]:
    """BPM and quality per window. The whole trace is filtered once, then cut."""
    x = signal if already_clean else clean_pulse(signal, fs)
    bpm, q = [], []
    for a, b in windows:
        seg = x[window_slice(t, a, b)]
        e = estimate_bpm(seg, fs, band=HR_BAND)
        bpm.append(e.bpm)
        q.append(e.quality)
    return np.array(bpm), np.array(q)


def reference_hr(rec: Recording, windows: list[tuple[float, float]], fs: float = 60.0) -> np.ndarray:
    """Ground-truth BPM per window from the reference PPG."""
    tu, xu = resample_uniform(rec.ppg_t, rec.ppg, fs)
    bpm, _ = windowed_bpm(tu, xu, fs, windows)
    return bpm


def provided_hr(rec: Recording, windows: list[tuple[float, float]]) -> np.ndarray | None:
    """Mean of the dataset's own HR column per window, as a cross-check."""
    if rec.hr_provided is None:
        return None
    out = []
    for a, b in windows:
        m = (rec.ppg_t >= a) & (rec.ppg_t < b)
        vals = rec.hr_provided[m]
        vals = vals[(vals > 30) & (vals < 250)]
        out.append(float(np.mean(vals)) if len(vals) else np.nan)
    return np.array(out)
