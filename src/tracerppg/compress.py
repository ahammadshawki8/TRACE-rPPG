"""Compression harness. Tier T5.

Bitrate is the controlled variable. Every condition re-encodes the same
lossless source, and every output is decoded by the same ffmpeg to RGB24
(`video.frames`), so the only thing that differs between conditions is what
the encoder threw away.

Three lossless controls separate the mechanism into steps:

    lossless_rgb     FFV1 in RGB: bit-identical to the source (verified)
    lossless_yuv444  RGB -> YUV 4:4:4 -> RGB: colour conversion rounding only
    lossless_yuv420  adds 4:2:0 chroma subsampling, still no quantisation

Lossy conditions use real-time settings, because that is what a video call
does: x264 `veryfast` with `zerolatency`, x265 `veryfast`, and libvpx in
`realtime` mode, each held to a target bitrate with a matching max rate. An
optional 4:4:4 variant of H.264 isolates chroma subsampling from
quantisation at the same bitrate.
"""

from __future__ import annotations

import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

from .video import FFMPEG, probe

BITRATES = (100, 200, 400, 800, 1600)  # kbps at 640x480, 30 fps
LOSSY_CODECS = ("h264", "h265", "vp9")

_ENCODER = {"h264": "libx264", "h265": "libx265", "vp9": "libvpx-vp9", "vp8": "libvpx"}


@dataclass(frozen=True)
class Condition:
    name: str
    codec: str               # h264, h265, vp9, vp8, ffv1
    kbps: int | None = None  # None for lossless
    pix_fmt: str = "yuv420p"

    @property
    def lossless(self) -> bool:
        return self.kbps is None

    @property
    def order_key(self) -> float:
        """Sort key: lossless first (infinite bitrate), then high to low."""
        return float("inf") if self.kbps is None else float(self.kbps)


LOSSLESS = (
    Condition("lossless_rgb", "ffv1", None, "bgr0"),
    Condition("lossless_yuv444", "h264", None, "yuv444p"),
    Condition("lossless_yuv420", "h264", None, "yuv420p"),
)


def grid_conditions(
    codecs: tuple[str, ...] = LOSSY_CODECS,
    bitrates: tuple[int, ...] = BITRATES,
    yuv444_ablation: bool = True,
) -> list[Condition]:
    conds = list(LOSSLESS)
    for c in codecs:
        for k in bitrates:
            conds.append(Condition(f"{c}_{k}k", c, k, "yuv420p"))
    if yuv444_ablation:
        for k in bitrates:
            conds.append(Condition(f"h264_444_{k}k", "h264", k, "yuv444p"))
    return conds


def ffmpeg_args(cond: Condition, threads: int = 2) -> list[str]:
    """Encoder arguments for one condition."""
    if cond.codec == "ffv1":
        return ["-c:v", "ffv1", "-level", "3", "-slices", "4", "-pix_fmt", "bgr0"]
    if cond.lossless:
        return ["-c:v", "libx264", "-preset", "ultrafast", "-qp", "0", "-pix_fmt", cond.pix_fmt,
                "-threads", str(threads)]
    k = cond.kbps
    rate = ["-b:v", f"{k}k", "-maxrate", f"{k}k", "-bufsize", f"{2 * k}k"]
    if cond.codec == "h264":
        return ["-c:v", "libx264", "-preset", "veryfast", "-tune", "zerolatency", "-g", "250",
                *rate, "-pix_fmt", cond.pix_fmt, "-threads", str(threads)]
    if cond.codec == "h265":
        return ["-c:v", "libx265", "-preset", "veryfast", "-g", "250", *rate, "-pix_fmt", cond.pix_fmt,
                "-x265-params", f"log-level=error:pools={threads}:frame-threads=1"]
    if cond.codec in ("vp9", "vp8"):
        extra = ["-row-mt", "1"] if cond.codec == "vp9" else []
        return ["-c:v", _ENCODER[cond.codec], "-deadline", "realtime", "-cpu-used", "8",
                "-b:v", f"{k}k", "-minrate", f"{k}k", "-maxrate", f"{k}k", "-g", "250",
                *extra, "-pix_fmt", cond.pix_fmt, "-threads", str(threads)]
    raise ValueError(f"unknown codec {cond.codec}")


@dataclass
class EncodeResult:
    path: Path
    condition: Condition
    achieved_kbps: float
    seconds: float


def encode(src: Path, dst_dir: Path, cond: Condition, threads: int = 2) -> EncodeResult:
    """Encode `src` under one condition into `dst_dir/<name>.mkv`."""
    dst_dir = Path(dst_dir)
    dst_dir.mkdir(parents=True, exist_ok=True)
    dst = dst_dir / f"{cond.name}.mkv"
    t0 = time.time()
    cmd = [FFMPEG, "-y", "-v", "error", "-i", str(src), "-an", *ffmpeg_args(cond, threads), str(dst)]
    subprocess.run(cmd, check=True)
    info = probe(dst)
    return EncodeResult(dst, cond, info.bitrate_kbps or 0.0, time.time() - t0)
