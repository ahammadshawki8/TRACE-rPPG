"""Conservative, session-local pulse feedback for an interactive research demo."""
from __future__ import annotations

import math
from collections import deque

import numpy as np

from tracerppg.spectral import estimate_bpm


class PulseController:
    """Calibrate only on fresh usable samples; missing data returns to neutral."""

    def __init__(self):
        self.reset()

    def reset(self):
        self.baseline = None
        self.samples = []
        self.valid_seconds = 0.0
        self.last_t = None
        self.previous_valid = False
        self.filtered = None
        self.intensity = 0.0
        self.history = deque(maxlen=40)

    def update(self, state: dict, now: float) -> dict:
        dt = min(max(now - self.last_t, 0), 1) if self.last_t is not None else 0
        self.last_t = now
        bpm = state.get("bpm")
        valid = (state.get("running", False) and state.get("confident", False)
                 and all(state.get("checks", {}).get(k, False) for k in ("face", "light", "still"))
                 and isinstance(bpm, (int, float)) and math.isfinite(bpm) and 42 <= bpm <= 200)
        reason = "Measuring"
        if not state.get("running"):
            reason = state.get("error") or "Source disconnected"
        elif not all(state.get("checks", {}).values()):
            reason = "Improve lighting and hold your face steady"
        elif not valid:
            reason = "Waiting for a stable pulse"
        bcg = state.get("bcg", {})
        if valid and bcg.get("usable") and abs(bcg["bpm"] - bpm) > 12:
            valid, reason = False, "Optical and motion estimates disagree"
        if valid:
            self.filtered = bpm if self.filtered is None else self.filtered + (1 - math.exp(-dt / 4)) * (bpm - self.filtered)
            if self.baseline is None:
                self.samples.append(bpm)
                if self.previous_valid:
                    self.valid_seconds += dt
                if self.valid_seconds >= 12:
                    self.baseline = float(np.median(self.samples))
            self.history.append((now, self.filtered))
        self.previous_valid = bool(valid)
        target = float(np.clip((self.filtered - self.baseline) / 25, 0, 1)) if valid and self.baseline else 0.0
        self.intensity += (1 - math.exp(-dt / 6)) * (target - self.intensity)
        trend = 0.0
        if valid and len(self.history) > 3 and self.history[-1][0] - self.history[0][0] > 3:
            trend = (self.history[-1][1] - self.history[0][1]) / (self.history[-1][0] - self.history[0][0]) * 10
        return {"valid": bool(valid), "reason": reason if not valid else "Pulse linked",
                "baseline": round(self.baseline, 1) if self.baseline else None,
                "bpm": round(self.filtered, 1) if valid else None,
                "calibration": min(1, self.valid_seconds / 12),
                "intensity": round(self.intensity, 4), "trend": round(trend, 1),
                "delta": round(self.filtered - self.baseline, 1) if valid and self.baseline else None}


def demo_state(elapsed: float, scenario: str = "cycle") -> dict:
    """Explicit synthetic signal, analysed with the real FFT estimator."""
    target = {"steady": 72, "elevated": 100}.get(scenario, 72 + 26 * max(0, math.sin((elapsed - 18) / 22)))
    t = np.arange(600) / 30
    pulse = np.sin(2 * np.pi * target / 60 * t) + .2 * np.sin(4 * np.pi * target / 60 * t)
    est = estimate_bpm(pulse, 30)
    return {"running": True, "source": "demo", "t": elapsed, "bpm": round(est.bpm, 1),
            "quality": est.quality, "confident": scenario != "dropout",
            "checks": {"face": True, "light": True, "still": True},
            "trace": {"pulse": pulse[-180:].tolist()}, "bcg": {"usable": False, "reason": "Synthetic optical signal only"}}
