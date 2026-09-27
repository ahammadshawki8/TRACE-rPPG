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
from tracerppg.fusion import artifact_reference, band_limited_pulses, fuse, p_correct, weights_from_quality
from tracerppg.hrv import DISCLAIMER, HRV_METHOD, MIN_HRV_SECONDS, clean_rr, hrv_from_pulse
from tracerppg.roi import REGIONS, FaceTracker, skin_mean
from tracerppg.spectral import HR_BAND, estimate_bpm
from tracerppg.preprocess import default_detrend_window, detrend

ROOT = Path(__file__).resolve().parents[1]
FS = 30.0
WINDOW_S = 20.0      # analysis window, the same length the grid evaluates
MIN_S = 8.0          # first reading after this much signal (resolution 7.5 BPM before interpolation)
ANALYSE_EVERY = 0.5  # seconds between read-outs
# Liveness: over the last 10 s of read-outs (20 at 2 per second), how often
# was a pulse found (see pulse_found)? A photo, a screen or a mask has no blood-volume pulse, so neither
# holds for long. A rule on existing outputs, nothing learned.
LIVENESS_READOUTS = 20
LIVE_SHARE, NONE_SHARE = 0.7, 0.2
# Per-method quality needed for a vote, chosen by scripts/tune_liveness.py on
# development volunteers (living and photo) so that no photo was accepted.
_lp = ROOT / "results" / "liveness_params.json"
LIVENESS_Q = json.loads(_lp.read_text())["min_quality"] if _lp.exists() else 0.15


def fusion_params() -> dict:
    """TRACE v3 (per-window selection, tuned and tested on separate simulated
    cohorts) when present, else the frozen v2 blend."""
    from tracerppg.simeval import frozen_params

    return frozen_params()


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

    def info(self) -> dict:
        g = self.cap.get
        return {"width": g(cv2.CAP_PROP_FRAME_WIDTH), "height": g(cv2.CAP_PROP_FRAME_HEIGHT), "fps": g(cv2.CAP_PROP_FPS),
                "auto_exposure": g(cv2.CAP_PROP_AUTO_EXPOSURE), "exposure": g(cv2.CAP_PROP_EXPOSURE),
                "auto_wb": g(cv2.CAP_PROP_AUTO_WB), "backend": self.cap.getBackendName()}

    def close(self):
        self.cap.release()


