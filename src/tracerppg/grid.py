"""The experiment grid: subject x condition x method. Tier T7.

Stage 1 (`process_subject`, expensive, parallel over subjects): take one
lossless source, run it through every compression condition, and keep only
what later stages need: the RGB traces per condition (a few kilobytes) and,
if neural baselines are enabled, 72x72 face crops. Encoded videos are
deleted as soon as they are decoded, so disk use stays bounded.

Stage 2 (`evaluate_subject`, cheap, repeatable): from stored traces, run
every classical method and TRACE over the shared analysis windows and emit
one tidy row per (subject, condition, method, window). Neural predictions,
if present, join the same table as extra methods.
"""

from __future__ import annotations

import json
import shutil
from dataclasses import asdict
from pathlib import Path

import numpy as np

from .compress import Condition, encode, grid_conditions
from .datasets import Recording, load_recording, reference_hr, sliding_windows, window_slice
from .fusion import (DEFAULT_CONFIDENCE, DEFAULT_GAMMA, DEFAULT_MASK_K, artifact_reference,
                     band_limited_pulses, fuse)
from .methods import METHODS
from .roi import Traces, extract_traces
from .spectral import estimate_bpm


def subject_dir(out_root: Path, subject: str) -> Path:
    return Path(out_root) / subject


def process_subject(
    source_folder: Path,
    subject: str,
    out_root: Path,
    work_root: Path,
    conditions: list[Condition] | None = None,
    crop_size: int | None = None,
    delete_source: bool = False,
    crop_conditions: set[str] | None = None,
    crops_root: Path | None = None,
) -> Path:
    """Encode, decode and extract traces for every condition of one subject.

    Face crops (for the neural baselines) are saved only for the conditions
    in `crop_conditions`, under `crops_root/<subject>/`, so inference can run
    later in a single memory-bounded process.
    """
    conditions = conditions or grid_conditions()
    rec = load_recording(source_folder)
    out = subject_dir(out_root, subject)
    out.mkdir(parents=True, exist_ok=True)
    work = Path(work_root) / subject
    work.mkdir(parents=True, exist_ok=True)
    crops_dir = Path(crops_root or work_root) / subject
    crops_dir.mkdir(parents=True, exist_ok=True)
    (out / "meta.json").write_text(json.dumps({**rec.meta, "subject": subject}))
    shutil.copy(source_folder / "ground_truth.txt", out / "ground_truth.txt")

    log = []
    for cond in conditions:
        tr_path = out / f"{cond.name}.npz"
        wants_crop = bool(crop_size) and (crop_conditions is None or cond.name in crop_conditions)
        if tr_path.exists() and (not wants_crop or (crops_dir / f"{cond.name}_crops.npy").exists()
                                 or (out / f"{cond.name}_nn.npz").exists()):
            continue
        if cond.name == "lossless_rgb":
            video, kbps, secs = rec.video_path, None, 0.0  # verified bit-identical in step6
        else:
            res = encode(rec.video_path, work, cond)
            video, kbps, secs = res.path, res.achieved_kbps, res.seconds
        tr = extract_traces(video, crop_size=crop_size if wants_crop else None)
        tr.save(tr_path)
        if wants_crop and tr.crops is not None:
            np.save(crops_dir / f"{cond.name}_crops.npy", tr.crops)
        if video != rec.video_path:
            Path(video).unlink(missing_ok=True)
        log.append({"condition": cond.name, "achieved_kbps": kbps, "encode_s": secs,
                    "detect_rate": tr.detect_rate})
    if log:
        prev = json.loads((out / "encode_log.json").read_text()) if (out / "encode_log.json").exists() else []
        (out / "encode_log.json").write_text(json.dumps(prev + log, indent=1))
    if delete_source:
        rec.video_path.unlink(missing_ok=True)
    return out


def masked_single(seg: np.ndarray, art: np.ndarray, fs: float, mode: str, k: float = DEFAULT_MASK_K) -> float:
    """One method with the artifact mask and no fusion (ablation)."""
    from .spectral import HR_BAND, band_mask, correct_harmonic_lock, peak_frequency, spectrum

    f, pa = spectrum(art, fs, pad_factor=4)
    _, p = spectrum(seg, fs, pad_factor=4)
    if mode == "wiener":
        pm = p * p / (p + pa + 1e-30)
    else:
        m = band_mask(f, HR_BAND)
        pm = p * (1 - np.clip(pa / max(float(pa[m].max()), 1e-30), 0, 1)) ** k
    pk = peak_frequency(f, pm)
    pk, _ = correct_harmonic_lock(f, pm, pk)
    return pk * 60.0


