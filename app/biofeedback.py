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
        self.measurements = deque(maxlen=7)
        self.last_measurement_t = None
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
        measurement_t = state.get("t")
        fresh = valid and measurement_t != self.last_measurement_t
        if fresh:
            sample_dt = min(max(float(measurement_t) - self.last_measurement_t, 0), 1) \
                if self.last_measurement_t is not None else 0
            self.last_measurement_t = float(measurement_t)
            self.measurements.append(float(bpm))
            stable = float(np.median(self.measurements))
            if self.filtered is None:
                if len(self.measurements) >= 3:
                    self.filtered = stable
            else:
                # Median rejection removes one-window peak swaps. The slew
                # limit still allows a real response to appear within seconds.
                step = max(0.5, 6.0 * sample_dt)
                target_bpm = float(np.clip(stable, self.filtered - step, self.filtered + step))
                self.filtered += (1 - math.exp(-sample_dt / 1.8)) * (target_bpm - self.filtered)
            if self.filtered is not None and self.baseline is None:
                self.samples.append(stable)
                if self.previous_valid:
                    self.valid_seconds += sample_dt
                if self.valid_seconds >= 8:
                    self.baseline = float(np.median(self.samples))
            if self.filtered is not None:
                self.history.append((now, self.filtered))
        self.previous_valid = bool(valid)
        target = float(np.clip((self.filtered - self.baseline) / 25, 0, 1)) if valid and self.baseline else 0.0
        self.intensity += (1 - math.exp(-dt / 6)) * (target - self.intensity)
        trend = 0.0
        if valid and len(self.history) > 3 and self.history[-1][0] - self.history[0][0] > 3:
            trend = (self.history[-1][1] - self.history[0][1]) / (self.history[-1][0] - self.history[0][0]) * 10
        return {"valid": bool(valid), "reason": reason if not valid else "Pulse linked",
                "baseline": round(self.baseline, 1) if self.baseline else None,
                "bpm": round(self.filtered, 1) if valid and self.filtered is not None else None,
                "calibration": min(1, self.valid_seconds / 8),
                "intensity": round(self.intensity, 4), "trend": round(trend, 1),
                "delta": round(self.filtered - self.baseline, 1) if valid and self.baseline else None}


def demo_state(elapsed: float, scenario: str = "cycle") -> dict:
    """Explicit synthetic signal, analysed with the real FFT estimator."""
    if elapsed < 8:
        target = 72.0
    elif scenario == "steady":
        target = 72.0
    elif scenario == "elevated":
        target = 108.0
    elif scenario == "scare":
        target = 112.0 - 18.0 * abs(math.sin(elapsed * 2.5))
    elif scenario == "dropout":
        target = 72.0
    else:
        # A deliberately visible demo rhythm: calm, alarm, recovery.
        cycle = elapsed % 28
        target = 72.0 if cycle < 8 else (112.0 if cycle < 15 else 82.0)
    t = np.arange(600) / 30
    pulse = np.sin(2 * np.pi * target / 60 * t) + .2 * np.sin(4 * np.pi * target / 60 * t)
    est = estimate_bpm(pulse, 30)
    return {"running": True, "source": "demo", "t": elapsed, "bpm": round(est.bpm, 1),
            "quality": est.quality, "confident": scenario != "dropout",
            "checks": {"face": True, "light": True, "still": True},
            "methods": {"green": {"bpm": round(est.bpm + 1.2, 1), "quality": .78},
                        "chrom": {"bpm": round(est.bpm - .7, 1), "quality": .71},
                        "pos": {"bpm": round(est.bpm, 1), "quality": .86}},
            "method_traces": {"green": (pulse + .08 * np.sin(2 * np.pi * .3 * t))[-180:].tolist(),
                              "chrom": (pulse * .86 + .12 * np.sin(2 * np.pi * target / 30 * t))[-180:].tolist(),
                              "pos": pulse[-180:].tolist()},
            "trace": {"pulse": pulse[-180:].tolist()},
            "bcg": {"usable": False, "reason": "Synthetic mode has no camera motion channel"}}