class SimSource:
    """A simulated volunteer rendered live at 30 fps, whose skin type, heart
    rate, motion and lighting can be changed while it runs (`set`).

    Timestamps are simulation time, so if rendering ever falls behind the
    wall clock the pipeline still sees a correct, uniform 30 fps signal.
    """

    def __init__(self, **params):
        from tracerppg.simulate import LiveParams, LiveSimulator

        self.sim = LiveSimulator(LiveParams(), seed=int(params.pop("seed", 11)))
        self.sim.set(**params)

    @property
    def params(self) -> dict:
        return asdict(self.sim.p)

    def set(self, **kw) -> dict:
        self.sim.set(**kw)
        return self.params

    def true_bpm(self, t: float, span: float = WINDOW_S) -> float | None:
        return self.sim.true_bpm(t, span)

    def __iter__(self):
        start = time.monotonic()
        while True:
            frame, t = self.sim.next_frame()
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
        self.recorder = None
        self.last_recording: dict | None = None
        self.rec_lock = threading.Lock()
        self.reset()

    def reset(self):
        self.t = deque()
        self.rgb = deque()
        self.centres = deque()
        self.jpeg: bytes | None = None
        self.state: dict = {"running": False}
        self.hrv_start: float | None = None
        self.hrv_result: dict | None = None
        self.live_hist: deque = deque(maxlen=LIVENESS_READOUTS)
        self.window_s = WINDOW_S

    # ------------------------------------------------------------ control
    def start(self, source: str = "sim", **kw):
        self.stop()
        self.reset()
        self.error = None
        try:
            if source == "webcam":
                self.source = WebcamSource(int(kw.get("index", 0)))
            elif source == "file":
                self.source = FileSource(kw["path"])
            else:
                self.source = SimSource(**kw)
        except Exception as exc:  # surfaced to the UI as a plain message
            self.error = str(exc)
            self.state = {"running": False, "error": self.error}
            return
        self.source_name = source
        self.stop_flag.clear()
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    def stop(self):
        if self.recorder is not None:
            self.rec_stop(save=True)
        self.stop_flag.set()
        self.jpeg = None  # the preview must go dark, not freeze on the last frame
        if self.thread is not None:
            self.thread.join(timeout=3)
        if self.source is not None:
            self.source.close()
        self.thread = None
        self.source = None

    def set_sim(self, **kw) -> dict | None:
        """Change the simulated volunteer while it runs."""
        src = self.source
        return src.set(**kw) if isinstance(src, SimSource) else None

    # ------------------------------------------------------------ recording
    def rec_start(self, volunteer: str, condition: dict, duration: float = 60.0, watch: str = "",
                  keep_video: bool = False) -> dict:
        import collect

        if self.source_name != "webcam" or self.thread is None:
            return {"error": "Start the webcam first. Recordings are of real volunteers only."}
        info = self.source.info() if hasattr(self.source, "info") else {}
        try:
            rec = collect.Recorder(volunteer, condition or {}, duration, watch, keep_video, info)
        except ValueError as exc:
            return {"error": str(exc)}
        with self.rec_lock:
            self.recorder, self.last_recording = rec, None
        return {"ok": True, "clip": rec.clip}

    def rec_watch(self, bpm: float) -> dict:
        rec = self.recorder
        if rec is None or not (30 <= bpm <= 220):
            return {"error": "No recording running, or the value is not a heart rate."}
        return rec.watch_reading(bpm)

    def rec_stop(self, save: bool = True) -> dict | None:
        with self.rec_lock:
            rec, self.recorder = self.recorder, None
        if rec is None:
            return None
        if not save:
            rec.finish(False)
            import collect
            collect.delete_clip(rec.volunteer, rec.clip)
            self.last_recording = {"discarded": True}
            return self.last_recording
        self.last_recording = rec.finish(rec.capture_done or rec.elapsed >= rec.duration - 0.5)
        return self.last_recording

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
        last = 0.0
        try:
            for i, (frame, t) in enumerate(self.source):
                if self.stop_flag.is_set():
                    break
                box, _ = tracker.update(frame)
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
                rec = self.recorder
                if rec is not None:
                    rec.add(frame, t, mean if npx > 200 else None, npx, box)
                    # Capture stops at the planned length; the recording then
                    # waits for the last watch reading, at most 90 s.
                    if rec.capture_done and time.monotonic() - rec.frozen_at > 90:
                        threading.Thread(target=self.rec_stop, daemon=True).start()
                if i % 2 == 0:
                    self.jpeg = self._preview(frame, box)
                if t - last >= ANALYSE_EVERY:
                    last = t
                    self._analyse(t, box, npx, frame if box is not None else None)
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

    def _liveness(self, found: bool) -> dict:
        self.live_hist.append(bool(found))
        return _liveness_verdict(self.live_hist)

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
                 "params": {"mode": "select" if self.params.get("gamma") == float("inf") else "blend",
                            "version": self.params.get("version", 2), "gamma": _finite(self.params.get("gamma")),
                            "mask_k": self.params.get("mask_k"), "confidence": self.params.get("confidence")}}
        if isinstance(self.source, SimSource):
            state["true_bpm"] = self.source.true_bpm(now)
            state["sim"] = self.source.params
            state["fitzpatrick"] = state["sim"]["fitzpatrick"]
        elif isinstance(self.source, FileSource) and self.source.beats is not None:
            state["true_bpm"] = self.source.true_bpm(now)
            state["fitzpatrick"] = getattr(self.source, "fitzpatrick", None)
        rec = self.recorder
        if rec is not None:
            state["rec"] = {"active": True, "volunteer": rec.volunteer, "clip": rec.clip, "elapsed": round(rec.elapsed, 1),
                            "capture_done": rec.capture_done,
                            "duration": rec.duration, "readings": rec.readings, "condition": rec.condition}
        elif self.last_recording is not None:
            state["rec"] = {"active": False, "last": {k: v for k, v in self.last_recording.items() if k != "camera"}}
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
                # Each method's share of the summed quality scores: how much TRACE
                # trusts it. v3 then selects the most trusted one (weights 1, 0, 0).
                "scores": {k: round(v, 3) for k, v in weights_from_quality({m: w.quality for m, w in fr.per_method.items()}, 1.0).items()},
                "methods": {k: {"bpm": round(v.bpm, 1), "quality": round(v.quality, 3), "artifact": round(v.artifact, 3)}
                            for k, v in fr.per_method.items()},
                # Each method's artifact-masked spectrum, normalised to its own
                # in-band peak: what the fusion actually sums.
                "method_spectra": {k: _thin(v.power[band] / (v.power[band].max() + 1e-30), 240)
                                   for k, v in fr.per_method.items()},
                "p_correct": p_correct(fr.quality, self.params),
                "liveness": self._liveness(pulse_found(fr, LIVENESS_Q)),
                "method_traces": {k: _thin(pulses[k][show] / (np.std(pulses[k][show]) + 1e-12))
                                  for k in ("green", "chrom", "pos")},
                "naive_green": round(estimate_bpm(pulses["green"], FS).bpm, 1),
                # The green channel at each theory step, for the "How it works" view.
                "stages": {"raw": _thin(green_raw[show]),
                           "detrended": _thin(detrend(green_raw, default_detrend_window(FS))[show]),
                           "filtered": _thin(pulses["green"][show])},
                "trace": {"raw": _thin(green_raw[show]), "pulse": _thin(pulses[best][show] / (np.std(pulses[best][show]) + 1e-12)),
                          "best": best},
                "spectrum": {"f": _thin(fr.freqs[band] * 60, 240), "p": _thin(fp, 240), "peak": round(fr.bpm, 1)},
            })
        self.state = state


def _finite(x):
    """JSON has no infinity; the browser would reject the whole message."""
    return None if x is None or not np.isfinite(x) else x


def pulse_found(fr, threshold: float) -> bool:
    """One read-out's liveness vote, independent of how TRACE fuses: CHROM and
    POS, two different colour projections, must each find a clean peak
    (quality over the confidence threshold) and agree within 5 BPM."""
    c, p = fr.per_method["chrom"], fr.per_method["pos"]
    return min(c.quality, p.quality) >= threshold and abs(c.bpm - p.bpm) <= 5.0


def _liveness_verdict(hist) -> dict:
    n = len(hist)
    share = sum(hist) / n if n else 0.0
    verdict = "checking"
    if n >= LIVENESS_READOUTS // 2 and share >= LIVE_SHARE:
        verdict = "pulse"
    elif n >= int(LIVENESS_READOUTS * 0.8) and share <= NONE_SHARE:
        verdict = "none"
    return {"verdict": verdict, "share": round(share, 2), "n": n, "of": LIVENESS_READOUTS}


def _thin(x: np.ndarray, n: int = 300) -> list[float]:
    x = np.asarray(x, float)
    if len(x) > n:
        x = x[np.linspace(0, len(x) - 1, n).astype(int)]
    return [round(float(v), 4) for v in x]
