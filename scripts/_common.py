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


def sim_folder(cfg: SimConfig) -> Path:
    """Render a simulated subject once, keyed by its full configuration."""
    key = hashlib.sha1(json.dumps(asdict(cfg), sort_keys=True).encode()).hexdigest()[:12]
    folder = CACHE / f"sim_{key}"
    if not (folder / "meta.json").exists():
        simulate_recording(folder, cfg)
    return folder