def evaluate_subject(
    subject_folder: Path,
    conditions: list[Condition] | None = None,
    params: dict | None = None,
    nn_models: tuple[str, ...] = (),
) -> list[dict]:
    """Tidy rows for one subject across all conditions and methods.

    Methods: green, ICA, CHROM, POS; TRACE v1, v2 and (if frozen) v3; POS
    with each artifact mask but no fusion; neural baselines if present.
    "trace" repeats whichever version `params["primary"]` names, so every
    figure can refer to one TRACE while the ablation keeps all of them.
    """
    params = params or {}
    gamma2, k2 = float(params.get("gamma", DEFAULT_GAMMA)), float(params.get("mask_k", DEFAULT_MASK_K))
    conf2 = float(params.get("confidence", DEFAULT_CONFIDENCE))
    v1_gamma = float(params.get("v1_gamma", 4.0))
    v3 = params.get("v3")
    primary = params.get("primary", "trace_v2")
    conditions = conditions or grid_conditions()
    folder = Path(subject_folder)
    rec: Recording = load_recording(folder)
    meta = rec.meta
    rows = []
    for cond in conditions:
        path = folder / f"{cond.name}.npz"
        if not path.exists():
            continue
        tr = Traces.load(path)
        ws = sliding_windows(min(rec.duration_s, tr.t[-1]))
        ref = reference_hr(rec, ws)
        pulses = band_limited_pulses(tr.rgb, tr.fps, names=tuple(METHODS))
        art = artifact_reference(tr.rgb, tr.fps)
        nn = {}
        nn_path = folder / f"{cond.name}_nn.npz"
        if nn_models and nn_path.exists():
            z = np.load(nn_path)
            from .preprocess import clean_pulse
            for m in nn_models:
                if m in z:
                    nn[m] = clean_pulse(z[m][: len(tr.t)], tr.fps)
        base = {"subject": meta.get("subject", folder.name), "fitzpatrick": rec.fitzpatrick,
                "source": meta.get("source", "real"), "condition": cond.name, "codec": cond.codec,
                "kbps": cond.kbps if cond.kbps is not None else np.nan, "pix_fmt": cond.pix_fmt,
                "lossless": cond.lossless, "detect_rate": tr.detect_rate}
        for wi, ((a, b), r) in enumerate(zip(ws, ref)):
            sl = window_slice(tr.t, a, b)
            for name, p in pulses.items():
                e = estimate_bpm(p[sl], tr.fps)
                rows.append({**base, "window": wi, "method": name, "ref_bpm": r, "est_bpm": e.bpm,
                             "quality": e.quality})
            segs = {n: pulses[n][sl] for n in ("green", "chrom", "pos")}
            fused = {
                "trace_v1": fuse(segs, tr.fps, v1_gamma, conf2),
                "trace_v2": fuse(segs, tr.fps, gamma2, conf2, artifact=art[sl], mask_k=k2),
            }
            if v3:
                fused["trace_v3"] = fuse(segs, tr.fps, float(v3["gamma"]), float(v3["confidence"]),
                                         artifact=art[sl], mask_mode="wiener")
            fused["trace"] = fused.get(primary, fused["trace_v2"])
            for name, fr in fused.items():
                rows.append({**base, "window": wi, "method": name, "ref_bpm": r, "est_bpm": fr.bpm,
                             "quality": fr.quality, "confident": fr.confident,
                             **{f"w_{k}": v for k, v in fr.weights.items()}})
            for mode, label in (("power", "pos_mask"), ("wiener", "pos_wiener")):
                rows.append({**base, "window": wi, "method": label, "ref_bpm": r,
                             "est_bpm": masked_single(pulses["pos"][sl], art[sl], tr.fps, mode, k2), "quality": np.nan})
            for name, p in nn.items():
                seg = p[sl]
                if len(seg) < 32:
                    continue
                e = estimate_bpm(seg, tr.fps)
                rows.append({**base, "window": wi, "method": name, "ref_bpm": r, "est_bpm": e.bpm,
                             "quality": e.quality})
    return rows
