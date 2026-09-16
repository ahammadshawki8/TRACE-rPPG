"""Live analysis engine for the demo app (T10).

One background thread reads frames from a source (webcam, the simulator, or
a video file) at the source's real frame rate, tracks the face, averages the
skin, and every half second runs the same pipeline the experiments use:
green, CHROM and POS, the pulse-blind artifact reference, TRACE v2 fusion
with the frozen parameters, and the confidence gate. Frames never leave the
machine; the browser receives only a small preview image and numbers.
"""

from __future__ import annotations

import json
import threading
import time
from collections import deque
from dataclasses import asdict
from pathlib import Path

import cv2
import numpy as np

from tracerppg.datasets import resample_uniform
from tracerppg.fusion import artifact_reference, band_limited_pulses, fuse
from tracerppg.hrv import DISCLAIMER, HRV_METHOD, MIN_HRV_SECONDS, clean_rr, hrv_from_pulse
from tracerppg.roi import REGIONS, FaceTracker, skin_mean
from tracerppg.spectral import HR_BAND, estimate_bpm
from tracerppg.mechanical import CameraBCG

ROOT = Path(__file__).resolve().parents[1]
FS = 30.0
WINDOW_S = 20.0      # analysis window, the same length the grid evaluates
MIN_S = 8.0          # first reading after this much signal (resolution 7.5 BPM before interpolation)
ANALYSE_EVERY = 0.5  # seconds between read-outs


def fusion_params() -> dict:
    p = ROOT / "results" / "fusion_params.json"
    if p.exists():
        return json.loads(p.read_text())
    return {"gamma": 2.0, "mask_k": 4.0, "confidence": 0.35}


# --------------------------------------------------------------------- sources

class WebcamSource:
    def __init__(self, index: int = 0):
        self.cap = cv2.VideoCapture(index, cv2.CAP_DSHOW) if hasattr(cv2, "CAP_DSHOW") else cv2.VideoCapture(index)
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        self.cap.set(cv2.CAP_PROP_FPS, 30)
        if not self.cap.isOpened():
            raise RuntimeError("No camera found. Connect a webcam or choose a recorded volunteer.")
        self.t0 = time.monotonic()

    def __iter__(self):
        while True:
            ok, bgr = self.cap.read()
            if not ok:
                break
            yield cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB), time.monotonic() - self.t0

    def close(self):
        self.cap.release()


class SimSource:
    """A simulated volunteer rendered live, paced at 30 fps."""

    def __init__(self, fitzpatrick: int = 2, motion: float = 0.3, duration_s: float = 600.0, seed: int = 11,
                 mean_bpm: float = 72.0):
        from tracerppg.simulate import SimConfig, render

        self.cfg = SimConfig(fitzpatrick=fitzpatrick, motion=motion, duration_s=duration_s, seed=seed,
                             mean_bpm=mean_bpm)
        self.frames, self.rhythm, _, _ = render(self.cfg)

    def true_bpm(self, t: float, span: float = WINDOW_S) -> float | None:
        b = self.rhythm.beat_times
        m = (b > t - span) & (b <= t)
        return float(60.0 / np.mean(np.diff(b[m]))) if m.sum() > 2 else None

    def __iter__(self):
        start = time.monotonic()
        for frame, t in self.frames:
            lag = t - (time.monotonic() - start)
            if lag > 0:
                time.sleep(lag)
            yield frame, float(t)

    def close(self):
        pass


class FileSource:
    def __init__(self, path: str, beat_times=None):
        from tracerppg.video import frames, probe

        self.info = probe(Path(path))
        self.it = frames(Path(path), self.info)
        self.beats = np.asarray(beat_times) if beat_times is not None else None

    def true_bpm(self, t: float, span: float = WINDOW_S) -> float | None:
        if self.beats is None:
            return None
        m = (self.beats > t - span) & (self.beats <= t)
        return float(60.0 / np.mean(np.diff(self.beats[m]))) if m.sum() > 2 else None

    def __iter__(self):
        start = time.monotonic()
        for i, frame in enumerate(self.it):
            t = i / self.info.fps
            lag = t - (time.monotonic() - start)
            if lag > 0:
                time.sleep(lag)
            yield np.ascontiguousarray(frame), t

    def close(self):
        pass


# ---------------------------------------------------------------------- engine

