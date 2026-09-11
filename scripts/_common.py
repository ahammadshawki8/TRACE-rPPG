"""Shared helpers for the stepN acceptance scripts: the check/rule/summary
pattern from step1, plus a cache so simulated clips are rendered once."""

from __future__ import annotations

import hashlib
import json
import sys
from dataclasses import asdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from tracerppg.simulate import SimConfig, simulate_recording  # noqa: E402

CACHE = ROOT / "data" / "cache"
results: list[tuple[str, bool, str]] = []


def check(name: str, passed: bool, detail: str = "") -> None:
    results.append((name, bool(passed), detail))
    print(f"  [{'PASS' if passed else 'FAIL'}] {name}" + (f"  --  {detail}" if detail else ""))


def rule(title: str) -> None:
    print(f"\n{title}\n" + "-" * len(title))


def finish() -> None:
    print("\n" + "=" * 62)
    passed = sum(1 for _, ok, _ in results if ok)
    print(f"  {passed}/{len(results)} checks passed")
    for name, ok, detail in results:
        if not ok:
            print(f"    FAILED: {name}: {detail}")
    print("=" * 62)
    sys.exit(0 if passed == len(results) else 1)


def sim_key(cfg: SimConfig) -> str:
    return hashlib.sha1(json.dumps(asdict(cfg), sort_keys=True).encode()).hexdigest()[:12]


def sim_folder(cfg: SimConfig, need_video: bool = True) -> Path:
    """Render a simulated subject once, keyed by its full configuration.

    Lossless noisy video costs about 12 MB per second, so cohort videos are
    deleted once their traces are cached; they re-render on demand
    (deterministically, from the same seed) if a later step needs pixels.
    """
    folder = CACHE / f"sim_{sim_key(cfg)}"
    if not (folder / "meta.json").exists() or (need_video and not (folder / "vid.mkv").exists()):
        simulate_recording(folder, cfg)
    return folder


def sim_traces(cfg: SimConfig, keep_video: bool = False):
    """(recording, traces) for a simulated subject; traces cached, video dropped."""
    from tracerppg.datasets import load_recording
    from tracerppg.roi import Traces, extract_traces

    folder = CACHE / f"sim_{sim_key(cfg)}"
    cache = folder / "traces.npz"
    if cache.exists() and (folder / "meta.json").exists():
        return load_recording(folder), Traces.load(cache)
    folder = sim_folder(cfg)
    rec = load_recording(folder)
    tr = extract_traces(rec.video_path)
    tr.save(cache)
    if not keep_video:
        rec.video_path.unlink(missing_ok=True)
    return rec, tr


def cohort(n_per_type: int = 4, duration_s: float = 40.0, seed0: int = 1000, **kw) -> list[SimConfig]:
    """A balanced simulated cohort: n subjects of each Fitzpatrick type, with
    heart rates and motion drawn from the same distribution for every type."""
    import numpy as np

    rng = np.random.default_rng(seed0)
    cfgs = []
    for fz in range(1, 7):
        for j in range(n_per_type):
            cfgs.append(SimConfig(fitzpatrick=fz, duration_s=duration_s,
                                  mean_bpm=float(rng.uniform(58, 98)),
                                  seed=seed0 + 100 * fz + j, **kw))
    return cfgs
