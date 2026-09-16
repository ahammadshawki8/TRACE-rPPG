"""T12 acceptance: conservative rPPG-guided camera rBCG.

This checks the spectral decision layer with known mechanical signals. It does
not claim that a webcam can recover cardiac head motion from every person.

Run:  .venv/Scripts/python.exe scripts/step9_camera_bcg.py
"""

from __future__ import annotations

from collections import deque

import numpy as np

from _common import check, finish, rule
from tracerppg.mechanical import CameraBCG


def detector_with_motion(*components: tuple[float, float]) -> CameraBCG:
    """Build 20 seconds of sub-pixel vertical motion: (BPM, amplitude)."""
    t = np.arange(0, 20, 1 / 30)
    position = sum(a * np.sin(2 * np.pi * bpm / 60 * t) for bpm, a in components)
    detector = CameraBCG()
    detector.samples = deque(zip(t, position), maxlen=900)
    return detector


if __name__ == "__main__":
    rule("1. BCG waits for optical guidance")
    bcg = detector_with_motion((65, 0.12))
    no_reference = bcg.result()
    check("no standalone BPM is published", "bpm" not in no_reference,
          no_reference["reason"])

    rule("2. Agreement must persist before a lock")
    first = bcg.result(65)
    second = bcg.result(65)
    third = bcg.result(65)
    check("one window is not enough", not first["usable"] and "bpm" not in first)
    check("two windows are not enough", not second["usable"] and "bpm" not in second)
    check("three agreeing windows lock near 65 BPM",
          third["usable"] and abs(third["bpm"] - 65) < 1,
          f"reported {third.get('bpm')} BPM")

    rule("3. Competing motion does not pull the guided estimate")
    mixed = detector_with_motion((65, 0.12), (80, 0.13))
    mixed_result = None
    for _ in range(3):
        mixed_result = mixed.result(65)
    check("65 BPM survives a slightly stronger 80 BPM motion component",
          mixed_result["usable"] and abs(mixed_result["bpm"] - 65) < 1,
          f"reported {mixed_result.get('bpm')} BPM")

    rule("4. Unrelated motion is refused")
    wrong = detector_with_motion((80, 0.15))
    wrong_results = [wrong.result(65) for _ in range(5)]
    check("pure 80 BPM motion is not relabelled as a 65 BPM BCG",
          all(not result["usable"] and "bpm" not in result for result in wrong_results),
          f"quality {wrong_results[-1].get('quality')}, peak ratio "
          f"{wrong_results[-1].get('peak_ratio')}")

    finish()
