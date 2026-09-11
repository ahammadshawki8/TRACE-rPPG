"""Face-video simulator with known ground truth and controllable skin tone.

Why a simulator
---------------
The study needs video whose true heart rate, beat timing, and skin tone are
known exactly, stored losslessly, across all six Fitzpatrick types. Public
data with all of that is not yet in hand (CLAUDE.md, U2), so this module
renders it. It is a pilot instrument, not a substitute for real subjects:
every result produced from it is labelled as simulated.

What is modelled, and what is real
----------------------------------
Modelled (a simplified two-layer skin reflectance model):

    pixel_c(t) = L(t) * S(t) * [ s(t) + D_c * r_c(m) * (1 + a_c * p(t)) ]

    s(t)    channel-neutral surface reflection (the part of the light that
            never reaches blood), which varies with head motion
    D_c     dermal albedo of the base face, per pixel and channel
    r_c(m)  round-trip transmission through epidermal melanin relative to the
            base face, exp(-2 K (m - m0) mu_c), where mu_c follows melanin's
            absorption falling with wavelength, (600 nm / lambda)^3.46
    a_c     pulsatile modulation depth per channel along the standard blood
            volume pulse direction (0.33, 0.77, 0.53)
    p(t)    unit peak-to-peak PPG waveform with known beat times
    L, S    global illumination drift and motion-coupled shading

Real, not modelled: every codec, the chroma subsampling, the quantisation,
the face detector, and the entire estimation pipeline. The simulation's
assumption is only the physics chain "more melanin, smaller pulse in pixel
levels, and a bluer channel swamped by surface reflection". What compression
then does to that smaller pulse is measured, not assumed.

Base face: NASA astronaut portrait (Eileen Collins), public domain, shipped
with scikit-image as `skimage.data.astronaut()`.
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path

import cv2
import numpy as np

from .datasets import write_ubfc2_ground_truth
from .synth import Rhythm, heart_rhythm, ppg_from_beats

WIDTH, HEIGHT = 640, 480

# Epidermal melanin fraction per Fitzpatrick type (dimensionless model units).
FITZPATRICK_MELANIN = {1: 0.05, 2: 0.10, 3: 0.20, 4: 0.34, 5: 0.52, 6: 0.75}
BASE_TYPE = 2  # the base photograph is treated as Fitzpatrick II
MELANIN_K = 0.7
# Relative melanin absorption at R, G, B (600, 540, 460 nm): (600/lambda)^3.46
MELANIN_MU = np.array([1.00, 1.44, 2.56], dtype=np.float32)
PULSE_DIRECTION = np.array([0.33, 0.77, 0.53], dtype=np.float32)
SURFACE_LEVEL = 14.0  # surface reflection in 8-bit levels, channel neutral


@dataclass
class SimConfig:
    fitzpatrick: int = 2
    duration_s: float = 60.0
    fps: float = 30.0
    mean_bpm: float = 72.0
    pulse_depth: float = 0.010   # green peak-to-peak modulation of the dermal term
    motion: float = 0.5          # 0 still, 0.5 natural sitting, 1+ restless, 3 heavy
    illum_drift: float = 0.02    # relative amplitude of slow lighting change
    # Chromatic relighting from the screen being watched. 0.002 was chosen in
    # T3 so that uncompressed type II accuracy lands near published UBFC-rPPG
    # figures (POS 3.2 vs about 4, CHROM 6.3 vs about 4, GREEN 16 vs about 20).
    screen_light: float = 0.002
    read_noise: float = 1.0      # sensor noise floor, 8-bit levels
    shot_noise: float = 0.015    # signal-dependent noise variance per level
    lf_bpm: float = 3.0
    hf_bpm: float = 2.5
    resp_hz: float = 0.25
    seed: int = 0


_BASE: dict | None = None


def _base_face() -> dict:
    """Base frame, soft skin mask, and dermal albedo, computed once."""
    global _BASE
    if _BASE is not None:
        return _BASE
    from skimage.data import astronaut

    img = astronaut()[0:240, 63:383]  # face-centred 4:3 crop
    img = cv2.resize(img, (WIDTH, HEIGHT), interpolation=cv2.INTER_CUBIC).astype(np.float32)

    gray = cv2.cvtColor(img.astype(np.uint8), cv2.COLOR_RGB2GRAY)
    cascade = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
    faces = cascade.detectMultiScale(cv2.equalizeHist(gray), 1.1, 5, minSize=(100, 100))
    if len(faces) == 0:
        raise RuntimeError("base face not detected")
    x, y, w, h = max(faces, key=lambda f: f[2] * f[3])

    # Adaptive skin model: chroma statistics of the central face, so the mask
    # does not depend on a fixed colour threshold (which would itself be a
    # skin-tone bias).
    ycc = cv2.cvtColor(img.astype(np.uint8), cv2.COLOR_RGB2YCrCb).astype(np.float32)
    core = ycc[y + h // 3 : y + 2 * h // 3, x + w // 4 : x + 3 * w // 4]
    cr0, cb0 = np.median(core[..., 1]), np.median(core[..., 2])
    near = (np.abs(ycc[..., 1] - cr0) < 11) & (np.abs(ycc[..., 2] - cb0) < 11) & (ycc[..., 0] > 60)
    region = np.zeros_like(near)
    region[max(0, y - h // 5) : min(HEIGHT, y + int(1.45 * h)), max(0, x - w // 8) : min(WIDTH, x + w + w // 8)] = True
    mask = (near & region).astype(np.uint8)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((5, 5), np.uint8))
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((9, 9), np.uint8))
    soft = cv2.GaussianBlur(mask.astype(np.float32), (0, 0), 3.0)[..., None]

    dermal = np.clip(img - SURFACE_LEVEL, 0, None)
    _BASE = {"img": img, "mask": soft, "dermal": dermal, "face": (int(x), int(y), int(w), int(h))}
    return _BASE


def melanin_ratio(fitzpatrick: int) -> np.ndarray:
    """r_c(m): round-trip transmission relative to the base face, per channel."""
    dm = FITZPATRICK_MELANIN[fitzpatrick] - FITZPATRICK_MELANIN[BASE_TYPE]
    return np.exp(-2.0 * MELANIN_K * dm * MELANIN_MU).astype(np.float32)


def _motion_track(n: int, fps: float, level: float, rng: np.random.Generator) -> dict:
    """Head translation, rotation and a shading signal, all smooth.

    Natural sitting motion is mostly slow sway, but it also carries a
    broadband component that reaches into the heart-rate band. That in-band
    part is what separates the colour methods from the green channel.
    """
    t = np.arange(n) / fps

    def smooth_noise(cut_hz: float) -> np.ndarray:
        k = max(3, int(fps / cut_hz))
        z = rng.normal(size=n + k)
        s = np.convolve(z, np.ones(k) / k, mode="valid")[:n]
        return s / (np.std(s) + 1e-12)

    sway = np.sin(2 * np.pi * rng.uniform(0.08, 0.2) * t + rng.uniform(0, 6.28))
    fast = smooth_noise(2.5)
    dx = level * (3.0 * sway + 1.2 * fast)
    dy = level * (1.5 * smooth_noise(0.5) + 0.6 * smooth_noise(2.5))
    rot = level * 0.8 * smooth_noise(0.4)  # degrees
    shade = level * (0.004 * sway + 0.006 * fast)
    spec = level * 0.25 * fast
    return {"dx": dx, "dy": dy, "rot": rot, "shade": shade, "spec": spec}


def _screen_light(n: int, fps: float, level: float, rng: np.random.Generator) -> np.ndarray:
    """Per-channel illumination gain from a screen whose content changes.

    A telehealth patient is lit partly by the display they are watching.
    Its colour changes with the content, broadband and in the heart-rate
    band, and in no fixed direction in RGB. Unlike a brightness change this
    does not project to zero under CHROM or POS, so it sets a realistic floor
    on accuracy even for uncompressed video.
    """
    if level <= 0:
        return np.ones((n, 3), dtype=np.float32)
    k = max(3, int(fps / 3.0))
    out = np.zeros((n, 3))
    for _ in range(2):
        z = rng.normal(size=n + k)
        s = np.convolve(z, np.ones(k) / k, mode="valid")[:n]
        s /= np.std(s) + 1e-12
        u = rng.normal(size=3)
        u /= np.linalg.norm(u)
        out += np.outer(s, u)
    return (1.0 + level * out).astype(np.float32)


def render(cfg: SimConfig):
    """Yield (frame_rgb_uint8, t) for every frame, plus return ground truth.

    Use `simulate_recording` to write a dataset folder; use this generator
    directly for the demo app's replay mode.
    """
    base = _base_face()
    rng = np.random.default_rng(cfg.seed)
    n = int(round(cfg.duration_s * cfg.fps))
    t = np.arange(n) / cfg.fps

    rhythm = heart_rhythm(cfg.duration_s + 1.0, mean_bpm=cfg.mean_bpm, lf_bpm=cfg.lf_bpm,
                          hf_bpm=cfg.hf_bpm, resp_hz=cfg.resp_hz, seed=cfg.seed)
    p = ppg_from_beats(t, rhythm.beat_times).astype(np.float32)
    a = (cfg.pulse_depth * PULSE_DIRECTION / PULSE_DIRECTION[1]).astype(np.float32)
    ratio = melanin_ratio(cfg.fitzpatrick)

    mv = _motion_track(n, cfg.fps, cfg.motion, rng)
    drift = 1.0 + cfg.illum_drift * np.sin(2 * np.pi * rng.uniform(0.02, 0.05) * t + rng.uniform(0, 6.28))
    screen = _screen_light(n, cfg.fps, cfg.screen_light, rng)

    img, mask, dermal = base["img"], base["mask"], base["dermal"]
    skin_dermal = dermal * ratio
    fx, fy, fw, fh = base["face"]
    centre = (fx + fw / 2.0, fy + fh / 2.0)

    def gen():
        for i in range(n):
            surface = SURFACE_LEVEL * (1.0 + mv["spec"][i])
            skin = surface + skin_dermal * (1.0 + a * p[i])
            frame = img * (1.0 - mask) + skin * mask
            frame *= drift[i] * (1.0 + mv["shade"][i]) * screen[i]
            M = cv2.getRotationMatrix2D(centre, float(mv["rot"][i]), 1.0)
            M[0, 2] += mv["dx"][i]
            M[1, 2] += mv["dy"][i]
            frame = cv2.warpAffine(frame, M, (WIDTH, HEIGHT), flags=cv2.INTER_LINEAR,
                                   borderMode=cv2.BORDER_REFLECT)
            sigma = np.sqrt(cfg.read_noise**2 + cfg.shot_noise * np.clip(frame, 0, None))
            frame = frame + sigma * rng.standard_normal(frame.shape, dtype=np.float32)
            yield np.clip(np.rint(frame), 0, 255).astype(np.uint8), t[i]

    return gen(), rhythm, t, p


def simulate_recording(folder: Path, cfg: SimConfig, ffmpeg: str = "ffmpeg") -> Path:
    """Render one subject into `folder` in the UBFC DATASET_2 layout.

    Video is FFV1 in an RGB pixel format, so it is bit-exact lossless: the
    clean control condition every compressed version is compared against.
    """
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    frames, rhythm, t, _ = render(cfg)
    video = folder / "vid.mkv"
    cmd = [ffmpeg, "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24",
           "-s", f"{WIDTH}x{HEIGHT}", "-r", f"{cfg.fps}", "-i", "-",
           "-c:v", "ffv1", "-level", "3", "-slices", "4", "-pix_fmt", "bgr0", str(video)]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    try:
        for frame, _ in frames:
            proc.stdin.write(frame.tobytes())
    finally:
        proc.stdin.close()
        if proc.wait() != 0:
            raise RuntimeError(f"ffmpeg failed writing {video}")

    write_ground_truth(folder, cfg, rhythm)
    return video


def write_ground_truth(folder: Path, cfg: SimConfig, rhythm: Rhythm, fs_ppg: float = 60.0) -> None:
    """Reference PPG at 60 Hz plus the exact beat times, UBFC layout."""
    tg = np.arange(0.0, cfg.duration_s, 1.0 / fs_ppg)
    ppg = ppg_from_beats(tg, rhythm.beat_times)
    mids = 0.5 * (rhythm.beat_times[1:] + rhythm.beat_times[:-1])
    hr = np.interp(tg, mids, 60.0 / rhythm.rr)
    write_ubfc2_ground_truth(Path(folder) / "ground_truth.txt", ppg, hr, tg)
    meta = {
        "source": "simulated",
        "fitzpatrick": cfg.fitzpatrick,
        "melanin": FITZPATRICK_MELANIN[cfg.fitzpatrick],
        "fps": cfg.fps,
        "config": asdict(cfg),
        "beat_times": [round(float(b), 5) for b in rhythm.beat_times],
        "lf_hf_nominal": rhythm.lf_hf_nominal,
    }
    (Path(folder) / "meta.json").write_text(json.dumps(meta))


def skin_preview(fitzpatrick: int) -> np.ndarray:
    """A still frame of the base face rendered at one Fitzpatrick type."""
    base = _base_face()
    ratio = melanin_ratio(fitzpatrick)
    skin = SURFACE_LEVEL + base["dermal"] * ratio
    frame = base["img"] * (1.0 - base["mask"]) + skin * base["mask"]
    return np.clip(np.rint(frame), 0, 255).astype(np.uint8)