class LiveEngine:
    def __init__(self):
        self.lock = threading.Lock()
        self.thread: threading.Thread | None = None
        self.stop_flag = threading.Event()
        self.source = None
        self.source_name = None
        self.error: str | None = None
        self.params = fusion_params()
        self.reset()

    def reset(self):
        self.t = deque()
        self.rgb = deque()
        self.centres = deque()
        self.jpeg: bytes | None = None
        self.state: dict = {"running": False}
        self.hrv_start: float | None = None
        self.hrv_result: dict | None = None
        self.window_s = WINDOW_S

    # ------------------------------------------------------------ control
    def start(self, source: str = "sim", **kw):
        self.stop()
        self.reset()
        self.error = None
        self.window_s = float(kw.get("game_window", WINDOW_S))
        self.window_s = min(30.0, max(8.0, self.window_s))
        try:
            if source == "webcam":
                self.source = WebcamSource(int(kw.get("index", 0)))
            elif source == "file":
                self.source = FileSource(kw["path"])
            else:
                fz = int(kw.get("fitzpatrick", 2))
                restless = float(kw.get("motion", 0.3)) > 1.0
                clip = ROOT / "data" / "replay" / f"type{fz}_{'restless' if restless else 'calm'}"
                if clip.with_suffix(".mkv").exists():
                    # Pre-rendered volunteer: decoding is cheap, rendering is not.
                    meta = json.loads(clip.with_suffix(".json").read_text())
                    self.source = FileSource(str(clip.with_suffix(".mkv")), meta["beat_times"])
                    self.source.fitzpatrick = fz
                else:
                    self.source = SimSource(fz, float(kw.get("motion", 0.3)))
        except Exception as exc:  # surfaced to the UI as a plain message
            self.error = str(exc)
            self.state = {"running": False, "error": self.error}
            return
        self.source_name = source
        self.stop_flag.clear()
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    def stop(self):
        self.stop_flag.set()
        if self.thread is not None:
            self.thread.join(timeout=3)
        if self.source is not None:
            self.source.close()
        self.thread = None
        self.source = None

    def hrv_begin(self):
        with self.lock:
            self.hrv_start = self.t[-1] if self.t else 0.0
            self.hrv_result = None

    def hrv_finish(self) -> dict:
        """Compute HRV over everything recorded since `hrv_begin`."""
        with self.lock:
            if self.hrv_start is None or not self.t:
                return {"error": "Start a heart-rhythm reading first."}
            t = np.array(self.t)
            rgb = np.array(self.rgb)
        m = t >= self.hrv_start
        t, rgb = t[m], rgb[m]
        span = float(t[-1] - t[0]) if len(t) > 1 else 0.0
        if span < 30:
            return {"error": "Too short. Record at least two minutes for LF/HF."}
        tu, cols = self._uniform(t, rgb)
        pulses = band_limited_pulses(cols, FS)
        name = HRV_METHOD
        h, beats = hrv_from_pulse(pulses[name], FS)
        rr_t, rr = clean_rr(beats)  # plot the cleaned intervals the statistics use
        out = {"seconds": span, "method": name, "mean_hr": h.mean_hr, "sdnn": h.sdnn_ms, "rmssd": h.rmssd_ms,
               "pnn50": h.pnn50, "lf": h.lf_ms2, "hf": h.hf_ms2, "lf_hf": h.lf_hf,
               "resp_bpm": h.resp_hz * 60 if h.resp_hz else None, "valid": h.valid_frequency,
               "indicator": h.indicator(), "disclaimer": DISCLAIMER,
               "rr_t": [round(float(x), 3) for x in rr_t], "rr_ms": [round(float(x) * 1000, 1) for x in rr]}
        if h.freqs is not None:
            keep = h.freqs <= 0.5
            out["psd_f"] = [round(float(x), 4) for x in h.freqs[keep]]
            out["psd_p"] = [round(float(x), 3) for x in h.psd[keep]]
        self.hrv_result = out
        return out

    # ------------------------------------------------------------ worker
    def _run(self):
        tracker = FaceTracker()
        mechanical = CameraBCG()
        last = 0.0
        try:
            for i, (frame, t) in enumerate(self.source):
                if self.stop_flag.is_set():
                    break
                box, _ = tracker.update(frame)
                if self.source_name == "webcam":
                    mechanical.update(frame, box, t)
                if box is not None:
                    mean, npx = skin_mean(frame, box)
                    centre = box[:2] + box[2:] / 2
                else:
                    mean, npx, centre = None, 0, None
                with self.lock:
                    if mean is not None and npx > 200:
                        self.t.append(t)
                        self.rgb.append(mean)
                        self.centres.append((t, *centre))
                    while self.t and self.t[0] < t - max(self.window_s, 330.0):
                        self.t.popleft()
                        self.rgb.popleft()
                    while self.centres and self.centres[0][0] < t - 3.0:
                        self.centres.popleft()
                if i % 2 == 0:
                    self.jpeg = self._preview(frame, box)
                if t - last >= ANALYSE_EVERY:
                    last = t
                    self._analyse(t, box, npx, frame if box is not None else None)
                    reference_bpm = self.state.get("bpm") if self.state.get("confident") else None
                    self.state["bcg"] = mechanical.result(reference_bpm) if self.source_name == "webcam" else {
                        "usable": False, "reason": "Replay has no validated cardiac head motion", "experimental": True}
        except Exception as exc:
            self.error = f"The video source stopped: {exc}"
        finally:
            self.state = {**self.state, "running": False, "error": self.error}

    @staticmethod
    def _uniform(t: np.ndarray, rgb: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        cols = []
        tu = None
        for c in range(3):
            tu, x = resample_uniform(t, rgb[:, c], FS)
            cols.append(x)
        return tu, np.column_stack(cols)

    def _preview(self, frame: np.ndarray, box) -> bytes:
        img = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
        if box is not None:
            x, y, w, h = box
            cv2.rectangle(img, (int(x), int(y)), (int(x + w), int(y + h)), (63, 27, 176), 2)
            for fx0, fy0, fx1, fy1 in REGIONS.values():
                cv2.rectangle(img, (int(x + fx0 * w), int(y + fy0 * h)), (int(x + fx1 * w), int(y + fy1 * h)),
                              (107, 121, 16), 1)
        img = cv2.resize(img, (480, 360), interpolation=cv2.INTER_AREA)
        ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 80])
        return buf.tobytes() if ok else b""

    def _analyse(self, now: float, box, npx: int, frame):
        with self.lock:
            t = np.array(self.t)
            rgb = np.array(self.rgb)
            cen = np.array([c[1:] for c in self.centres]) if self.centres else np.zeros((0, 2))
        # Setup checks, in plain terms.
        face = box is not None and npx > 200
        if face and len(rgb):
            lum = float(np.dot(rgb[-1], [0.299, 0.587, 0.114]))
            light = 45.0 <= lum <= 235.0
        else:
            lum, light = 0.0, False
        motion = float(np.max(np.std(cen, axis=0))) if len(cen) > 10 else 0.0
        still = motion < 3.0
        buffered = float(t[-1] - t[0]) if len(t) > 1 else 0.0
        state = {"running": True, "source": self.source_name, "t": now, "buffered_s": round(buffered, 1),
                 "needed_s": MIN_S, "checks": {"face": face, "light": light, "still": still},
                 "luminance": round(lum, 1), "motion_px": round(motion, 2), "error": self.error,
                 "params": {k: self.params.get(k) for k in ("gamma", "mask_k", "confidence")}}
        if isinstance(self.source, SimSource):
            state["true_bpm"] = self.source.true_bpm(now)
            state["fitzpatrick"] = self.source.cfg.fitzpatrick
        elif isinstance(self.source, FileSource) and self.source.beats is not None:
            state["true_bpm"] = self.source.true_bpm(now)
            state["fitzpatrick"] = getattr(self.source, "fitzpatrick", None)
        if self.hrv_start is not None:
            state["hrv_elapsed"] = round(now - self.hrv_start, 1)
            state["hrv_needed"] = MIN_HRV_SECONDS

        recent = t >= now - self.window_s
        if (buffered >= MIN_S and recent.sum() > FS * MIN_S and now - t[-1] < .5
                and np.max(np.diff(t[recent])) < .5):
            m = t >= now - self.window_s
            tu, cols = self._uniform(t[m], rgb[m])
            pulses = band_limited_pulses(cols, FS)
            art = artifact_reference(cols, FS)
            fr = fuse(pulses, FS, float(self.params["gamma"]), float(self.params["confidence"]),
                      artifact=art, mask_k=float(self.params.get("mask_k", 4.0)))
            band = (fr.freqs >= 0.6) & (fr.freqs <= HR_BAND[1])
            fp = fr.fused_power[band]
            fp = fp / fp.max() if fp.max() > 0 else fp
            best = max(fr.weights, key=fr.weights.get)
            show = slice(-min(len(tu), int(10 * FS)), None)
            green_raw = cols[:, 1] / np.mean(cols[:, 1]) - 1.0
            state.update({
                "bpm": round(fr.bpm, 1), "quality": round(fr.quality, 3), "confident": bool(fr.confident),
                "weights": {k: round(v, 3) for k, v in fr.weights.items()},
                "methods": {k: {"bpm": round(v.bpm, 1), "quality": round(v.quality, 3)}
                            for k, v in fr.per_method.items()},
                "method_traces": {k: _thin(pulses[k][show] / (np.std(pulses[k][show]) + 1e-12))
                                  for k in ("green", "chrom", "pos")},
                "naive_green": round(estimate_bpm(pulses["green"], FS).bpm, 1),
                "trace": {"raw": _thin(green_raw[show]), "pulse": _thin(pulses[best][show] / (np.std(pulses[best][show]) + 1e-12)),
                          "best": best},
                "spectrum": {"f": _thin(fr.freqs[band] * 60, 240), "p": _thin(fp, 240), "peak": round(fr.bpm, 1)},
            })
        self.state = state


def _thin(x: np.ndarray, n: int = 300) -> list[float]:
    x = np.asarray(x, float)
    if len(x) > n:
        x = x[np.linspace(0, len(x) - 1, n).astype(int)]
    return [round(float(v), 4) for v in x]
