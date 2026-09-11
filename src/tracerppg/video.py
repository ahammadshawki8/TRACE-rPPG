"""Video decoding through ffmpeg. Tier T2.

Every video, lossless or compressed, is decoded by the same ffmpeg binary to
packed RGB24 through a pipe. Using one decoder and one YUV-to-RGB conversion
for every condition means a difference between conditions is caused by the
codec, not by two libraries disagreeing about colour matrices.
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

import numpy as np

FFMPEG = "ffmpeg"
FFPROBE = "ffprobe"


@dataclass
class VideoInfo:
    width: int
    height: int
    fps: float
    codec: str
    pix_fmt: str
    duration_s: float
    bitrate_kbps: float | None


def probe(path: Path) -> VideoInfo:
    out = subprocess.run(
        [FFPROBE, "-v", "error", "-select_streams", "v:0", "-show_entries",
         "stream=width,height,r_frame_rate,codec_name,pix_fmt,bit_rate:format=duration,bit_rate,size",
         "-of", "json", str(path)],
        capture_output=True, text=True, check=True,
    )
    info = json.loads(out.stdout)
    s, f = info["streams"][0], info.get("format", {})
    num, den = (int(v) for v in s["r_frame_rate"].split("/"))
    duration = float(f.get("duration", 0.0) or 0.0)
    size = float(f.get("size", 0.0) or 0.0)
    kbps = size * 8 / duration / 1000 if duration > 0 and size > 0 else None
    return VideoInfo(int(s["width"]), int(s["height"]), num / den, s["codec_name"],
                     s.get("pix_fmt", ""), duration, kbps)


def frames(path: Path, info: VideoInfo | None = None) -> Iterator[np.ndarray]:
    """Yield every frame as an (H, W, 3) uint8 RGB array."""
    info = info or probe(path)
    n_bytes = info.width * info.height * 3
    proc = subprocess.Popen(
        [FFMPEG, "-v", "error", "-i", str(path), "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
        stdout=subprocess.PIPE, bufsize=n_bytes * 4,
    )
    try:
        while True:
            buf = proc.stdout.read(n_bytes)
            if len(buf) < n_bytes:
                break
            yield np.frombuffer(buf, np.uint8).reshape(info.height, info.width, 3)
    finally:
        # A caller that stops early (a thumbnail, a closed demo) would leave
        # ffmpeg writing into a closed pipe; end it quietly instead.
        if proc.poll() is None:
            proc.kill()
        proc.stdout.close()
        proc.wait()
