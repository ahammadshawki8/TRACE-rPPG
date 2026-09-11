"""Face tracking, skin regions, and per-frame RGB traces. Tier T2.

Face detection uses OpenCV's Haar cascade: a fixed classifier built from
rectangle features evaluated on an integral image, with no training step in
this project. It initialises the box; phase correlation (the Fourier shift
theorem) then follows the face between frames, and Haar only returns to
correct gross drift. Re-detecting every few frames makes the box twitch, and
a twitching box changes which pixels are averaged, which is in-band noise.

Inside the box, three regions are averaged: forehead and both cheeks, the
places with the most capillary blood and the least hair and expression. A
per-frame adaptive skin mask keeps only pixels whose chroma is close to the
region's own median. A fixed colour threshold would be tuned to one skin tone
and would silently drop pixels from others, which is exactly the kind of
bias this project measures.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

import cv2
import numpy as np

from . import video as vio

CASCADE_FILE = "haarcascade_frontalface_default.xml"

# Regions as fractions of the face box: (x0, y0, x1, y1).
REGIONS = {
    "forehead": (0.28, 0.06, 0.72, 0.24),
    "cheek_l": (0.16, 0.50, 0.40, 0.72),
    "cheek_r": (0.60, 0.50, 0.84, 0.72),
}


@dataclass
class Traces:
    """Per-frame mean skin colour and the bookkeeping to judge it."""

    t: np.ndarray                # frame times, s
    rgb: np.ndarray              # (n, 3) mean R, G, B over skin pixels
    n_pixels: np.ndarray         # skin pixels averaged per frame
    boxes: np.ndarray            # (n, 4) smoothed face box x, y, w, h
    detected: np.ndarray         # bool, a fresh detection succeeded on this frame
    fps: float
    detect_attempts: int = 0
    detect_hits: int = 0
    crops: np.ndarray | None = field(default=None, repr=False)  # (n, s, s, 3) for neural baselines

    @property
    def detect_rate(self) -> float:
        return self.detect_hits / max(self.detect_attempts, 1)

    def save(self, path: Path) -> None:
        np.savez_compressed(path, t=self.t, rgb=self.rgb, n_pixels=self.n_pixels, boxes=self.boxes,
                            detected=self.detected, fps=self.fps,
                            detect=np.array([self.detect_attempts, self.detect_hits]))

    @classmethod
    def load(cls, path: Path) -> "Traces":
        z = np.load(path)
        a, h = (int(v) for v in z["detect"])
        return cls(z["t"], z["rgb"], z["n_pixels"], z["boxes"], z["detected"], float(z["fps"]), a, h)


class FaceTracker:
    """Haar to find the face, phase correlation to follow it.

    Measured in step3: re-running Haar every few frames makes the box wobble
    by 1 to 2 px even on a perfectly still face. That wobble changes which
    pixels are averaged, and on dark skin (pulse under one pixel level) it
    alone drove the green-channel error from 0.04 to 25 BPM.

    So Haar only initialises the box (median of the first few detections) and
    corrects gross drift. Frame-to-frame motion comes from phase correlation:
    by the Fourier shift theorem a translation multiplies the spectrum by a
    linear phase, so the inverse FFT of the normalised cross-power spectrum
    peaks at the shift, located to sub-pixel precision.
    """

    def __init__(self, every: int = 15, deadband: float = 0.12, init_hits: int = 5, scale: float = 0.5):
        self.cascade = cv2.CascadeClassifier(cv2.data.haarcascades + CASCADE_FILE)
        if self.cascade.empty():
            raise RuntimeError("Haar cascade not found; install opencv-python-headless<5")
        self.every, self.deadband, self.init_hits, self.scale = every, deadband, init_hits, scale
        self.box: np.ndarray | None = None
        self.i = 0
        self.attempts = 0
        self.hits = 0
        self._init: list[np.ndarray] = []
        self._anchor_patch: np.ndarray | None = None
        self._anchor_box: np.ndarray | None = None
        self._region: tuple[int, int, int, int] | None = None
        self._hann: np.ndarray | None = None

    def _set_anchor(self, gray: np.ndarray, box: np.ndarray) -> None:
        x, y, w, h = box
        H, W = gray.shape
        pad = 0.15
        x0, y0 = int(max(0, x - pad * w)), int(max(0, y - pad * h))
        x1, y1 = int(min(W, x + (1 + pad) * w)), int(min(H, y + (1 + pad) * h))
        self._region = (x0, y0, x1, y1)
        self._anchor_patch = gray[y0:y1, x0:x1].copy()
        self._anchor_box = box.copy()
        self._hann = cv2.createHanningWindow((x1 - x0, y1 - y0), cv2.CV_32F)

    def _track(self, gray: np.ndarray) -> tuple[np.ndarray, float]:
        x0, y0, x1, y1 = self._region
        (sx, sy), resp = cv2.phaseCorrelate(self._anchor_patch, gray[y0:y1, x0:x1], self._hann)
        box = self._anchor_box.copy()
        box[0] += sx
        box[1] += sy
        return box, resp

    def detect(self, rgb: np.ndarray) -> np.ndarray | None:
        small = cv2.resize(rgb, None, fx=self.scale, fy=self.scale, interpolation=cv2.INTER_AREA)
        gray = cv2.equalizeHist(cv2.cvtColor(small, cv2.COLOR_RGB2GRAY))
        min_side = int(0.15 * min(gray.shape))
        faces = self.cascade.detectMultiScale(gray, 1.1, 4, minSize=(min_side, min_side))
        if len(faces) == 0:
            return None
        if self.box is not None:
            # Prefer the face nearest the one being tracked (multiple people).
            c = self.box[:2] + self.box[2:] / 2
            best = min(faces, key=lambda f: np.hypot(*(f[:2] / self.scale + f[2:] / self.scale / 2 - c)))
        else:
            best = max(faces, key=lambda f: f[2] * f[3])
        return np.asarray(best, dtype=float) / self.scale

    def update(self, rgb: np.ndarray) -> tuple[np.ndarray | None, bool]:
        gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY).astype(np.float32)
        fresh = False
        self.i += 1

        if self.box is None:
            # Initialisation: collect a few detections and take the median box.
            self.attempts += 1
            found = self.detect(rgb)
            if found is not None:
                self.hits += 1
                fresh = True
                self._init.append(found)
            if len(self._init) >= self.init_hits or (self._init and self.attempts >= 3 * self.init_hits):
                self.box = np.median(np.array(self._init), axis=0)
                self._set_anchor(gray, self.box)
            return self.box, fresh

        box, resp = self._track(gray)
        w = self._anchor_box[2]
        moved = np.hypot(*(box[:2] - self._anchor_box[:2]))
        if moved > 0.2 * w or resp < 0.05:
            # The face has left the anchor patch (or changed a lot): re-anchor
            # on the tracked position, so the box does not jump.
            self._set_anchor(gray, box)
        self.box = box

        if self.i % self.every == 0:
            self.attempts += 1
            found = self.detect(rgb)
            if found is not None:
                self.hits += 1
                fresh = True
                c_found = found[:2] + found[2:] / 2
                c_box = self.box[:2] + self.box[2:] / 2
                if np.hypot(*(c_found - c_box)) > self.deadband * w:
                    # Gross drift: hard reset to the detector, keeping box size.
                    self.box = np.array([c_found[0] - self.box[2] / 2, c_found[1] - self.box[3] / 2,
                                         self.box[2], self.box[3]])
                    self._set_anchor(gray, self.box)
        return self.box, fresh


def skin_mean(rgb: np.ndarray, box: np.ndarray, chroma_tol: float = 14.0) -> tuple[np.ndarray, int]:
    """Mean RGB over skin pixels in the forehead and cheek regions."""
    x, y, w, h = box
    H, W = rgb.shape[:2]
    patches = []
    for fx0, fy0, fx1, fy1 in REGIONS.values():
        x0, x1 = int(max(0, x + fx0 * w)), int(min(W, x + fx1 * w))
        y0, y1 = int(max(0, y + fy0 * h)), int(min(H, y + fy1 * h))
        if x1 > x0 and y1 > y0:
            patches.append(rgb[y0:y1, x0:x1].reshape(-1, 3))
    if not patches:
        return np.full(3, np.nan), 0
    px = np.concatenate(patches)
    ycc = cv2.cvtColor(px.reshape(-1, 1, 3), cv2.COLOR_RGB2YCrCb).reshape(-1, 3).astype(np.float32)
    cr0, cb0 = np.median(ycc[:, 1]), np.median(ycc[:, 2])
    keep = (np.abs(ycc[:, 1] - cr0) < chroma_tol) & (np.abs(ycc[:, 2] - cb0) < chroma_tol) & (ycc[:, 0] > 8)
    if keep.sum() < 50:
        keep = np.ones(len(px), bool)
    return px[keep].astype(np.float64).mean(axis=0), int(keep.sum())


def face_crop(rgb: np.ndarray, box: np.ndarray, size: int = 72, enlarge: float = 1.5) -> np.ndarray:
    """Square crop around the face, enlarged as in rPPG-Toolbox preprocessing."""
    x, y, w, h = box
    cx, cy, side = x + w / 2, y + h / 2, enlarge * max(w, h)
    H, W = rgb.shape[:2]
    x0, y0 = int(round(cx - side / 2)), int(round(cy - side / 2))
    x1, y1 = x0 + int(round(side)), y0 + int(round(side))
    pad = max(0, -x0, -y0, x1 - W, y1 - H)
    if pad:
        rgb = cv2.copyMakeBorder(rgb, pad, pad, pad, pad, cv2.BORDER_REPLICATE)
        x0, x1, y0, y1 = x0 + pad, x1 + pad, y0 + pad, y1 + pad
    return cv2.resize(rgb[y0:y1, x0:x1], (size, size), interpolation=cv2.INTER_AREA)


def extract_from_frames(
    frame_iter: Iterable[np.ndarray],
    fps: float,
    crop_size: int | None = None,
    tracker: FaceTracker | None = None,
) -> Traces:
    """Run the tracker over frames and return the RGB traces."""
    tracker = tracker or FaceTracker()
    rgb_rows, npx, boxes, det, crops = [], [], [], [], []
    for frame in frame_iter:
        box, fresh = tracker.update(frame)
        if box is None:
            rgb_rows.append(np.full(3, np.nan))
            npx.append(0)
            boxes.append(np.full(4, np.nan))
            if crop_size:
                crops.append(np.zeros((crop_size, crop_size, 3), np.uint8))
        else:
            m, k = skin_mean(frame, box)
            rgb_rows.append(m)
            npx.append(k)
            boxes.append(box.copy())
            if crop_size:
                crops.append(face_crop(frame, box, crop_size))
        det.append(fresh)
    n = len(rgb_rows)
    rgb = np.array(rgb_rows)
    # Frames before the first detection have no box: back-fill from the first valid frame.
    bad = np.isnan(rgb[:, 0])
    if bad.any() and (~bad).any():
        idx = np.flatnonzero(~bad)
        for c in range(3):
            rgb[:, c] = np.interp(np.arange(n), idx, rgb[idx, c])
    return Traces(
        t=np.arange(n) / fps,
        rgb=rgb,
        n_pixels=np.array(npx),
        boxes=np.array(boxes),
        detected=np.array(det),
        fps=fps,
        detect_attempts=tracker.attempts,
        detect_hits=tracker.hits,
        crops=np.array(crops) if crop_size else None,
    )


def extract_traces(path: Path, crop_size: int | None = None) -> Traces:
    """Decode a video file and extract its RGB traces."""
    info = vio.probe(path)
    return extract_from_frames(vio.frames(path, info), info.fps, crop_size)
